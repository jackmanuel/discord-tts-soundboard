import asyncio
import hashlib
import os
import shutil
import tempfile

import requests

import soundboard_generator
from logger_config import bot_logger

from . import settings


async def download_sound_from_url(ctx, name, url, output_path):
    if not (url.startswith("http://") or url.startswith("https://")):
        bot_logger.info("Command %addsound rejected: Invalid URL format")
        await ctx.send("Invalid URL format. Please provide a valid HTTP or HTTPS URL.")
        return None, None

    is_video_site = any(domain in url.lower() for domain in [
        "youtube.com", "youtu.be", "soundcloud.com", "vimeo.com",
        "twitch.tv", "tiktok.com", "twitter.com", "x.com", "instagram.com",
    ])

    if is_video_site:
        return await _download_with_ytdlp(ctx, name, url, output_path)

    return await _download_direct_file(ctx, name, url)


async def _download_with_ytdlp(ctx, name, url, output_path):
    status_msg = await ctx.send("Fetching audio from link...")
    try:
        temp_base = os.path.join(tempfile.gettempdir(), f"ytdlp_{hashlib.md5(url.encode()).hexdigest()}")
        command = [
            "yt-dlp",
            "-x",
            "--audio-format",
            "opus",
            "--no-playlist",
            "--max-filesize",
            f"{settings.MAX_YTDLP_FILE_SIZE_MB}M",
            "--match-filter",
            f"duration < {settings.MAX_SOUND_DURATION_SECONDS}",
            "-o",
            f"{temp_base}.%(ext)s",
            url,
        ]

        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        combined_output = (stdout.decode() + "\n" + stderr.decode()).lower()

        expected_file = f"{temp_base}.opus"
        if process.returncode != 0 or not os.path.exists(expected_file):
            await _report_ytdlp_error(status_msg, name, url, process, stderr, combined_output)
            return None, None

        shutil.move(expected_file, output_path)
        bot_logger.info(f"Command %addsound: Successfully added '{name}' to soundboard (via yt-dlp)")
        await status_msg.edit(content=f"Sound '{name}' added to soundboard successfully!")
        bot_logger.info("Command %addsound: Triggering regeneration of cached special sounds")
        asyncio.ensure_future(soundboard_generator.regenerate_all_cached())
        return None, None
    except Exception as exc:
        bot_logger.error(f"Command %addsound: yt-dlp exception for '{name}': {exc}")
        await ctx.send("An unexpected error occurred while processing the link.")
        return None, None


async def _report_ytdlp_error(status_msg, name, url, process, stderr, combined_output):
    if "does not pass filter" in combined_output or "skipping" in combined_output:
        bot_logger.warning(f"Command %addsound: Failed for '{name}' - Video too long | URL: {url}")
        await status_msg.edit(
            content=f"Error: Audio is too long (max {settings.MAX_SOUND_DURATION_SECONDS} seconds)."
        )
    elif "larger than max-filesize" in combined_output:
        bot_logger.warning(f"Command %addsound: Failed for '{name}' - File too large | URL: {url}")
        await status_msg.edit(content=f"Error: File is too large (max {settings.MAX_YTDLP_FILE_SIZE_MB}MB).")
    else:
        if process.returncode != 0:
            bot_logger.error(f"Command %addsound: yt-dlp error (code {process.returncode}): {stderr.decode()}")
        else:
            bot_logger.error(f"Command %addsound: yt-dlp finished but file missing | Output: {combined_output}")
        await status_msg.edit(content="Error: Failed to process the provided link.")


async def _download_direct_file(ctx, name, url):
    url_lower = url.lower()
    if url_lower.endswith(".wav"):
        filename = "temp.wav"
    elif url_lower.endswith(".opus"):
        filename = "temp.opus"
    else:
        filename = "temp.mp3"

    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()

        content_length = response.headers.get("content-length")
        if content_length and int(content_length) > settings.MAX_URL_FILE_SIZE_MB * 1024 * 1024:
            bot_logger.info(f"Command %addsound rejected: URL file too large ({content_length} bytes)")
            await ctx.send(f"File is too large. Please keep it under {settings.MAX_URL_FILE_SIZE_MB}MB.")
            return None, None

        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1]) as temp_file:
            temp_path = temp_file.name
            for chunk in response.iter_content(chunk_size=settings.DOWNLOAD_CHUNK_SIZE):
                if chunk:
                    temp_file.write(chunk)
        return temp_path, filename
    except requests.exceptions.RequestException as exc:
        bot_logger.error(f"Command %addsound: Download error for '{name}': {exc}")
        await ctx.send("Failed to download the file from the provided URL.")
        return None, None
