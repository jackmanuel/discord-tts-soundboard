# TTS Discord Bot

This is a Discord bot that uses Text-to-Speech to read messages in a voice channel. It integrates with a TTS server and an LLM to provide interactive voice responses.

## Features

- **`%say <text>`**: Synthesizes speech from the provided text and plays it in the user's current voice channel.
- **`%ask <text>`**: Sends a query to an LLM via OpenRouter and speaks the response in the voice channel.
- **`%soundboard <sound_name>` or `%sb <sound_name>`**: Plays a pre-configured sound from the `soundboard` directory.
- **`%addsound <sound_name> [url]` or `%upload <sound_name> [url]`**: Uploads a new sound to the soundboard. You can either attach an audio file (.mp3, .wav, or .opus) to the command message or provide a URL to an audio file.
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
- **Automatic Server Startup**: Checks if the required TTS server is running and starts it automatically if it's not detected.

## TTS Server

The Text-to-Speech functionality of this bot is powered by [OpenVoice](https://github.com/myshell-ai/OpenVoice) by myshell-ai.

The bot is configured to automatically start the OpenVoice server on `http://0.0.0.0:8080` if it's not already running. For this to work, you must have OpenVoice set up correctly on your machine and provide the necessary paths in the `.env` file.

## Setup

### Prerequisites

- Python 3.8+
- A local clone of the [OpenVoice](https://github.com/myshell-ai/OpenVoice) repository.
- A Discord bot token.
- An OpenRouter API key.

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
    UVICORN_PATH="C:\\path\\to\\your\\OpenVoice_server\\.venv\\Scripts\\uvicorn.exe"
    SERVER_DIR="C:\\path\\to\\your\\OpenVoice_server"
    OPENROUTER_MODEL="lab/model-name"
    TTS_VOICE="demo_speaker0"
    TTS_ACCENT="en-us"
    TTS_SPEED="1.0"
    
    # Logging configuration
    LOG_LEVEL="INFO"
    LOG_DIR="logs"
    LOG_RETENTION_DAYS="7"
    ```

    - `DISCORD_TOKEN`: Your unique Discord bot token.
    - `OPENROUTER_API_KEY`: Your API key for OpenRouter.
    - `UVICORN_PATH`: The absolute path to the `uvicorn.exe` executable within your OpenVoice server's Python virtual environment.
    - `SERVER_DIR`: The absolute path to the root directory of your OpenVoice server installation.
    - `OPENROUTER_MODEL`: The model to use for the `ask` command.
    - `TTS_VOICE`: The voice to use for TTS. Defaults to `demo_speaker0`.
    - `TTS_ACCENT`: The accent to use for TTS. Defaults to `en-us`.
    - `TTS_SPEED`: The speed of the TTS. Defaults to `1.0`.
    - `LOG_LEVEL`: The logging level (DEBUG, INFO, WARNING, ERROR). Defaults to `INFO`.
    - `LOG_DIR`: Directory where log files will be stored. Defaults to `logs`.
    - `LOG_RETENTION_DAYS`: Number of days to keep log files. Defaults to `7`.

## Usage

1.  **Run the bot:**
    ```bash
    python bot.py
    ```

2.  **Run the bot without starting the TTS server (for testing):**
    ```bash
    python bot.py --no-tts
    ```
    
    When running with the `--no-tts` flag, the bot will not attempt to start the TTS server and TTS-related commands (`%say` and `%ask`) will be disabled.

3.  **Invite the bot** to your Discord server.

4.  **Use the commands** in a text channel while connected to a voice channel.

### Soundboard Management

The bot includes a soundboard feature that allows you to upload, play, and manage custom sounds:

- **Uploading Sounds**: Use `%addsound <name> [url]` or `%upload <name> [url]` to add new sounds to the soundboard. You can either:
  - Attach an audio file (.mp3, .wav, or .opus) to the command message
  - Provide a URL to an audio file as an additional parameter
  
  Supported formats are .mp3, .wav, and .opus. Files are automatically converted to .opus format for optimal performance. Maximum file size is 3MB.
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

## Logging

The bot includes configurable logging with daily rotation. Logs are stored in the `logs/` directory and can be configured via the `LOG_LEVEL`, `LOG_DIR`, and `LOG_RETENTION_DAYS` environment variables in your `.env` file.
