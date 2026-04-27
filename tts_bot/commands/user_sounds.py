import soundboard_generator
from logger_config import bot_logger

from ..storage import save_user_sounds


def _format_sound_choices(available_sounds):
    if len(available_sounds) > 1:
        return ", ".join(available_sounds[:-1]) + f", or {available_sounds[-1]}"
    if available_sounds:
        return available_sounds[0]
    return ""


def register_user_sound_commands(bot, state):
    @bot.command(name="setjoinsound", help="Set a sound to play when you join a voice channel. Usage: %setjoinsound <sound_name>")
    async def set_join_sound(ctx, name: str = None):
        await _set_user_sound(ctx, name, "join", state)

    @bot.command(name="setleavesound", help="Set a sound to play when you leave a voice channel. Usage: %setleavesound <sound_name>")
    async def set_leave_sound(ctx, name: str = None):
        await _set_user_sound(ctx, name, "leave", state)

    @bot.command(name="unsetjoinsound", help="Remove your join sound. Usage: %unsetjoinsound")
    async def unset_join_sound(ctx):
        await _unset_user_sound(ctx, "join", state)

    @bot.command(name="unsetleavesound", help="Remove your leave sound. Usage: %unsetleavesound")
    async def unset_leave_sound(ctx):
        await _unset_user_sound(ctx, "leave", state)

    @bot.command(name="mysounds", help="Check your current join and leave sounds. Usage: %mysounds")
    async def my_sounds(ctx):
        channel_name = ctx.channel.name if ctx.channel else "DM"
        guild_name = ctx.guild.name if ctx.guild else "DM"
        bot_logger.info(
            f"Command: %mysounds | User: {ctx.author.name} ({ctx.author.id}) | "
            f"Guild: {guild_name} | Channel: {channel_name}"
        )

        user_id = str(ctx.author.id)
        if user_id in state.user_sounds:
            join_sound = state.user_sounds[user_id].get("join", "None")
            leave_sound = state.user_sounds[user_id].get("leave", "None")
            bot_logger.info(
                f"Command %mysounds: User {ctx.author.name} has join='{join_sound}', leave='{leave_sound}'"
            )
            await ctx.send(f"Your sounds:\nJoin: {join_sound}\nLeave: {leave_sound}")
        else:
            bot_logger.info(f"Command %mysounds: User {ctx.author.name} has no sounds set")
            await ctx.send("You don't have any sounds set.")


async def _set_user_sound(ctx, name, sound_type, state):
    if name:
        name = name.lower()
    channel_name = ctx.channel.name if ctx.channel else "DM"
    guild_name = ctx.guild.name if ctx.guild else "DM"
    command_name = "setjoinsound" if sound_type == "join" else "setleavesound"
    bot_logger.info(
        f"Command: %{command_name} | User: {ctx.author.name} ({ctx.author.id}) | "
        f"Guild: {guild_name} | Channel: {channel_name} | Sound: '{name}'"
    )

    if not name:
        bot_logger.info(f"Command %{command_name} rejected: No sound name provided")
        await ctx.send(f"Please provide a sound name. Usage: `%{command_name} <sound_name>`")
        return

    try:
        available_sounds = soundboard_generator.get_real_sound_names()
    except Exception:
        bot_logger.warning(f"Command %{command_name}: Soundboard directory not found")
        await ctx.send("Soundboard directory not found.")
        return

    if name not in available_sounds:
        bot_logger.info(f"Command %{command_name} rejected: Invalid sound '{name}'")
        await ctx.send(f"Invalid sound. Choose from: {_format_sound_choices(available_sounds)}")
        return

    user_id = str(ctx.author.id)
    if user_id not in state.user_sounds:
        state.user_sounds[user_id] = {}

    state.user_sounds[user_id][sound_type] = name
    save_user_sounds(state.user_sounds)
    bot_logger.info(f"Command %{command_name}: User {ctx.author.name} set {sound_type} sound to '{name}'")
    await ctx.send(f"Your {sound_type} sound has been set to '{name}'")


async def _unset_user_sound(ctx, sound_type, state):
    channel_name = ctx.channel.name if ctx.channel else "DM"
    guild_name = ctx.guild.name if ctx.guild else "DM"
    command_name = "unsetjoinsound" if sound_type == "join" else "unsetleavesound"
    bot_logger.info(
        f"Command: %{command_name} | User: {ctx.author.name} ({ctx.author.id}) | "
        f"Guild: {guild_name} | Channel: {channel_name}"
    )

    user_id = str(ctx.author.id)
    if user_id in state.user_sounds and sound_type in state.user_sounds[user_id]:
        old_sound = state.user_sounds[user_id][sound_type]
        del state.user_sounds[user_id][sound_type]
        save_user_sounds(state.user_sounds)
        bot_logger.info(
            f"Command %{command_name}: User {ctx.author.name} removed {sound_type} sound "
            f"(was '{old_sound}')"
        )
        await ctx.send(f"Your {sound_type} sound has been removed.")
    else:
        bot_logger.info(f"Command %{command_name}: User {ctx.author.name} has no {sound_type} sound set")
        await ctx.send(f"You don't have a {sound_type} sound set.")
