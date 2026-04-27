import asyncio

import discord

from logger_config import bot_logger

from . import settings


async def play_user_sound(member, channel, sound_type, state):
    user_id = str(member.id)
    if user_id not in state.user_sounds or sound_type not in state.user_sounds[user_id]:
        return

    sound_name = state.user_sounds[user_id][sound_type]
    filepath = settings.SOUNDBOARD_DIR / f"{sound_name}.opus"
    action = "joining" if sound_type == "join" else "leaving"
    bot_logger.info(
        f"Playing '{sound_name}' for user {member.name} ({user_id}) "
        f"{action} voice channel '{channel.name}'"
    )

    if not filepath.exists():
        bot_logger.warning(f"Sound file not found: {filepath}")
        return

    try:
        if state.voice_client is None or not state.voice_client.is_connected():
            bot_logger.info(f"Connecting to voice channel {channel.name} to play user sound")
            state.voice_client = await channel.connect()

        bot_logger.info(f"Now playing sound file: {filepath}")
        source = await discord.FFmpegOpusAudio.from_probe(str(filepath))
        state.voice_client.play(source)

        while state.voice_client.is_playing():
            await asyncio.sleep(0.5)

        bot_logger.info(f"Finished playing '{sound_name}' for user {member.name}")
    except Exception as exc:
        bot_logger.error(f"Error playing user sound: {exc}")
