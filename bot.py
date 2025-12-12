import discord
from discord.ext import commands
import os
import asyncio
import requests
from dotenv import load_dotenv
import tempfile
import argparse
import hashlib
import functools
import json
import logging
import subprocess
from datetime import datetime
from logger_config import bot_logger
from dotenv import load_dotenv
import soundfile as sf
import numpy as np
from kokoro import KPipeline

# Load environment variables for logging configuration
load_dotenv()
LOG_DIR = os.getenv("LOG_DIR", "logs")

# Set Discord library logger level to capture all discord-related logs
discord_logger = logging.getLogger('discord')
discord_logger.setLevel(logging.INFO)

# Get the bot logger's file handler and add it to the Discord logger
# This ensures Discord logs go to the same file as bot logs
if bot_logger.handlers:
    for handler in bot_logger.handlers:
        if isinstance(handler, logging.handlers.TimedRotatingFileHandler):
            discord_logger.addHandler(handler)
            # Prevent propagation to avoid duplicate logs
            discord_logger.propagate = False

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
TTS_VOICE = os.getenv("TTS_VOICE", "af_bella")
TTS_ACCENT = os.getenv("TTS_ACCENT", "en-us")
TTS_SPEED = float(os.getenv("TTS_SPEED", 1.0))
CACHE_DIR = "audio_cache"

pipeline = None

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="%", intents=intents)

voice_client = None
disconnect_timer = None
request_queue = asyncio.Queue()
user_sounds = {}  # Dictionary to store user sound preferences: {user_id: {"join": sound_name, "leave": sound_name}}
last_tts_file = None  # Track the most recent TTS audio file (not soundboard)

async def disconnect_voice():
    global voice_client, disconnect_timer
    if voice_client:
        await voice_client.disconnect()
        voice_client = None
    disconnect_timer = None

async def audio_worker():
    global voice_client, disconnect_timer, last_tts_file
    while True:
        ctx, text = await request_queue.get()

        # Generate a unique filename from the hash of the text
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        output_filename = os.path.join(CACHE_DIR, f"{text_hash}.wav")

        if os.path.exists(output_filename):
            bot_logger.info(f"Playing from cache: {output_filename}")
        else:
            loop = asyncio.get_event_loop()
            try:
                await loop.run_in_executor(
                    None, functools.partial(fetch_and_cache_audio, text, output_filename)
                )
            except Exception as e:
                await ctx.send(f"An error occurred while generating audio: {e}")
                continue

        try:
            if voice_client is None or not voice_client.is_connected():
                voice_channel = ctx.author.voice.channel
                voice_client = await voice_channel.connect()

            # If there's a timer, cancel it
            if disconnect_timer:
                disconnect_timer.cancel()

            # Track the most recent TTS file
            last_tts_file = output_filename

            voice_client.play(discord.FFmpegPCMAudio(output_filename))

            while voice_client.is_playing():
                await asyncio.sleep(1)

            # Start a new timer (10 minutes)
            loop = asyncio.get_event_loop()
            disconnect_timer = loop.call_later(10 * 60, lambda: asyncio.ensure_future(disconnect_voice()))

            await ctx.send(f"Played: '{text}'")

        except Exception as e:
            await ctx.send(f"An error occurred: {e}")

@bot.event
async def on_ready():
    bot_logger.info(f'Logged in as {bot.user.name}')
    
    if not args.no_tts:
        global pipeline
        try:
            bot_logger.info("Initializing Kokoro TTS pipeline...")
            # Simple mapping for lang_code based on accent, default to 'a' (American English)
            lang_code = 'a'
            if TTS_ACCENT and 'gb' in TTS_ACCENT.lower():
                lang_code = 'b'
            
            pipeline = KPipeline(lang_code=lang_code)
            bot_logger.info(f"Kokoro TTS pipeline initialized (lang={lang_code}).")
        except Exception as e:
            bot_logger.error(f"Failed to initialize Kokoro TTS: {e}")
            bot_logger.warning("TTS functionality will be disabled.")
            args.no_tts = True
    else:
        bot_logger.info("Running without TTS (no-tts mode enabled)")

    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)
    
    # Load user sound preferences if file exists
    load_user_sounds()
    
    bot.loop.create_task(audio_worker())

def fetch_and_cache_audio(text, output_filename):
    bot_logger.info(f"Generating audio for: {text}")
    
    if pipeline is None:
        raise Exception("Kokoro pipeline not initialized")

    try:
        generator = pipeline(text, voice=TTS_VOICE, speed=TTS_SPEED)
        audio_segments = []
        for _, _, audio in generator:
            audio_segments.append(audio)
        
        if audio_segments:
            final_audio = np.concatenate(audio_segments)
            sf.write(output_filename, final_audio, 24000)
        else:
            bot_logger.warning(f"No audio generated for text: {text}")
            raise Exception("No audio generated by Kokoro")
            
    except Exception as e:
        bot_logger.error(f"Error generating audio: {e}")
        raise e

def load_user_sounds():
    """Load user sound preferences from file"""
    global user_sounds
    try:
        if os.path.exists("user_sounds.json"):
            with open("user_sounds.json", "r") as f:
                user_sounds = json.load(f)
    except Exception as e:
        bot_logger.error(f"Error loading user sounds: {e}")
        user_sounds = {}

def save_user_sounds():
    """Save user sound preferences to file"""
    try:
        with open("user_sounds.json", "w") as f:
            json.dump(user_sounds, f)
    except Exception as e:
        bot_logger.error(f"Error saving user sounds: {e}")

@bot.command(name="ask", help="Ask a question to the LLM and get a spoken response. Usage: %ask <your question>")
async def ask(ctx, *, text: str):
    if not ctx.author.voice:
        await ctx.send("You are not connected to a voice channel.")
        return
    
    if args.no_tts:
        await ctx.send("Error: Bot currently has TTS disabled.")
        return

    if not os.path.exists("system_prompt.txt"):
        bot_logger.warning("system_prompt.txt not found. Proceeding with an empty system prompt.")
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
    
    # Log the soundboard play request
    channel_name = ctx.author.voice.channel.name if ctx.author.voice else "Unknown"
    bot_logger.info(f"Soundboard: '{name}' requested by {ctx.author.name} ({ctx.author.id}) in channel {channel_name}")

    global voice_client
    try:
        if voice_client is None or not voice_client.is_connected():
            voice_channel = ctx.author.voice.channel
            bot_logger.info(f"Connecting to voice channel {voice_channel.name} to play soundboard sound")
            voice_client = await voice_channel.connect()
        
        bot_logger.info(f"Now playing soundboard sound: {filepath}")
        voice_client.play(discord.FFmpegPCMAudio(filepath))

        while voice_client.is_playing():
            await asyncio.sleep(1)
            
        bot_logger.info(f"Finished playing soundboard sound '{name}' for {ctx.author.name}")

    except Exception as e:
        bot_logger.error(f"Error playing soundboard sound '{name}' for {ctx.author.name}: {e}")
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

@bot.command(name="addsound", aliases=["upload"], help="Upload a new sound to the soundboard. Usage: %addsound <name> [url] or %upload <name> [url]")
async def upload_sound(ctx, name: str = None, url: str = None):
    if not name:
        await ctx.send("Please provide a name for the sound. Usage: `%addsound <name> [url]`")
        return
    
    # Check if sound already exists
    soundboard_dir = "soundboard"
    output_path = os.path.join(soundboard_dir, f"{name}.opus")
    if os.path.exists(output_path):
        await ctx.send(f"A sound with the name '{name}' already exists.")
        return
    
    # Determine if we're using an attachment or URL
    has_attachment = len(ctx.message.attachments) > 0
    has_url = url is not None
    
    if not has_attachment and not has_url:
        await ctx.send("Please either attach an audio file or provide a URL with your command.")
        return
    
    if has_attachment and has_url:
        await ctx.send("Please provide either an attachment or a URL, not both.")
        return
    
    temp_path = None
    filename = None
    
    try:
        # Create soundboard directory if it doesn't exist
        if not os.path.exists(soundboard_dir):
            os.makedirs(soundboard_dir)
        
        if has_attachment:
            # Handle file attachment
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
            
            # Download the file to a temporary location
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1]) as temp_file:
                await attachment.save(temp_file.name)
                temp_path = temp_file.name
        
        else:  # has_url
            if not (url.startswith('http://') or url.startswith('https://')):
                await ctx.send("Invalid URL format. Please provide a valid HTTP or HTTPS URL.")
                return
            
            # Get file extension from URL or default to .mp3
            url_lower = url.lower()
            if url_lower.endswith('.mp3'):
                filename = "temp.mp3"
            elif url_lower.endswith('.wav'):
                filename = "temp.wav"
            elif url_lower.endswith('.opus'):
                filename = "temp.opus"
            else:
                # Default to mp3 if we can't determine the extension
                filename = "temp.mp3"
            
            # Download the file from URL
            try:
                response = requests.get(url, stream=True)
                response.raise_for_status()
                
                # Check content-length if available
                content_length = response.headers.get('content-length')
                if content_length and int(content_length) > 3 * 1024 * 1024:  # 3MB
                    await ctx.send("File is too large. Please keep it under 3MB.")
                    return
                
                # Save to temporary file
                with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1]) as temp_file:
                    temp_path = temp_file.name
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:  # filter out keep-alive new chunks
                            temp_file.write(chunk)
                
            except requests.exceptions.RequestException as e:
                await ctx.send(f"Error downloading file from URL: {e}")
                return
        
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
                if temp_path:
                    os.unlink(temp_path)
            except subprocess.CalledProcessError as e:
                await ctx.send(f"Error converting file: {e.stderr.decode() if e.stderr else 'Unknown error'}")
                if temp_path and os.path.exists(temp_path):
                    os.unlink(temp_path)
                return
        
        await ctx.send(f"Sound '{name}' added to soundboard successfully!")
        
    except Exception as e:
        await ctx.send(f"An error occurred while processing the file: {e}")
        # Clean up temp file if it exists
        if temp_path and os.path.exists(temp_path):
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

@bot.command(name="setjoinsound", help="Set a sound to play when you join a voice channel. Usage: %setjoinsound <sound_name>")
async def set_join_sound(ctx, name: str = None):
    if not name:
        await ctx.send("Please provide a sound name. Usage: `%setjoinsound <sound_name>`")
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
    
    user_id = str(ctx.author.id)
    if user_id not in user_sounds:
        user_sounds[user_id] = {}
    
    user_sounds[user_id]["join"] = name
    save_user_sounds()
    await ctx.send(f"Your join sound has been set to '{name}'")

@bot.command(name="setleavesound", help="Set a sound to play when you leave a voice channel. Usage: %setleavesound <sound_name>")
async def set_leave_sound(ctx, name: str = None):
    if not name:
        await ctx.send("Please provide a sound name. Usage: `%setleavesound <sound_name>`")
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
    
    user_id = str(ctx.author.id)
    if user_id not in user_sounds:
        user_sounds[user_id] = {}
    
    user_sounds[user_id]["leave"] = name
    save_user_sounds()
    await ctx.send(f"Your leave sound has been set to '{name}'")

@bot.command(name="unsetjoinsound", help="Remove your join sound. Usage: %unsetjoinsound")
async def unset_join_sound(ctx):
    user_id = str(ctx.author.id)
    if user_id in user_sounds and "join" in user_sounds[user_id]:
        del user_sounds[user_id]["join"]
        save_user_sounds()
        await ctx.send("Your join sound has been removed.")
    else:
        await ctx.send("You don't have a join sound set.")

@bot.command(name="unsetleavesound", help="Remove your leave sound. Usage: %unsetleavesound")
async def unset_leave_sound(ctx):
    user_id = str(ctx.author.id)
    if user_id in user_sounds and "leave" in user_sounds[user_id]:
        del user_sounds[user_id]["leave"]
        save_user_sounds()
        await ctx.send("Your leave sound has been removed.")
    else:
        await ctx.send("You don't have a leave sound set.")

@bot.command(name="mysounds", help="Check your current join and leave sounds. Usage: %mysounds")
async def my_sounds(ctx):
    user_id = str(ctx.author.id)
    if user_id in user_sounds:
        join_sound = user_sounds[user_id].get("join", "None")
        leave_sound = user_sounds[user_id].get("leave", "None")
        await ctx.send(f"Your sounds:\nJoin: {join_sound}\nLeave: {leave_sound}")
    else:
        await ctx.send("You don't have any sounds set.")

@bot.command(name="replay", aliases=["repeat"], help="Replay the most recently played TTS sound file. Usage: %replay or %repeat")
async def replay(ctx):
    global voice_client, disconnect_timer, last_tts_file
    
    if not ctx.author.voice:
        await ctx.send("You are not connected to a voice channel.")
        return
    
    if args.no_tts:
        await ctx.send("Error: Bot currently has TTS disabled.")
        return
    
    if not last_tts_file or not os.path.exists(last_tts_file):
        await ctx.send("No TTS audio file has been played yet or the file is no longer available.")
        return
    
    try:
        if voice_client is None or not voice_client.is_connected():
            voice_channel = ctx.author.voice.channel
            voice_client = await voice_channel.connect()

        # If there's a timer, cancel it
        if disconnect_timer:
            disconnect_timer.cancel()

        voice_client.play(discord.FFmpegPCMAudio(last_tts_file))

        while voice_client.is_playing():
            await asyncio.sleep(1)

        # Start a new timer (10 minutes)
        loop = asyncio.get_event_loop()
        disconnect_timer = loop.call_later(10 * 60, lambda: asyncio.ensure_future(disconnect_voice()))

        await ctx.send("Replayed the most recent TTS audio.")

    except Exception as e:
        await ctx.send(f"An error occurred: {e}")

async def play_user_sound(member, channel, sound_type):
    """Play a user's join or leave sound"""
    user_id = str(member.id)
    if user_id in user_sounds and sound_type in user_sounds[user_id]:
        sound_name = user_sounds[user_id][sound_type]
        filepath = os.path.join("soundboard", f"{sound_name}.opus")
        
        # Log which user's sound is being played and for what action
        action = "joining" if sound_type == "join" else "leaving"
        bot_logger.info(f"Playing '{sound_name}' for user {member.name} ({user_id}) {action} voice channel '{channel.name}'")
        
        if os.path.exists(filepath):
            global voice_client, disconnect_timer
            try:
                # Connect to the channel if not already connected
                if voice_client is None or not voice_client.is_connected():
                    bot_logger.info(f"Connecting to voice channel {channel.name} to play user sound")
                    voice_client = await channel.connect()
                
                # Cancel any existing disconnect timer
                if disconnect_timer:
                    disconnect_timer.cancel()
                    disconnect_timer = None
                
                # Play the sound
                bot_logger.info(f"Now playing sound file: {filepath}")
                voice_client.play(discord.FFmpegPCMAudio(filepath))
                
                while voice_client.is_playing():
                    await asyncio.sleep(0.5)
                
                bot_logger.info(f"Finished playing '{sound_name}' for user {member.name}")
                
                # Set a new disconnect timer for 10 minutes (600 seconds)
                loop = asyncio.get_event_loop()
                disconnect_timer = loop.call_later(10 * 60, lambda: asyncio.ensure_future(disconnect_voice()))
                
            except Exception as e:
                bot_logger.error(f"Error playing user sound: {e}")
        else:
            bot_logger.warning(f"Sound file not found: {filepath}")

@bot.event
async def on_voice_state_update(member, before, after):
    """Handle voice state changes for join/leave sounds"""
    # Ignore bot's own voice state changes
    if member.bot:
        return
    
    # User joined a voice channel
    if before.channel is None and after.channel is not None:
        # Wait 1 second before playing the join sound to ensure connection is established
        await asyncio.sleep(1)
        await play_user_sound(member, after.channel, "join")
    
    # User left a voice channel
    elif before.channel is not None and after.channel is None:
        await play_user_sound(member, before.channel, "leave")

bot.run(DISCORD_TOKEN)
