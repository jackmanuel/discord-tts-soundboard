#!/usr/bin/env bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

if [[ ! -x .venv/bin/python ]]; then
    echo "Missing virtual environment: create .venv and install dependencies first." >&2
    exit 1
fi

# Activation also puts tools such as yt-dlp on PATH.
source .venv/bin/activate
exec python -u bot.py "$@"
