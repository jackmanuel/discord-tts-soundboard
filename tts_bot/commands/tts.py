import os
import asyncio

import discord
import requests

from logger_config import bot_logger

from ..audio import ensure_voice_connected
from ..llm import LLMConfigurationError, ask_llm
from ..storage import load_system_prompt, load_user_map


def register_tts_commands(bot, state, args):
    @bot.command(name="ask", help="Ask a question to the LLM and get a spoken response. Usage: %ask <your question>")
    async def ask(ctx, *, text: str):
        channel_name = ctx.channel.name if ctx.channel else "DM"
        guild_name = ctx.guild.name if ctx.guild else "DM"
        bot_logger.info(
            f"Command: %ask | User: {ctx.author.name} ({ctx.author.id}) | "
            f"Guild: {guild_name} | Channel: {channel_name} | Text: '{text}'"
        )

        if not ctx.author.voice:
            bot_logger.info(f"Command %ask rejected: User {ctx.author.name} not in voice channel")
            await ctx.send("You are not connected to a voice channel.")
            return

        if args.no_tts:
            bot_logger.info("Command %ask rejected: TTS disabled")
            await ctx.send("Error: Bot currently has TTS disabled.")
            return

        system_prompt = load_system_prompt()
        user_map = load_user_map()
        author_name = ctx.author.name
        if author_name in user_map:
            system_prompt += f"\n\nThe user making this request is: {user_map[author_name]}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ]

        try:
            llm_response = ask_llm(messages)
            await state.request_queue.put((ctx, llm_response))
            await ctx.send(f"Sent to LLM: '{text}'")
        except LLMConfigurationError as exc:
            await ctx.send(f"LLM configuration error: {exc}")
        except requests.exceptions.RequestException as exc:
            await ctx.send(f"Error contacting LLM API: {exc}")
        except Exception as exc:
            await ctx.send(f"An error occurred: {exc}")

    @bot.command(name="say", help="Convert text to speech and play it in the voice channel. Usage: %say <text>")
    async def say(ctx, *, text: str):
        channel_name = ctx.channel.name if ctx.channel else "DM"
        guild_name = ctx.guild.name if ctx.guild else "DM"
        voice_channel = ctx.author.voice.channel.name if ctx.author.voice else "None"
        bot_logger.info(
            f"Command: %say | User: {ctx.author.name} ({ctx.author.id}) | Guild: {guild_name} | "
            f"Channel: {channel_name} | Voice: {voice_channel} | Text: '{text}'"
        )

        if not ctx.author.voice:
            bot_logger.info(f"Command %say rejected: User {ctx.author.name} not in voice channel")
            await ctx.send("You are not connected to a voice channel.")
            return

        if args.no_tts:
            bot_logger.info("Command %say rejected: TTS disabled")
            await ctx.send("Error: Bot currently has TTS disabled.")
            return

        await state.request_queue.put((ctx, text))
        bot_logger.info(f"Command %say: Added to queue for user {ctx.author.name}")
        await ctx.send(f"Added to queue: '{text}'")

    @bot.command(name="stop", aliases=["skip"], help="Stop the currently playing audio. Usage: %stop")
    async def stop(ctx):
        channel_name = ctx.channel.name if ctx.channel else "DM"
        guild_name = ctx.guild.name if ctx.guild else "DM"
        bot_logger.info(
            f"Command: %stop | User: {ctx.author.name} ({ctx.author.id}) | "
            f"Guild: {guild_name} | Channel: {channel_name}"
        )

        if state.voice_client and state.voice_client.is_connected() and state.voice_client.is_playing():
            state.voice_client.stop()
            bot_logger.info(f"Command %stop: Audio stopped by {ctx.author.name}")
            await ctx.send("Audio stopped.")
        else:
            bot_logger.info("Command %stop: No audio playing")
            await ctx.send("No audio is currently playing.")

    @bot.command(name="replay", aliases=["repeat"], help="Replay the most recently played TTS sound file. Usage: %replay or %repeat")
    async def replay(ctx):
        channel_name = ctx.channel.name if ctx.channel else "DM"
        guild_name = ctx.guild.name if ctx.guild else "DM"
        voice_channel_name = ctx.author.voice.channel.name if ctx.author.voice else "None"
        bot_logger.info(
            f"Command: %replay | User: {ctx.author.name} ({ctx.author.id}) | Guild: {guild_name} | "
            f"Channel: {channel_name} | Voice: {voice_channel_name}"
        )

        if not ctx.author.voice:
            bot_logger.info(f"Command %replay rejected: User {ctx.author.name} not in voice channel")
            await ctx.send("You are not connected to a voice channel.")
            return

        if args.no_tts:
            bot_logger.info("Command %replay rejected: TTS disabled")
            await ctx.send("Error: Bot currently has TTS disabled.")
            return

        if not state.last_tts_file or not os.path.exists(state.last_tts_file):
            bot_logger.info("Command %replay rejected: No TTS file available")
            await ctx.send("No TTS audio file has been played yet or the file is no longer available.")
            return

        try:
            voice_client = await ensure_voice_connected(ctx, state)
            bot_logger.info(f"Command %replay: Playing file {state.last_tts_file}")
            source = await discord.FFmpegOpusAudio.from_probe(state.last_tts_file)
            voice_client.play(source)

            while voice_client.is_playing():
                await asyncio.sleep(1)

            bot_logger.info(f"Command %replay: Successfully replayed TTS for {ctx.author.name}")
            await ctx.send("Replayed the most recent TTS audio.")
        except Exception as exc:
            bot_logger.error(f"Command %replay: Error for {ctx.author.name}: {exc}")
            await ctx.send(f"An error occurred: {exc}")
