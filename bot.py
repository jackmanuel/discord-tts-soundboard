import discord
from discord.ext import commands
import os
import asyncio
import requests
from dotenv import load_dotenv
import subprocess
import socket
import tempfile
import argparse

import hashlib

import functools
import json

def is_server_running(host, port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0

def start_server():
    server_venv_uvicorn = os.getenv("UVICORN_PATH")
    server_dir = os.getenv("SERVER_DIR")
    command = [
        server_venv_uvicorn,
        "openvoice.openvoice_server:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8080",
    ]
    print("Starting TTS server...")
    subprocess.Popen(command, cwd=server_dir)

def parse_args():
    parser = argparse.ArgumentParser(description="TTS Discord Bot")
    parser.add_argument("--no-tts", action="store_true",
                        help="Run the bot without starting the TTS server")
    return parser.parse_args()

args = parse_args()

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL")
TTS_VOICE = os.getenv("TTS_VOICE", "demo_speaker0")
TTS_ACCENT = os.getenv("TTS_ACCENT", "en-us")
TTS_SPEED = float(os.getenv("TTS_SPEED", 1.0))
SERVER_URL = "http://localhost:8080/synthesize_speech/"
CACHE_DIR = "audio_cache"

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="%", intents=intents)

voice_client = None
disconnect_timer = None
request_queue = asyncio.Queue()

async def disconnect_voice():
    global voice_client, disconnect_timer
    if voice_client:
        await voice_client.disconnect()
        voice_client = None
    disconnect_timer = None

async def audio_worker():
    global voice_client, disconnect_timer
    while True:
        ctx, text = await request_queue.get()

        # Generate a unique filename from the hash of the text
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        output_filename = os.path.join(CACHE_DIR, f"{text_hash}.wav")

        if os.path.exists(output_filename):
            print(f"Playing from cache: {output_filename}")
        else:
            loop = asyncio.get_event_loop()
            try:
                await loop.run_in_executor(
                    None, functools.partial(fetch_and_cache_audio, text, output_filename)
                )
            except requests.exceptions.RequestException as e:
                await ctx.send(f"Error contacting TTS server: {e}")
                continue
            except Exception as e:
                await ctx.send(f"An error occurred while fetching audio: {e}")
                continue

        try:
            if voice_client is None or not voice_client.is_connected():
                voice_channel = ctx.author.voice.channel
                voice_client = await voice_channel.connect()

            # If there's a timer, cancel it
            if disconnect_timer:
                disconnect_timer.cancel()

            voice_client.play(discord.FFmpegPCMAudio(output_filename))

            while voice_client.is_playing():
                await asyncio.sleep(1)

            # Start a new timer
            loop = asyncio.get_event_loop()
            disconnect_timer = loop.call_later(20 * 60, lambda: asyncio.ensure_future(disconnect_voice()))

            await ctx.send(f"Played: '{text}'")

        except Exception as e:
            await ctx.send(f"An error occurred: {e}")

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    
    if not args.no_tts:
        if not is_server_running("127.0.0.1", 8080):
            start_server()
            print("Waiting for TTS server to start...")
            for _ in range(6):  # Try to connect for 30 seconds
                if is_server_running("127.0.0.1", 8080):
                    print("TTS server started.")
                    break
                await asyncio.sleep(5)
            else:
                print("TTS server did not start in time.")
                # You might want to add further error handling here
    else:
        print("Running without TTS server (no-tts mode enabled)")

    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)
    bot.loop.create_task(audio_worker())

def fetch_and_cache_audio(text, output_filename):
    print(f"Fetching from server: {text}")
    params = {
        "text": text,
        "voice": TTS_VOICE,
        "accent": TTS_ACCENT,
        "speed": TTS_SPEED,
    }
    response = requests.get(SERVER_URL, params=params)
    response.raise_for_status()  # Raise an exception for bad status codes

    with open(output_filename, "wb") as f:
        f.write(response.content)

import json

@bot.command(name="ask", help="Ask a question to the LLM and get a spoken response. Usage: %ask <your question>")
async def ask(ctx, *, text: str):
    if not ctx.author.voice:
        await ctx.send("You are not connected to a voice channel.")
        return
    
    if args.no_tts:
        await ctx.send("Error: Bot currently has TTS disabled.")
        return

    if not os.path.exists("system_prompt.txt"):
        print("Warning: system_prompt.txt not found. Proceeding with an empty system prompt.")
        system_prompt = ""
    else:
        with open("system_prompt.txt", "r", encoding="utf-8") as f:
            system_prompt = f.read()

    # Optional: Map Discord usernames to real names for a more personalized prompt.
    user_map = {}
    if os.path.exists("user_map.json"):
        with open("user_map.json", "r", encoding="utf-8") as f:
            user_map = json.load(f)

    author_name = ctx.author.name
    if author_name in user_map:
        real_name = user_map[author_name]
        system_prompt += f"\n\nThe user making this request is: {real_name}"

    try:
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            },
            json={
                "model": OPENROUTER_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text},
                ],
            },
        )
        response.raise_for_status()
        llm_response = response.json()["choices"][0]["message"]["content"]
        await request_queue.put((ctx, llm_response))
        await ctx.send(f"Sent to LLM: '{text}'")

    except requests.exceptions.RequestException as e:
        await ctx.send(f"Error contacting OpenRouter API: {e}")
    except Exception as e:
        await ctx.send(f"An error occurred: {e}")

@bot.command(name="soundboard", aliases=["sb"], help="Play a sound from the soundboard. Usage: %soundboard <sound_name> or %sb <sound_name>")
async def soundboard(ctx, name: str = None):
    if not name:
        await ctx.send("Please provide a sound name. Usage: `%sb <sound_name>`")
        return
    if not ctx.author.voice:
        await ctx.send("You are not connected to a voice channel.")
        return

    soundboard_dir = "soundboard"
    try:
        available_sounds = [f.split('.')[0] for f in os.listdir(soundboard_dir) if f.endswith('.opus')]
    except FileNotFoundError:
        await ctx.send(f"Soundboard directory not found.")
        return

    if name not in available_sounds:
        if len(available_sounds) > 1:
            sounds_list = ", ".join(available_sounds[:-1]) + f", or {available_sounds[-1]}"
        elif available_sounds:
            sounds_list = available_sounds[0]
        else:
            sounds_list = ""
        await ctx.send(f"Invalid sound. Choose from: {sounds_list}")
        return

    filepath = os.path.join(soundboard_dir, f"{name}.opus")

    global voice_client
    try:
        if voice_client is None or not voice_client.is_connected():
            voice_channel = ctx.author.voice.channel
            voice_client = await voice_channel.connect()
        
        voice_client.play(discord.FFmpegPCMAudio(filepath))

        while voice_client.is_playing():
            await asyncio.sleep(1)

    except Exception as e:
        await ctx.send(f"An error occurred: {e}")

@bot.command(name="say", help="Convert text to speech and play it in the voice channel. Usage: %say <text>")
async def say(ctx, *, text: str):
    if not ctx.author.voice:
        await ctx.send("You are not connected to a voice channel.")
        return
    
    if args.no_tts:
        await ctx.send("Error: Bot currently has TTS disabled.")
        return

    await request_queue.put((ctx, text))
    await ctx.send(f"Added to queue: '{text}'")

@bot.command(name="stop", help="Stop the currently playing audio. Usage: %stop")
async def stop(ctx):
    global voice_client
    if voice_client and voice_client.is_connected() and voice_client.is_playing():
        voice_client.stop()
        await ctx.send("Audio stopped.")
    else:
        await ctx.send("No audio is currently playing.")

@bot.command(name="addsound", aliases=["upload"], help="Upload a new sound to the soundboard. Usage: %addsound <sound_name> or %upload <sound_name>")
async def upload_sound(ctx, name: str = None):
    if not name:
        await ctx.send("Please provide a name for the sound. Usage: `!upload soundname`")
        return
    
    if not ctx.message.attachments:
        await ctx.send("Please attach an audio file with your command.")
        return
    
    # Check if sound already exists
    soundboard_dir = "soundboard"
    output_path = os.path.join(soundboard_dir, f"{name}.opus")
    if os.path.exists(output_path):
        await ctx.send(f"A sound with the name '{name}' already exists.")
        return
    
    attachment = ctx.message.attachments[0]
    
    # Check file size
    if attachment.size > 3 * 1024 * 1024:  # 3MB
        await ctx.send("File is too large. Please keep it under 3MB.")
        return
    
    # Get file extension
    filename = attachment.filename.lower()
    if not (filename.endswith('.mp3') or filename.endswith('.wav') or filename.endswith('.opus')):
        await ctx.send("Invalid file type. Please upload .mp3, .wav, or .opus files only.")
        return
    
    try:
        # Create soundboard directory if it doesn't exist
        if not os.path.exists(soundboard_dir):
            os.makedirs(soundboard_dir)
        
        # Download the file to a temporary location
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1]) as temp_file:
            await attachment.save(temp_file.name)
            temp_path = temp_file.name
        
        # Convert to opus if needed
        if filename.endswith('.opus'):
            import shutil
            shutil.move(temp_path, output_path)
        else:
            # Convert mp3/wav to opus using ffmpeg
            try:
                command = [
                    'ffmpeg',
                    '-i', temp_path,
                    '-c:a', 'libopus',
                    output_path
                ]
                subprocess.run(command, check=True, capture_output=True)
                os.unlink(temp_path)
            except subprocess.CalledProcessError as e:
                await ctx.send(f"Error converting file: {e.stderr.decode() if e.stderr else 'Unknown error'}")
                os.unlink(temp_path)
                return
        
        await ctx.send(f"Sound '{name}' added to soundboard successfully!")
        
    except Exception as e:
        await ctx.send(f"An error occurred while processing the file: {e}")
        # Clean up temp file if it exists
        if 'temp_path' in locals() and os.path.exists(temp_path):
            os.unlink(temp_path)

@bot.command(name="listsounds", aliases=["ls"], help="List all available sounds in the soundboard. Usage: %listsounds or %ls")
async def list_sounds(ctx):
    soundboard_dir = "soundboard"
    try:
        available_sounds = [f.split('.')[0] for f in os.listdir(soundboard_dir) if f.endswith('.opus')]
    except FileNotFoundError:
        await ctx.send("Soundboard directory not found.")
        return
    
    if not available_sounds:
        await ctx.send("No sounds available in the soundboard.")
        return
    
    sounds_list = ", ".join(available_sounds)
    await ctx.send(f"Available sounds: {sounds_list}")

@bot.command(name="deletesound", aliases=["rmsound"], help="Delete a sound from the soundboard (admin only). Usage: %deletesound <sound_name> or %rmsound <sound_name>")
async def delete_sound(ctx, name: str):
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("You need administrator permissions to delete sounds.")
        return
    
    soundboard_dir = "soundboard"
    sound_path = os.path.join(soundboard_dir, f"{name}.opus")
    
    if not os.path.exists(sound_path):
        await ctx.send(f"Sound '{name}' not found.")
        return
    
    try:
        os.remove(sound_path)
        await ctx.send(f"Sound '{name}' deleted successfully.")
    except Exception as e:
        await ctx.send(f"An error occurred while deleting the sound: {e}")

bot.run(DISCORD_TOKEN)
