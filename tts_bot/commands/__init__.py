from .soundboard import register_soundboard_commands
from .tts import register_tts_commands
from .user_sounds import register_user_sound_commands


def register_commands(bot, state, args):
    register_tts_commands(bot, state, args)
    register_soundboard_commands(bot, state)
    register_user_sound_commands(bot, state)
