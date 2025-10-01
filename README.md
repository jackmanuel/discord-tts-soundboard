# TTS Discord Bot

This is a Discord bot that uses Text-to-Speech to read messages in a voice channel. It integrates with a TTS server and an LLM to provide interactive voice responses.

## Features

- **`%say <text>`**: Synthesizes speech from the provided text and plays it in the user's current voice channel.
- **`%ask <text>`**: Sends a query to an LLM via OpenRouter and speaks the response in the voice channel.
- **`%soundboard <sound_name>` or `%sb <sound_name>`**: Plays a pre-configured sound from the `soundboard` directory.
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
    ```

    - `DISCORD_TOKEN`: Your unique Discord bot token.
    - `OPENROUTER_API_KEY`: Your API key for OpenRouter.
    - `UVICORN_PATH`: The absolute path to the `uvicorn.exe` executable within your OpenVoice server's Python virtual environment.
    - `SERVER_DIR`: The absolute path to the root directory of your OpenVoice server installation.
    - `OPENROUTER_MODEL`: The model to use for the `ask` command.
    - `TTS_VOICE`: The voice to use for TTS. Defaults to `demo_speaker0`.
    - `TTS_ACCENT`: The accent to use for TTS. Defaults to `en-us`.
    - `TTS_SPEED`: The speed of the TTS. Defaults to `1.0`.

## Usage

1.  **Run the bot:**
    ```bash
    python bot.py
    ```

2.  **Invite the bot** to your Discord server.

3.  **Use the commands** in a text channel while connected to a voice channel.
