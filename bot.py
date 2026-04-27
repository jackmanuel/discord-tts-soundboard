from tts_bot.app import create_bot, parse_args


def main():
    args = parse_args()
    bot, settings = create_bot(args)
    bot.run(settings.DISCORD_TOKEN)


if __name__ == "__main__":
    main()
