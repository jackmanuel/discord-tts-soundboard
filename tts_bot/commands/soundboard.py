import asyncio
import os
import shutil
import subprocess
import tempfile

import discord

import soundboard_generator
from logger_config import bot_logger

from .. import settings
from ..soundboard_uploads import download_sound_from_url


def _format_sound_choices(available_sounds):
    if len(available_sounds) > 1:
        return ", ".join(available_sounds[:-1]) + f", or {available_sounds[-1]}"
    if available_sounds:
        return available_sounds[0]
    return ""


async def _play_generated_sound(ctx, state, name, duration_key, filepath):
    if state.voice_client is None or not state.voice_client.is_connected():
        voice_channel = ctx.author.voice.channel
        bot_logger.info(f"Command %soundboard: Connecting to voice channel '{voice_channel.name}'")
        state.voice_client = await voice_channel.connect()

    duration_display = "full" if duration_key == "full" else f"{duration_key}s"
    bot_logger.info(f"Command %soundboard: Playing '{name}' ({duration_display}) ({filepath})")

    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", filepath],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if probe.returncode == 0 and probe.stdout.strip():
            total_seconds = float(probe.stdout.strip())
            minutes = int(total_seconds) // 60
            seconds = int(total_seconds) % 60
            if minutes > 0:
                await ctx.send(f"Playing **{name}** ({duration_display}) - {minutes}m {seconds}s")
            else:
                await ctx.send(f"Playing **{name}** ({duration_display}) - {seconds}s")
    except Exception:
        pass

    source = await discord.FFmpegOpusAudio.from_probe(filepath)
    state.voice_client.play(source)

    while state.voice_client.is_playing():
        await asyncio.sleep(1)

    bot_logger.info(f"Command %soundboard: Finished playing '{name}' ({duration_display}) for {ctx.author.name}")


def _parse_special_duration(name, option):
    if name == "all":
        default_duration = soundboard_generator.DEFAULT_ALL_DURATION
        usage = "%sb all [seconds|full]"
    else:
        default_duration = soundboard_generator.DEFAULT_SEQ_DURATION
        usage = "%sb seq [seconds|full]"

    if option is None:
        return default_duration, None
    if option.lower() == "full":
        return "full", None

    try:
        duration_key = int(option)
    except ValueError:
        return None, f"Invalid option. Usage: `{usage}`"

    if duration_key < 1:
        return None, "Duration must be at least 1 second."
    return duration_key, None


def register_soundboard_commands(bot, state):
    @bot.command(name="soundboard", aliases=["sb"], help="Play a sound from the soundboard. Usage: %sb <sound_name> | %sb all [seconds|full] | %sb seq [seconds]")
    async def soundboard(ctx, name: str = None, option: str = None):
        if name:
            name = name.lower()
        channel_name = ctx.channel.name if ctx.channel else "DM"
        guild_name = ctx.guild.name if ctx.guild else "DM"
        voice_channel_name = ctx.author.voice.channel.name if ctx.author.voice else "None"
        bot_logger.info(
            f"Command: %soundboard | User: {ctx.author.name} ({ctx.author.id}) | Guild: {guild_name} | "
            f"Channel: {channel_name} | Voice: {voice_channel_name} | Sound: '{name}' | Option: '{option}'"
        )

        if not name:
            bot_logger.info("Command %soundboard rejected: No sound name provided")
            await ctx.send("Please provide a sound name. Usage: `%sb <sound_name>`")
            return
        if not ctx.author.voice:
            bot_logger.info(f"Command %soundboard rejected: User {ctx.author.name} not in voice channel")
            await ctx.send("You are not connected to a voice channel.")
            return

        if name in ("all", "seq"):
            duration_key, error = _parse_special_duration(name, option)
            if error:
                await ctx.send(error)
                return

            real_sounds = soundboard_generator.get_real_sound_names()
            if not real_sounds:
                await ctx.send("No sounds available to generate from.")
                return

            filepath, status_msg = await soundboard_generator.get_or_generate(name, duration_key, ctx)
            if not filepath:
                if not status_msg:
                    await ctx.send(f"Failed to generate {name} sound.")
                return

            try:
                await _play_generated_sound(ctx, state, name, duration_key, filepath)
            except Exception as exc:
                bot_logger.error(f"Command %soundboard: Error playing '{name}' for {ctx.author.name}: {exc}")
                await ctx.send(f"An error occurred: {exc}")
            return

        try:
            available_sounds = soundboard_generator.get_real_sound_names()
        except Exception:
            bot_logger.warning("Command %soundboard: Soundboard directory not found")
            await ctx.send("Soundboard directory not found.")
            return

        if name not in available_sounds:
            bot_logger.info(f"Command %soundboard rejected: Invalid sound '{name}'")
            display_sounds = available_sounds + ["all", "seq"]
            await ctx.send(f"Invalid sound. Choose from: {_format_sound_choices(display_sounds)}")
            return

        filepath = settings.SOUNDBOARD_DIR / f"{name}.opus"
        try:
            if state.voice_client is None or not state.voice_client.is_connected():
                voice_channel = ctx.author.voice.channel
                bot_logger.info(f"Command %soundboard: Connecting to voice channel '{voice_channel.name}'")
                state.voice_client = await voice_channel.connect()

            bot_logger.info(f"Command %soundboard: Playing '{name}' ({filepath})")
            source = await discord.FFmpegOpusAudio.from_probe(str(filepath))
            state.voice_client.play(source)

            while state.voice_client.is_playing():
                await asyncio.sleep(1)

            bot_logger.info(f"Command %soundboard: Finished playing '{name}' for {ctx.author.name}")
        except Exception as exc:
            bot_logger.error(f"Command %soundboard: Error playing '{name}' for {ctx.author.name}: {exc}")
            await ctx.send(f"An error occurred: {exc}")

    @bot.command(name="addsound", aliases=["upload"], help="Upload a new sound to the soundboard. Usage: %addsound <name> [url] or %upload <name> [url]. Supports YouTube and SoundCloud.")
    async def upload_sound(ctx, name: str = None, url: str = None):
        if name:
            name = name.lower()
        channel_name = ctx.channel.name if ctx.channel else "DM"
        guild_name = ctx.guild.name if ctx.guild else "DM"

        has_attachment = len(ctx.message.attachments) > 0
        has_url = url is not None
        source_info = f"URL: {url}" if has_url else (
            f"Attachment: {ctx.message.attachments[0].filename}" if has_attachment else "None"
        )
        bot_logger.info(
            f"Command: %addsound | User: {ctx.author.name} ({ctx.author.id}) | Guild: {guild_name} | "
            f"Channel: {channel_name} | Name: '{name}' | Source: {source_info}"
        )

        if not name:
            bot_logger.info("Command %addsound rejected: No sound name provided")
            await ctx.send("Please provide a name for the sound. Usage: `%addsound <name> [url]`")
            return

        settings.SOUNDBOARD_DIR.mkdir(parents=True, exist_ok=True)
        output_path = settings.SOUNDBOARD_DIR / f"{name}.opus"
        if output_path.exists():
            bot_logger.info(f"Command %addsound rejected: Sound '{name}' already exists")
            await ctx.send(f"A sound with the name '{name}' already exists.")
            return

        if not has_attachment and not has_url:
            bot_logger.info("Command %addsound rejected: No source provided")
            await ctx.send("Please either attach an audio file or provide a URL with your command.")
            return

        if has_attachment and has_url:
            bot_logger.info("Command %addsound rejected: Both attachment and URL provided")
            await ctx.send("Please provide either an attachment or a URL, not both.")
            return

        temp_path = None
        filename = None

        try:
            if has_attachment:
                attachment = ctx.message.attachments[0]
                if attachment.size > settings.MAX_ATTACHMENT_SIZE_MB * 1024 * 1024:
                    bot_logger.info(f"Command %addsound rejected: Attachment too large ({attachment.size} bytes)")
                    await ctx.send(f"File is too large. Please keep it under {settings.MAX_ATTACHMENT_SIZE_MB}MB.")
                    return

                filename = attachment.filename.lower()
                if not (filename.endswith(".mp3") or filename.endswith(".wav") or filename.endswith(".opus")):
                    bot_logger.info(f"Command %addsound rejected: Invalid file type '{filename}'")
                    await ctx.send("Invalid file type. Please upload .mp3, .wav, or .opus files only.")
                    return

                with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1]) as temp_file:
                    await attachment.save(temp_file.name)
                    temp_path = temp_file.name
            else:
                temp_path, filename = await download_sound_from_url(ctx, name, url, output_path)
                if temp_path is None and filename is None:
                    return

            if filename.endswith(".opus"):
                shutil.move(temp_path, output_path)
            else:
                command = ["ffmpeg", "-i", temp_path, "-c:a", "libopus", str(output_path)]
                subprocess.run(command, check=True, capture_output=True)
                if temp_path:
                    os.unlink(temp_path)

            bot_logger.info(f"Command %addsound: Successfully added '{name}' to soundboard")
            await ctx.send(f"Sound '{name}' added to soundboard successfully!")
            bot_logger.info("Command %addsound: Triggering regeneration of cached special sounds")
            asyncio.ensure_future(soundboard_generator.regenerate_all_cached())
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.decode() if exc.stderr else str(exc)
            bot_logger.error(f"Command %addsound: ffmpeg conversion error for '{name}': {stderr}")
            await ctx.send("Failed to convert the audio file to a compatible format.")
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)
        except Exception as exc:
            bot_logger.error(f"Command %addsound: Error processing '{name}': {exc}")
            await ctx.send("An error occurred while processing the file.")
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)

    @bot.command(name="listsounds", aliases=["ls"], help="List all available sounds in the soundboard. Usage: %listsounds or %ls")
    async def list_sounds(ctx):
        channel_name = ctx.channel.name if ctx.channel else "DM"
        guild_name = ctx.guild.name if ctx.guild else "DM"
        bot_logger.info(
            f"Command: %listsounds | User: {ctx.author.name} ({ctx.author.id}) | "
            f"Guild: {guild_name} | Channel: {channel_name}"
        )

        try:
            available_sounds = soundboard_generator.get_real_sound_names()
        except Exception:
            bot_logger.warning("Command %listsounds: Soundboard directory not found")
            await ctx.send("Soundboard directory not found.")
            return

        if not available_sounds:
            bot_logger.info("Command %listsounds: No sounds available")
            await ctx.send("No sounds available in the soundboard.")
            return

        bot_logger.info(f"Command %listsounds: Returning {len(available_sounds)} sounds")
        await ctx.send(f"Available sounds: {', '.join(available_sounds)}\n*Special: all, seq*")

    @bot.command(name="deletesound", aliases=["rmsound"], help="Delete a sound from the soundboard (admin only). Usage: %deletesound <sound_name> or %rmsound <sound_name>")
    async def delete_sound(ctx, name: str):
        if name:
            name = name.lower()
        channel_name = ctx.channel.name if ctx.channel else "DM"
        guild_name = ctx.guild.name if ctx.guild else "DM"
        bot_logger.info(
            f"Command: %deletesound | User: {ctx.author.name} ({ctx.author.id}) | Guild: {guild_name} | "
            f"Channel: {channel_name} | Sound: '{name}'"
        )

        if not ctx.author.guild_permissions.administrator:
            bot_logger.warning(f"Command %deletesound rejected: User {ctx.author.name} lacks admin permissions")
            await ctx.send("You need administrator permissions to delete sounds.")
            return

        sound_path = settings.SOUNDBOARD_DIR / f"{name}.opus"
        if not sound_path.exists():
            bot_logger.info(f"Command %deletesound: Sound '{name}' not found")
            await ctx.send(f"Sound '{name}' not found.")
            return

        try:
            os.remove(sound_path)
            bot_logger.info(f"Command %deletesound: Sound '{name}' deleted by {ctx.author.name}")
            await ctx.send(f"Sound '{name}' deleted successfully.")
            bot_logger.info("Command %deletesound: Triggering regeneration of cached special sounds")
            asyncio.ensure_future(soundboard_generator.regenerate_all_cached())
        except Exception as exc:
            bot_logger.error(f"Command %deletesound: Error deleting '{name}': {exc}")
            await ctx.send(f"An error occurred while deleting the sound: {exc}")
