import argparse
import logging
import logging.handlers

import discord
from discord.ext import commands
from dotenv import load_dotenv
from kokoro import KPipeline

from logger_config import bot_logger

from . import settings
from .audio import audio_worker
from .commands import register_commands
from .events import register_events
from .state import BotState
from .storage import load_user_sounds


def parse_args():
    parser = argparse.ArgumentParser(description="TTS Discord Bot")
    parser.add_argument(
        "--no-tts",
        action="store_true",
        help="Run the bot without starting the TTS server",
    )
    return parser.parse_args()


def configure_discord_logging():
    load_dotenv()
    discord_logger = logging.getLogger("discord")
    discord_logger.setLevel(logging.INFO)

    if bot_logger.handlers:
        for handler in bot_logger.handlers:
            if isinstance(handler, logging.handlers.TimedRotatingFileHandler):
                discord_logger.addHandler(handler)
                discord_logger.propagate = False


def create_bot(args):
    configure_discord_logging()

    intents = discord.Intents.default()
    intents.message_content = True
    intents.voice_states = True

    bot = commands.Bot(command_prefix="%", intents=intents)
    state = BotState()

    register_events(bot, state, args, initialize_tts, start_background_tasks)
    register_commands(bot, state, args)

    return bot, settings


async def initialize_tts(state, args):
    if args.no_tts:
        bot_logger.info("Running without TTS (no-tts mode enabled)")
        return

    try:
        bot_logger.info("Initializing Kokoro TTS pipeline...")
        lang_code = "a"
        if settings.TTS_ACCENT and "gb" in settings.TTS_ACCENT.lower():
            lang_code = "b"

        state.pipeline = KPipeline(lang_code=lang_code, repo_id=settings.TTS_REPO_ID)
        bot_logger.info(f"Kokoro TTS pipeline initialized (lang={lang_code}).")
    except Exception as exc:
        bot_logger.error(f"Failed to initialize Kokoro TTS: {exc}")
        bot_logger.warning("TTS functionality will be disabled.")
        args.no_tts = True


def start_background_tasks(bot, state):
    settings.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    state.user_sounds = load_user_sounds()
    bot.loop.create_task(audio_worker(state))
