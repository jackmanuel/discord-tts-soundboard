# Command Reference

The bot uses `%` as its command prefix. Most playback commands require you to be connected to a voice channel.

## Soundboard

| Command | Description |
| --- | --- |
| `%sb <sound_name>` or `%soundboard <sound_name>` | Plays a saved sound. |
| `%sb all [seconds\|full]` | Plays a generated clip using all available sounds. |
| `%sb seq [seconds\|full]` | Plays a generated sequence of available sounds. |
| `%listsounds` or `%ls` | Lists saved sounds, plus the special `all` and `seq` modes. |
| `%addsound <name> [url]` or `%upload <name> [url]` | Adds a sound from an attachment or URL. |
| `%deletesound <name>` or `%rmsound <name>` | Deletes a sound. Requires administrator permissions. |
| `%stop` or `%skip` | Stops the currently playing audio. |

### Upload Sources

`%addsound` accepts one source at a time:

- An attached `.mp3`, `.wav`, or `.opus` file.
- A direct HTTP or HTTPS audio URL.
- A supported media link, including YouTube, YouTube Music, SoundCloud, Vimeo, Twitch, TikTok, Twitter/X, and Instagram.

Uploaded sounds are converted to `.opus` and saved in `soundboard/`.

Current limits:

- Discord attachment uploads: 3 MB.
- Direct audio URLs: 5 MB.
- yt-dlp media links: 15 MB and under 10 minutes.

## Join And Leave Sounds

| Command | Description |
| --- | --- |
| `%setjoinsound <sound_name>` | Plays that sound when you join a voice channel. |
| `%setleavesound <sound_name>` | Plays that sound when you leave a voice channel. |
| `%unsetjoinsound` | Removes your join sound. |
| `%unsetleavesound` | Removes your leave sound. |
| `%mysounds` | Shows your current join and leave sounds. |

Join and leave sound settings are saved per user in `data/user_sounds.json`.

## TTS And LLM Commands

These commands are disabled when the bot is started with `--no-tts`.

| Command | Description |
| --- | --- |
| `%say <text>` | Converts text to speech and plays it in your voice channel. |
| `%ask <text>` | Sends text to OpenRouter, then speaks the response. |
| `%replay` or `%repeat` | Replays the most recent TTS audio file. |

Kokoro powers local TTS. `%ask` also requires `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` in `.env`.
