# Discord Audio Bot

A Discord audio bot with soundboard, text-to-speech, and LLM voice response features.

The bot combines two main workflows: a shared soundboard for playing and managing clips, and TTS commands for spoken messages or LLM responses in voice channels. Either side can be useful on its own, and soundboard features can still run without loading the TTS pipeline by starting the bot with `--no-tts`.

## Features

- Play and manage saved sounds from the `soundboard/` directory.
- Upload clips from attachments, direct audio URLs, YouTube, SoundCloud, and other supported media links.
- Generate special mixed soundboard clips with `%sb all` and `%sb seq`.
- Convert text to speech with Kokoro.
- Ask an LLM through OpenRouter and speak the response in a voice channel.
- Set custom join and leave sounds per user.

See [docs/commands.md](docs/commands.md) for the full command reference.

## Requirements

- Python 3.8+
- [FFmpeg](https://ffmpeg.org/) available in your `PATH`
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) available in your `PATH` for media-link uploads
- A Discord bot token
- An OpenRouter API key if you want to use `%ask`

## Setup

1. Clone the repository and install dependencies:

   ```bash
   git clone <repository_url>
   cd tts-bot-v2
   pip install -r requirements.txt
   ```

2. Create a `.env` file in the project root:

   ```env
   DISCORD_TOKEN="your_discord_bot_token"

   # Optional, only needed for %ask.
   OPENROUTER_API_KEY="your_openrouter_api_key"
   OPENROUTER_MODEL="your_openrouter_model"

   # Optional TTS settings.
   TTS_VOICE="af_bella"
   TTS_ACCENT="en-us"
   TTS_SPEED="1.0"

   # Optional local data and logging settings.
   DATA_DIR="data"
   LOG_LEVEL="INFO"
   LOG_DIR="logs"
   LOG_RETENTION_DAYS="7"
   ```

3. Invite the bot to your Discord server and make sure it has message and voice permissions.

## Running

Run the full bot:

```bash
python bot.py
```

Run soundboard-only mode:

```bash
python bot.py --no-tts
```

Soundboard-only mode skips Kokoro TTS initialisation and disables `%say`, `%ask`, and `%replay`. Soundboard playback, uploads, lists, deletes, and join/leave sounds still work.

## Local Data

Uploaded sounds are stored as `.opus` files in `soundboard/`.

Runtime user data is stored in `data/` by default:

- `data/user_sounds.json` stores join and leave sound preferences.
- `data/user_map.json`, if present, can provide friendly names for LLM prompts.

Logs are written to `logs/` by default with daily rotation.
