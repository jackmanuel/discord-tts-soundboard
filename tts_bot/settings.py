import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / os.getenv("DATA_DIR", "data")
SOUNDBOARD_DIR = ROOT_DIR / "soundboard"
CACHE_DIR = ROOT_DIR / "audio_cache"

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL")
TTS_VOICE = os.getenv("TTS_VOICE", "af_bella")
TTS_ACCENT = os.getenv("TTS_ACCENT", "en-us")
TTS_SPEED = float(os.getenv("TTS_SPEED", 1.0))

EMPTY_CHANNEL_TIMEOUT_SECONDS = 60
TTS_SAMPLE_RATE = 24000

MAX_ATTACHMENT_SIZE_MB = 3
MAX_YTDLP_FILE_SIZE_MB = 15
MAX_SOUND_DURATION_SECONDS = 600
MAX_URL_FILE_SIZE_MB = 5
DOWNLOAD_CHUNK_SIZE = 8192
JOIN_SOUND_DELAY_SECONDS = 1
