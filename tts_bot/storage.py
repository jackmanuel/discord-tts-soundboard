import json
from pathlib import Path

from logger_config import bot_logger

from . import settings


USER_SOUNDS_FILE = settings.DATA_DIR / "user_sounds.json"
USER_MAP_FILE = settings.DATA_DIR / "user_map.json"
SYSTEM_PROMPT_FILE = settings.ROOT_DIR / "system_prompt.txt"


def ensure_data_dir():
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_json(path: Path, default):
    try:
        if path.exists():
            with path.open("r", encoding="utf-8") as file:
                return json.load(file)
    except Exception as exc:
        bot_logger.error(f"Error loading {path.name}: {exc}")
    return default


def load_user_sounds():
    ensure_data_dir()
    return _load_json(USER_SOUNDS_FILE, {})


def save_user_sounds(user_sounds):
    ensure_data_dir()
    try:
        with USER_SOUNDS_FILE.open("w", encoding="utf-8") as file:
            json.dump(user_sounds, file)
    except Exception as exc:
        bot_logger.error(f"Error saving user sounds: {exc}")


def load_user_map():
    return _load_json(USER_MAP_FILE, {})


def load_system_prompt():
    if not SYSTEM_PROMPT_FILE.exists():
        bot_logger.warning("system_prompt.txt not found. Proceeding with an empty system prompt.")
        return ""

    with SYSTEM_PROMPT_FILE.open("r", encoding="utf-8") as file:
        return file.read()
