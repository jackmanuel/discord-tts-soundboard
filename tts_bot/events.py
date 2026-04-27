import asyncio

from logger_config import bot_logger

from . import settings
from .audio import empty_channel_timeout
from .user_sounds import play_user_sound


def register_events(bot, state, args, initialize_tts, start_background_tasks):
    @bot.event
    async def on_ready():
        bot_logger.info(f"Logged in as {bot.user.name}")
        await initialize_tts(state, args)
        start_background_tasks(bot, state)

    @bot.event
    async def on_voice_state_update(member, before, after):
        if state.voice_client and state.voice_client.is_connected():
            bot_channel = state.voice_client.channel
            if (before.channel and before.channel.id == bot_channel.id) or (
                after.channel and after.channel.id == bot_channel.id
            ):
                non_bot_members = [voice_member for voice_member in bot_channel.members if not voice_member.bot]
                if not non_bot_members:
                    if state.disconnect_task is None or state.disconnect_task.done():
                        state.disconnect_task = bot.loop.create_task(empty_channel_timeout(state))
                        bot_logger.info(
                            f"Channel '{bot_channel.name}' became empty. Starting "
                            f"{settings.EMPTY_CHANNEL_TIMEOUT_SECONDS}s disconnect timer."
                        )
                elif state.disconnect_task and not state.disconnect_task.done():
                    state.disconnect_task.cancel()
                    state.disconnect_task = None
                    bot_logger.info(
                        f"User joined voice channel '{bot_channel.name}'. Cancelled disconnect timer."
                    )

        if member.bot:
            return

        if before.channel is None and after.channel is not None:
            await asyncio.sleep(settings.JOIN_SOUND_DELAY_SECONDS)
            await play_user_sound(member, after.channel, "join", state)
        elif before.channel is not None and after.channel is None:
            await play_user_sound(member, before.channel, "leave", state)
