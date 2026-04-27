# TTS Discord Bot

This is a Discord bot that uses Text-to-Speech to read messages in a voice channel. It uses Kokoro TTS for speech synthesis and integrates with an LLM via OpenRouter to provide interactive voice responses.

## Features

- **`%say <text>`**: Synthesizes speech from the provided text and plays it in the user's current voice channel.
- **`%ask <text>`**: Sends a query to an LLM via OpenRouter and speaks the response in the voice channel.
- **`%soundboard <sound_name>` or `%sb <sound_name>`**: Plays a pre-configured sound from the `soundboard` directory.
- **`%addsound <sound_name> [url]` or `%upload <sound_name> [url]`**: Uploads a new sound to the soundboard. You can either attach an audio file (.mp3, .wav, or .opus) to the command message, provide a direct URL to an audio file, or provide a YouTube/SoundCloud/other video site link (audio will be extracted automatically using yt-dlp).
- **`%listsounds` or `%ls`**: Lists all available sounds in the soundboard.
- **`%deletesound <sound_name>` or `%rmsound <sound_name>`**: Deletes a sound from the soundboard.
- **`%setjoinsound <sound_name>`**: Sets a sound to play when you join a voice channel.
- **`%setleavesound <sound_name>`**: Sets a sound to play when you leave a voice channel.
- **`%unsetjoinsound`**: Removes your join sound.
- **`%unsetleavesound`**: Removes your leave sound.
- **`%mysounds`**: Shows your current join and leave sounds.
- **`%stop`**: Stops the currently playing audio.
- **`%replay` or `%repeat`**: Replays the most recently played TTS audio file.
- **Join/Leave Sounds**: Users can set custom sounds that play when they join or leave voice channels.
- **Audio Caching**: Caches generated TTS audio files to provide instant responses for previously synthesized text.

## TTS Engine

The Text-to-Speech functionality of this bot is powered by [Kokoro](https://github.com/hexgrad/kokoro), a fast and lightweight TTS engine that runs directly as a Python library - no external server required.

## Setup

### Prerequisites

- Python 3.8+
- [FFmpeg](https://ffmpeg.org/) installed and available in your PATH
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) installed (for YouTube/SoundCloud support)
- A Discord bot token
- An OpenRouter API key (for the `%ask` command)

### Installation

1.  **Clone this repository:**
    ```bash
    git clone <repository_url>
    cd tts-bot-v2
    ```

2.  **Install the required Python packages:**
    ```bash
    pip install -r requirements.txt
    ```

### Configuration

1.  **Create a `.env` file** in the root directory of the project.

2.  **Add the following environment variables** to your `.env` file:

    ```
    DISCORD_TOKEN="your_discord_bot_token"
    OPENROUTER_API_KEY="your_openrouter_api_key"
    OPENROUTER_MODEL="openai/gpt-4o-mini"
    TTS_VOICE="af_bella"
    TTS_ACCENT="en-us"
    TTS_SPEED="1.0"
    DATA_DIR="data"
    
    # Logging configuration
    LOG_LEVEL="INFO"
    LOG_DIR="logs"
    LOG_RETENTION_DAYS="7"
    ```

    - `DISCORD_TOKEN`: Your unique Discord bot token.
    - `OPENROUTER_API_KEY`: Your API key for OpenRouter.
    - `OPENROUTER_MODEL`: The model to use for the `%ask` command (e.g., `openai/gpt-4o-mini`).
    - `TTS_VOICE`: The Kokoro voice to use for TTS. Defaults to `af_bella`.
    - `TTS_ACCENT`: The accent to use for TTS (`en-us` for American, `en-gb` for British). Defaults to `en-us`.
    - `TTS_SPEED`: The speed of the TTS playback. Defaults to `1.0`.
    - `DATA_DIR`: Directory for personal/runtime JSON files such as `user_map.json` and `user_sounds.json`. Defaults to `data`.
    - `LOG_LEVEL`: The logging level (DEBUG, INFO, WARNING, ERROR). Defaults to `INFO`.
    - `LOG_DIR`: Directory where log files will be stored. Defaults to `logs`.
    - `LOG_RETENTION_DAYS`: Number of days to keep log files before automatic cleanup. Defaults to `7`.

## Usage

1.  **Run the bot:**
    ```bash
    python bot.py
    ```

2.  **Run the bot without TTS (for testing soundboard features):**
    ```bash
    python bot.py --no-tts
    ```
    
    When running with the `--no-tts` flag, the Kokoro TTS pipeline will not be initialized and TTS-related commands (`%say` and `%ask`) will be disabled. Soundboard features will still work.

3.  **Invite the bot** to your Discord server.

4.  **Use the commands** in a text channel while connected to a voice channel.

## Project Structure

- `bot.py`: Small entrypoint that parses CLI flags and starts the bot.
- `tts_bot/app.py`: Bot construction, logging setup, TTS initialization, and background task startup.
- `tts_bot/audio.py`: Voice connection helpers, TTS cache generation, and audio queue worker.
- `tts_bot/events.py`: Discord event handlers.
- `tts_bot/commands/`: Discord command groups for TTS/LLM, soundboard, and join/leave sound preferences.
- `tts_bot/soundboard_uploads.py`: URL, yt-dlp, and direct-file download handling for soundboard uploads.
- `tts_bot/storage.py`: Runtime data loading/saving for personal JSON files.
- `data/`: Local personal/runtime JSON data. JSON files in this folder are ignored by Git.

### Soundboard Management

The bot includes a soundboard feature that allows you to upload, play, and manage custom sounds:

- **Uploading Sounds**: Use `%addsound <name> [url]` or `%upload <name> [url]` to add new sounds to the soundboard. You can either:
  - Attach an audio file (.mp3, .wav, or .opus) to the command message
  - Provide a direct URL to an audio file
  - Provide a link from supported video/audio platforms:
    - YouTube / YouTube Music
    - SoundCloud
    - Vimeo
    - Twitch
    - TikTok
    - Twitter / X
    - Instagram
  
  Audio will be extracted automatically using yt-dlp. Supported input formats are .mp3, .wav, and .opus. Files are automatically converted to .opus format for optimal performance. Maximum file size is 15MB and maximum duration is 10 minutes.
- **Playing Sounds**: Use `%soundboard <name>` or `%sb <name>` to play a sound from the soundboard.
- **Listing Sounds**: Use `%listsounds` or `%ls` to see all available sounds.
- **Deleting Sounds**: Use `%deletesound <name>` or `%rmsound <name>` to remove a sound (requires administrator permissions).

All sounds are stored in the `soundboard` directory in .opus format.

### Join/Leave Sounds

The bot supports custom join and leave sounds for each user:

- **Setting Sounds**: Use `%setjoinsound <name>` or `%setleavesound <name>` to set a sound that will play when you join or leave a voice channel.
- **Removing Sounds**: Use `%unsetjoinsound` or `%unsetleavesound` to remove your join or leave sound.
- **Checking Your Sounds**: Use `%mysounds` to see your currently configured join and leave sounds.

These settings are saved per user and will persist across bot restarts. The sounds are played automatically when you join or leave a voice channel.

Personal JSON data is stored in the `data/` directory by default. User sound preferences are written to `data/user_sounds.json`, and optional username mappings are read from `data/user_map.json`.

## Logging

The bot includes configurable logging with daily rotation. Logs are stored in the `logs/` directory and can be configured via the `LOG_LEVEL`, `LOG_DIR`, and `LOG_RETENTION_DAYS` environment variables in your `.env` file.
