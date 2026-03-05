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
import shutil
import soundboard_generator

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

# Bot configuration constants
VOICE_DISCONNECT_TIMEOUT_SECONDS = 600  # 10 minutes - how long to wait before disconnecting from voice
TTS_SAMPLE_RATE = 24000  # Sample rate for Kokoro TTS audio output

# File size and duration limits for soundboard uploads
MAX_ATTACHMENT_SIZE_MB = 3  # Maximum file size for direct Discord attachments
MAX_YTDLP_FILE_SIZE_MB = 15  # Maximum file size for yt-dlp downloads
MAX_SOUND_DURATION_SECONDS = 600  # Maximum duration for soundboard sounds
MAX_URL_FILE_SIZE_MB = 5  # Maximum file size for direct URL downloads
DOWNLOAD_CHUNK_SIZE = 8192  # Chunk size for streaming URL downloads
JOIN_SOUND_DELAY_SECONDS = 1  # Delay before playing join sound to ensure connection is established

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
            # Cancel any existing disconnect timer before connecting
            # to prevent it firing during a slow connection
            if disconnect_timer:
                disconnect_timer.cancel()
                disconnect_timer = None

            if voice_client is None or not voice_client.is_connected():
                voice_channel = ctx.author.voice.channel
                voice_client = await voice_channel.connect()

            # Track the most recent TTS file
            last_tts_file = output_filename

            source = await discord.FFmpegOpusAudio.from_probe(output_filename)
            voice_client.play(source)

            while voice_client.is_playing():
                await asyncio.sleep(1)

            # Start a new timer (10 minutes)
            loop = asyncio.get_event_loop()
            disconnect_timer = loop.call_later(VOICE_DISCONNECT_TIMEOUT_SECONDS, lambda: asyncio.ensure_future(disconnect_voice()))

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
            sf.write(output_filename, final_audio, TTS_SAMPLE_RATE)
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
    channel_name = ctx.channel.name if ctx.channel else "DM"
    guild_name = ctx.guild.name if ctx.guild else "DM"
    bot_logger.info(f"Command: %ask | User: {ctx.author.name} ({ctx.author.id}) | Guild: {guild_name} | Channel: {channel_name} | Text: '{text}'")
    
    if not ctx.author.voice:
        bot_logger.info(f"Command %ask rejected: User {ctx.author.name} not in voice channel")
        await ctx.send("You are not connected to a voice channel.")
        return
    
    if args.no_tts:
        bot_logger.info(f"Command %ask rejected: TTS disabled")
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

@bot.command(name="soundboard", aliases=["sb"], help="Play a sound from the soundboard. Usage: %sb <sound_name> | %sb all [seconds|full] | %sb seq [seconds]")
async def soundboard(ctx, name: str = None, option: str = None):
    global voice_client, disconnect_timer
    channel_name = ctx.channel.name if ctx.channel else "DM"
    guild_name = ctx.guild.name if ctx.guild else "DM"
    voice_channel_name = ctx.author.voice.channel.name if ctx.author.voice else "None"
    bot_logger.info(f"Command: %soundboard | User: {ctx.author.name} ({ctx.author.id}) | Guild: {guild_name} | Channel: {channel_name} | Voice: {voice_channel_name} | Sound: '{name}' | Option: '{option}'")
    
    if not name:
        bot_logger.info(f"Command %soundboard rejected: No sound name provided")
        await ctx.send("Please provide a sound name. Usage: `%sb <sound_name>`")
        return
    if not ctx.author.voice:
        bot_logger.info(f"Command %soundboard rejected: User {ctx.author.name} not in voice channel")
        await ctx.send("You are not connected to a voice channel.")
        return

    # Handle special sounds: "all" and "seq"
    if name in ("all", "seq"):
        # Determine the duration key
        if name == "all":
            if option is None:
                duration_key = soundboard_generator.DEFAULT_ALL_DURATION
            elif option.lower() == "full":
                duration_key = "full"
            else:
                try:
                    duration_key = int(option)
                    if duration_key < 1:
                        await ctx.send("Duration must be at least 1 second.")
                        return
                except ValueError:
                    await ctx.send("Invalid option. Usage: `%sb all [seconds|full]`")
                    return
        else:  # seq
            if option is None:
                duration_key = soundboard_generator.DEFAULT_SEQ_DURATION
            elif option.lower() == "full":
                duration_key = "full"
            else:
                try:
                    duration_key = int(option)
                    if duration_key < 1:
                        await ctx.send("Duration must be at least 1 second.")
                        return
                except ValueError:
                    await ctx.send("Invalid option. Usage: `%sb seq [seconds|full]`")
                    return
        
        # Check if there are any real sounds to work with
        real_sounds = soundboard_generator.get_real_sound_names()
        if not real_sounds:
            await ctx.send("No sounds available to generate from.")
            return
        
        # Get or generate the sound
        filepath, status_msg = await soundboard_generator.get_or_generate(name, duration_key, ctx)
        
        if not filepath:
            if not status_msg:
                await ctx.send(f"Failed to generate {name} sound.")
            return
        
        # Play the generated sound
        try:
            # Cancel any existing disconnect timer before connecting
            # to prevent it firing during a slow connection
            if disconnect_timer:
                disconnect_timer.cancel()
                disconnect_timer = None
            
            if voice_client is None or not voice_client.is_connected():
                voice_channel = ctx.author.voice.channel
                bot_logger.info(f"Command %soundboard: Connecting to voice channel '{voice_channel.name}'")
                voice_client = await voice_channel.connect()
            
            duration_display = "full" if duration_key == "full" else f"{duration_key}s"
            bot_logger.info(f"Command %soundboard: Playing '{name}' ({duration_display}) ({filepath})")
            
            # Get file duration with ffprobe and notify in Discord
            try:
                probe = subprocess.run(
                    ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration', '-of', 'csv=p=0', filepath],
                    capture_output=True, text=True, timeout=5
                )
                if probe.returncode == 0 and probe.stdout.strip():
                    total_seconds = float(probe.stdout.strip())
                    minutes = int(total_seconds) // 60
                    seconds = int(total_seconds) % 60
                    if minutes > 0:
                        await ctx.send(f"▶️ Playing **{name}** ({duration_display}) — {minutes}m {seconds}s")
                    else:
                        await ctx.send(f"▶️ Playing **{name}** ({duration_display}) — {seconds}s")
            except Exception:
                pass  # Don't block playback if ffprobe fails
            
            source = await discord.FFmpegOpusAudio.from_probe(filepath)
            voice_client.play(source)

            while voice_client.is_playing():
                await asyncio.sleep(1)
                
            bot_logger.info(f"Command %soundboard: Finished playing '{name}' ({duration_display}) for {ctx.author.name}")

        except Exception as e:
            bot_logger.error(f"Command %soundboard: Error playing '{name}' for {ctx.author.name}: {e}")
            await ctx.send(f"An error occurred: {e}")
        return

    # Regular sound playback
    soundboard_dir = "soundboard"
    try:
        available_sounds = soundboard_generator.get_real_sound_names()
    except Exception:
        bot_logger.warning(f"Command %soundboard: Soundboard directory not found")
        await ctx.send(f"Soundboard directory not found.")
        return

    if name not in available_sounds:
        bot_logger.info(f"Command %soundboard rejected: Invalid sound '{name}'")
        # Include 'all' and 'seq' in the hint
        display_sounds = available_sounds + ["all", "seq"]
        if len(display_sounds) > 1:
            sounds_list = ", ".join(display_sounds[:-1]) + f", or {display_sounds[-1]}"
        elif display_sounds:
            sounds_list = display_sounds[0]
        else:
            sounds_list = ""
        await ctx.send(f"Invalid sound. Choose from: {sounds_list}")
        return

    filepath = os.path.join(soundboard_dir, f"{name}.opus")


    try:
        # Cancel any existing disconnect timer before connecting
        # to prevent it firing during a slow connection
        if disconnect_timer:
            disconnect_timer.cancel()
            disconnect_timer = None
        
        if voice_client is None or not voice_client.is_connected():
            voice_channel = ctx.author.voice.channel
            bot_logger.info(f"Command %soundboard: Connecting to voice channel '{voice_channel.name}'")
            voice_client = await voice_channel.connect()
        
        bot_logger.info(f"Command %soundboard: Playing '{name}' ({filepath})")
        source = await discord.FFmpegOpusAudio.from_probe(filepath)
        voice_client.play(source)

        while voice_client.is_playing():
            await asyncio.sleep(1)
            
        bot_logger.info(f"Command %soundboard: Finished playing '{name}' for {ctx.author.name}")

    except Exception as e:
        bot_logger.error(f"Command %soundboard: Error playing '{name}' for {ctx.author.name}: {e}")
        await ctx.send(f"An error occurred: {e}")

@bot.command(name="say", help="Convert text to speech and play it in the voice channel. Usage: %say <text>")
async def say(ctx, *, text: str):
    channel_name = ctx.channel.name if ctx.channel else "DM"
    guild_name = ctx.guild.name if ctx.guild else "DM"
    voice_channel = ctx.author.voice.channel.name if ctx.author.voice else "None"
    bot_logger.info(f"Command: %say | User: {ctx.author.name} ({ctx.author.id}) | Guild: {guild_name} | Channel: {channel_name} | Voice: {voice_channel} | Text: '{text}'")
    
    if not ctx.author.voice:
        bot_logger.info(f"Command %say rejected: User {ctx.author.name} not in voice channel")
        await ctx.send("You are not connected to a voice channel.")
        return
    
    if args.no_tts:
        bot_logger.info(f"Command %say rejected: TTS disabled")
        await ctx.send("Error: Bot currently has TTS disabled.")
        return

    await request_queue.put((ctx, text))
    bot_logger.info(f"Command %say: Added to queue for user {ctx.author.name}")
    await ctx.send(f"Added to queue: '{text}'")

@bot.command(name="stop", aliases=["skip"], help="Stop the currently playing audio. Usage: %stop")
async def stop(ctx):
    channel_name = ctx.channel.name if ctx.channel else "DM"
    guild_name = ctx.guild.name if ctx.guild else "DM"
    bot_logger.info(f"Command: %stop | User: {ctx.author.name} ({ctx.author.id}) | Guild: {guild_name} | Channel: {channel_name}")
    
    global voice_client
    if voice_client and voice_client.is_connected() and voice_client.is_playing():
        voice_client.stop()
        bot_logger.info(f"Command %stop: Audio stopped by {ctx.author.name}")
        await ctx.send("Audio stopped.")
    else:
        bot_logger.info(f"Command %stop: No audio playing")
        await ctx.send("No audio is currently playing.")

@bot.command(name="addsound", aliases=["upload"], help="Upload a new sound to the soundboard. Usage: %addsound <name> [url] or %upload <name> [url]. Supports YouTube and SoundCloud.")
async def upload_sound(ctx, name: str = None, url: str = None):
    channel_name = ctx.channel.name if ctx.channel else "DM"
    guild_name = ctx.guild.name if ctx.guild else "DM"
    
    # Determine if we're using an attachment or URL
    has_attachment = len(ctx.message.attachments) > 0
    has_url = url is not None
    
    source_info = f"URL: {url}" if has_url else (f"Attachment: {ctx.message.attachments[0].filename}" if has_attachment else "None")
    bot_logger.info(f"Command: %addsound | User: {ctx.author.name} ({ctx.author.id}) | Guild: {guild_name} | Channel: {channel_name} | Name: '{name}' | Source: {source_info}")
    
    if not name:
        bot_logger.info(f"Command %addsound rejected: No sound name provided")
        await ctx.send("Please provide a name for the sound. Usage: `%addsound <name> [url]`")
        return
    
    # Check if sound already exists
    soundboard_dir = "soundboard"
    output_path = os.path.join(soundboard_dir, f"{name}.opus")
    if os.path.exists(output_path):
        bot_logger.info(f"Command %addsound rejected: Sound '{name}' already exists")
        await ctx.send(f"A sound with the name '{name}' already exists.")
        return
    
    if not has_attachment and not has_url:
        bot_logger.info(f"Command %addsound rejected: No source provided")
        await ctx.send("Please either attach an audio file or provide a URL with your command.")
        return
    
    if has_attachment and has_url:
        bot_logger.info(f"Command %addsound rejected: Both attachment and URL provided")
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
            if attachment.size > MAX_ATTACHMENT_SIZE_MB * 1024 * 1024:
                bot_logger.info(f"Command %addsound rejected: Attachment too large ({attachment.size} bytes)")
                await ctx.send(f"File is too large. Please keep it under {MAX_ATTACHMENT_SIZE_MB}MB.")
                return
            
            # Get file extension
            filename = attachment.filename.lower()
            if not (filename.endswith('.mp3') or filename.endswith('.wav') or filename.endswith('.opus')):
                bot_logger.info(f"Command %addsound rejected: Invalid file type '{filename}'")
                await ctx.send("Invalid file type. Please upload .mp3, .wav, or .opus files only.")
                return
            
            # Download the file to a temporary location
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1]) as temp_file:
                await attachment.save(temp_file.name)
                temp_path = temp_file.name
        
        else:  # has_url
            if not (url.startswith('http://') or url.startswith('https://')):
                bot_logger.info(f"Command %addsound rejected: Invalid URL format")
                await ctx.send("Invalid URL format. Please provide a valid HTTP or HTTPS URL.")
                return
            
            # Detect if it's a YouTube/SoundCloud/video site URL
            is_video_site = any(domain in url.lower() for domain in [
                "youtube.com", "youtu.be", "soundcloud.com", "vimeo.com", 
                "twitch.tv", "tiktok.com", "twitter.com", "x.com", "instagram.com"
            ])
            
            if is_video_site:
                status_msg = await ctx.send(f"Fetching audio from link...")
                try:
                    # Use a temporary file base for yt-dlp
                    temp_base = os.path.join(tempfile.gettempdir(), f"ytdlp_{hashlib.md5(url.encode()).hexdigest()}")
                    
                    command = [
                        'yt-dlp',
                        '-x',
                        '--audio-format', 'opus',
                        '--no-playlist',
                        '--max-filesize', f'{MAX_YTDLP_FILE_SIZE_MB}M',
                        '--match-filter', f'duration < {MAX_SOUND_DURATION_SECONDS}',
                        '-o', f"{temp_base}.%(ext)s",
                        url
                    ]
                    
                    process = await asyncio.create_subprocess_exec(
                        *command,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    stdout, stderr = await process.communicate()
                    
                    combined_output = (stdout.decode() + "\n" + stderr.decode()).lower()
                    
                    if process.returncode != 0 or not os.path.exists(f"{temp_base}.opus"):
                        if "does not pass filter" in combined_output or "skipping" in combined_output:
                            bot_logger.warning(f"Command %addsound: Failed for '{name}' - Video too long | URL: {url}")
                            await status_msg.edit(content=f"Error: Audio is too long (max {MAX_SOUND_DURATION_SECONDS} seconds).")
                        elif "larger than max-filesize" in combined_output:
                            bot_logger.warning(f"Command %addsound: Failed for '{name}' - File too large | URL: {url}")
                            await status_msg.edit(content=f"Error: File is too large (max {MAX_YTDLP_FILE_SIZE_MB}MB).")
                        else:
                            if process.returncode != 0:
                                bot_logger.error(f"Command %addsound: yt-dlp error (code {process.returncode}): {stderr.decode()}")
                            else:
                                bot_logger.error(f"Command %addsound: yt-dlp finished but file missing | Output: {combined_output}")
                            await status_msg.edit(content="Error: Failed to process the provided link.")
                        return

                    # Find what yt-dlp actually created
                    expected_file = f"{temp_base}.opus"
                    shutil.move(expected_file, output_path)
                    bot_logger.info(f"Command %addsound: Successfully added '{name}' to soundboard (via yt-dlp)")
                    await status_msg.edit(content=f"Sound '{name}' added to soundboard successfully!")
                    # Regenerate special sounds in background
                    bot_logger.info(f"Command %addsound: Triggering regeneration of cached special sounds")
                    asyncio.ensure_future(soundboard_generator.regenerate_all_cached())
                    return
                        
                except Exception as e:
                    bot_logger.error(f"Command %addsound: yt-dlp exception for '{name}': {e}")
                    await ctx.send("An unexpected error occurred while processing the link.")
                    return

            # Fallback to direct download for other URLs
            url_lower = url.lower()
            if url_lower.endswith('.mp3'):
                filename = "temp.mp3"
            elif url_lower.endswith('.wav'):
                filename = "temp.wav"
            elif url_lower.endswith('.opus'):
                filename = "temp.opus"
            else:
                filename = "temp.mp3"
            
            try:
                response = requests.get(url, stream=True)
                response.raise_for_status()
                
                content_length = response.headers.get('content-length')
                if content_length and int(content_length) > MAX_URL_FILE_SIZE_MB * 1024 * 1024:
                    bot_logger.info(f"Command %addsound rejected: URL file too large ({content_length} bytes)")
                    await ctx.send(f"File is too large. Please keep it under {MAX_URL_FILE_SIZE_MB}MB.")
                    return
                
                with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1]) as temp_file:
                    temp_path = temp_file.name
                    for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                        if chunk:
                            temp_file.write(chunk)
                
            except requests.exceptions.RequestException as e:
                bot_logger.error(f"Command %addsound: Download error for '{name}': {e}")
                await ctx.send("Failed to download the file from the provided URL.")
                return
        
        # Convert to opus if needed
        if filename.endswith('.opus'):
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
                bot_logger.error(f"Command %addsound: ffmpeg conversion error for '{name}': {e.stderr.decode() if e.stderr else str(e)}")
                await ctx.send("Failed to convert the audio file to a compatible format.")
                if temp_path and os.path.exists(temp_path):
                    os.unlink(temp_path)
                return
        
        bot_logger.info(f"Command %addsound: Successfully added '{name}' to soundboard")
        await ctx.send(f"Sound '{name}' added to soundboard successfully!")
        # Regenerate special sounds in background
        bot_logger.info(f"Command %addsound: Triggering regeneration of cached special sounds")
        asyncio.ensure_future(soundboard_generator.regenerate_all_cached())
        
    except Exception as e:
        bot_logger.error(f"Command %addsound: Error processing '{name}': {e}")
        await ctx.send("An error occurred while processing the file.")
        # Clean up temp file if it exists
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)

@bot.command(name="listsounds", aliases=["ls"], help="List all available sounds in the soundboard. Usage: %listsounds or %ls")
async def list_sounds(ctx):
    channel_name = ctx.channel.name if ctx.channel else "DM"
    guild_name = ctx.guild.name if ctx.guild else "DM"
    bot_logger.info(f"Command: %listsounds | User: {ctx.author.name} ({ctx.author.id}) | Guild: {guild_name} | Channel: {channel_name}")
    
    try:
        available_sounds = soundboard_generator.get_real_sound_names()
    except Exception:
        bot_logger.warning(f"Command %listsounds: Soundboard directory not found")
        await ctx.send("Soundboard directory not found.")
        return
    
    if not available_sounds:
        bot_logger.info(f"Command %listsounds: No sounds available")
        await ctx.send("No sounds available in the soundboard.")
        return
    
    bot_logger.info(f"Command %listsounds: Returning {len(available_sounds)} sounds")
    sounds_list = ", ".join(available_sounds)
    await ctx.send(f"Available sounds: {sounds_list}\n*Special: all, seq*")

@bot.command(name="deletesound", aliases=["rmsound"], help="Delete a sound from the soundboard (admin only). Usage: %deletesound <sound_name> or %rmsound <sound_name>")
async def delete_sound(ctx, name: str):
    channel_name = ctx.channel.name if ctx.channel else "DM"
    guild_name = ctx.guild.name if ctx.guild else "DM"
    bot_logger.info(f"Command: %deletesound | User: {ctx.author.name} ({ctx.author.id}) | Guild: {guild_name} | Channel: {channel_name} | Sound: '{name}'")
    
    if not ctx.author.guild_permissions.administrator:
        bot_logger.warning(f"Command %deletesound rejected: User {ctx.author.name} lacks admin permissions")
        await ctx.send("You need administrator permissions to delete sounds.")
        return
    
    soundboard_dir = "soundboard"
    sound_path = os.path.join(soundboard_dir, f"{name}.opus")
    
    if not os.path.exists(sound_path):
        bot_logger.info(f"Command %deletesound: Sound '{name}' not found")
        await ctx.send(f"Sound '{name}' not found.")
        return
    
    try:
        os.remove(sound_path)
        bot_logger.info(f"Command %deletesound: Sound '{name}' deleted by {ctx.author.name}")
        await ctx.send(f"Sound '{name}' deleted successfully.")
        # Regenerate special sounds in background
        bot_logger.info(f"Command %deletesound: Triggering regeneration of cached special sounds")
        asyncio.ensure_future(soundboard_generator.regenerate_all_cached())
    except Exception as e:
        bot_logger.error(f"Command %deletesound: Error deleting '{name}': {e}")
        await ctx.send(f"An error occurred while deleting the sound: {e}")

@bot.command(name="setjoinsound", help="Set a sound to play when you join a voice channel. Usage: %setjoinsound <sound_name>")
async def set_join_sound(ctx, name: str = None):
    channel_name = ctx.channel.name if ctx.channel else "DM"
    guild_name = ctx.guild.name if ctx.guild else "DM"
    bot_logger.info(f"Command: %setjoinsound | User: {ctx.author.name} ({ctx.author.id}) | Guild: {guild_name} | Channel: {channel_name} | Sound: '{name}'")
    
    if not name:
        bot_logger.info(f"Command %setjoinsound rejected: No sound name provided")
        await ctx.send("Please provide a sound name. Usage: `%setjoinsound <sound_name>`")
        return
    
    try:
        available_sounds = soundboard_generator.get_real_sound_names()
    except Exception:
        bot_logger.warning(f"Command %setjoinsound: Soundboard directory not found")
        await ctx.send(f"Soundboard directory not found.")
        return
    
    if name not in available_sounds:
        bot_logger.info(f"Command %setjoinsound rejected: Invalid sound '{name}'")
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
    bot_logger.info(f"Command %setjoinsound: User {ctx.author.name} set join sound to '{name}'")
    await ctx.send(f"Your join sound has been set to '{name}'")

@bot.command(name="setleavesound", help="Set a sound to play when you leave a voice channel. Usage: %setleavesound <sound_name>")
async def set_leave_sound(ctx, name: str = None):
    channel_name = ctx.channel.name if ctx.channel else "DM"
    guild_name = ctx.guild.name if ctx.guild else "DM"
    bot_logger.info(f"Command: %setleavesound | User: {ctx.author.name} ({ctx.author.id}) | Guild: {guild_name} | Channel: {channel_name} | Sound: '{name}'")
    
    if not name:
        bot_logger.info(f"Command %setleavesound rejected: No sound name provided")
        await ctx.send("Please provide a sound name. Usage: `%setleavesound <sound_name>`")
        return
    
    try:
        available_sounds = soundboard_generator.get_real_sound_names()
    except Exception:
        bot_logger.warning(f"Command %setleavesound: Soundboard directory not found")
        await ctx.send(f"Soundboard directory not found.")
        return
    
    if name not in available_sounds:
        bot_logger.info(f"Command %setleavesound rejected: Invalid sound '{name}'")
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
    bot_logger.info(f"Command %setleavesound: User {ctx.author.name} set leave sound to '{name}'")
    await ctx.send(f"Your leave sound has been set to '{name}'")

@bot.command(name="unsetjoinsound", help="Remove your join sound. Usage: %unsetjoinsound")
async def unset_join_sound(ctx):
    channel_name = ctx.channel.name if ctx.channel else "DM"
    guild_name = ctx.guild.name if ctx.guild else "DM"
    bot_logger.info(f"Command: %unsetjoinsound | User: {ctx.author.name} ({ctx.author.id}) | Guild: {guild_name} | Channel: {channel_name}")
    
    user_id = str(ctx.author.id)
    if user_id in user_sounds and "join" in user_sounds[user_id]:
        old_sound = user_sounds[user_id]["join"]
        del user_sounds[user_id]["join"]
        save_user_sounds()
        bot_logger.info(f"Command %unsetjoinsound: User {ctx.author.name} removed join sound (was '{old_sound}')")
        await ctx.send("Your join sound has been removed.")
    else:
        bot_logger.info(f"Command %unsetjoinsound: User {ctx.author.name} has no join sound set")
        await ctx.send("You don't have a join sound set.")

@bot.command(name="unsetleavesound", help="Remove your leave sound. Usage: %unsetleavesound")
async def unset_leave_sound(ctx):
    channel_name = ctx.channel.name if ctx.channel else "DM"
    guild_name = ctx.guild.name if ctx.guild else "DM"
    bot_logger.info(f"Command: %unsetleavesound | User: {ctx.author.name} ({ctx.author.id}) | Guild: {guild_name} | Channel: {channel_name}")
    
    user_id = str(ctx.author.id)
    if user_id in user_sounds and "leave" in user_sounds[user_id]:
        old_sound = user_sounds[user_id]["leave"]
        del user_sounds[user_id]["leave"]
        save_user_sounds()
        bot_logger.info(f"Command %unsetleavesound: User {ctx.author.name} removed leave sound (was '{old_sound}')")
        await ctx.send("Your leave sound has been removed.")
    else:
        bot_logger.info(f"Command %unsetleavesound: User {ctx.author.name} has no leave sound set")
        await ctx.send("You don't have a leave sound set.")

@bot.command(name="mysounds", help="Check your current join and leave sounds. Usage: %mysounds")
async def my_sounds(ctx):
    channel_name = ctx.channel.name if ctx.channel else "DM"
    guild_name = ctx.guild.name if ctx.guild else "DM"
    bot_logger.info(f"Command: %mysounds | User: {ctx.author.name} ({ctx.author.id}) | Guild: {guild_name} | Channel: {channel_name}")
    
    user_id = str(ctx.author.id)
    if user_id in user_sounds:
        join_sound = user_sounds[user_id].get("join", "None")
        leave_sound = user_sounds[user_id].get("leave", "None")
        bot_logger.info(f"Command %mysounds: User {ctx.author.name} has join='{join_sound}', leave='{leave_sound}'")
        await ctx.send(f"Your sounds:\nJoin: {join_sound}\nLeave: {leave_sound}")
    else:
        bot_logger.info(f"Command %mysounds: User {ctx.author.name} has no sounds set")
        await ctx.send("You don't have any sounds set.")

@bot.command(name="replay", aliases=["repeat"], help="Replay the most recently played TTS sound file. Usage: %replay or %repeat")
async def replay(ctx):
    global voice_client, disconnect_timer, last_tts_file
    
    channel_name = ctx.channel.name if ctx.channel else "DM"
    guild_name = ctx.guild.name if ctx.guild else "DM"
    voice_channel_name = ctx.author.voice.channel.name if ctx.author.voice else "None"
    bot_logger.info(f"Command: %replay | User: {ctx.author.name} ({ctx.author.id}) | Guild: {guild_name} | Channel: {channel_name} | Voice: {voice_channel_name}")
    
    if not ctx.author.voice:
        bot_logger.info(f"Command %replay rejected: User {ctx.author.name} not in voice channel")
        await ctx.send("You are not connected to a voice channel.")
        return
    
    if args.no_tts:
        bot_logger.info(f"Command %replay rejected: TTS disabled")
        await ctx.send("Error: Bot currently has TTS disabled.")
        return
    
    if not last_tts_file or not os.path.exists(last_tts_file):
        bot_logger.info(f"Command %replay rejected: No TTS file available")
        await ctx.send("No TTS audio file has been played yet or the file is no longer available.")
        return
    
    try:
        if voice_client is None or not voice_client.is_connected():
            voice_channel = ctx.author.voice.channel
            bot_logger.info(f"Command %replay: Connecting to voice channel {voice_channel.name}")
            voice_client = await voice_channel.connect()

        # If there's a timer, cancel it
        if disconnect_timer:
            disconnect_timer.cancel()

        bot_logger.info(f"Command %replay: Playing file {last_tts_file}")
        source = await discord.FFmpegOpusAudio.from_probe(last_tts_file)
        voice_client.play(source)

        while voice_client.is_playing():
            await asyncio.sleep(1)

        # Start a new timer (10 minutes)
        loop = asyncio.get_event_loop()
        disconnect_timer = loop.call_later(VOICE_DISCONNECT_TIMEOUT_SECONDS, lambda: asyncio.ensure_future(disconnect_voice()))

        bot_logger.info(f"Command %replay: Successfully replayed TTS for {ctx.author.name}")
        await ctx.send("Replayed the most recent TTS audio.")

    except Exception as e:
        bot_logger.error(f"Command %replay: Error for {ctx.author.name}: {e}")
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
                # Cancel any existing disconnect timer before connecting
                # to prevent it firing during a slow connection
                if disconnect_timer:
                    disconnect_timer.cancel()
                    disconnect_timer = None
                
                # Connect to the channel if not already connected
                if voice_client is None or not voice_client.is_connected():
                    bot_logger.info(f"Connecting to voice channel {channel.name} to play user sound")
                    voice_client = await channel.connect()
                
                # Play the sound
                bot_logger.info(f"Now playing sound file: {filepath}")
                source = await discord.FFmpegOpusAudio.from_probe(filepath)
                voice_client.play(source)
                
                while voice_client.is_playing():
                    await asyncio.sleep(0.5)
                
                bot_logger.info(f"Finished playing '{sound_name}' for user {member.name}")
                
                # Set a new disconnect timer for 10 minutes (600 seconds)
                loop = asyncio.get_event_loop()
                disconnect_timer = loop.call_later(VOICE_DISCONNECT_TIMEOUT_SECONDS, lambda: asyncio.ensure_future(disconnect_voice()))
                
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
        # Wait before playing the join sound to ensure connection is established
        await asyncio.sleep(JOIN_SOUND_DELAY_SECONDS)
        await play_user_sound(member, after.channel, "join")
    
    # User left a voice channel
    elif before.channel is not None and after.channel is None:
        await play_user_sound(member, before.channel, "leave")

bot.run(DISCORD_TOKEN)
