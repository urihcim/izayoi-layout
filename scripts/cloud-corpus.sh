#!/bin/bash
# Build the kana corpus into a directory outside the repository.
#
# Called from the cloud environment's setup script, whose result is cached
# across sessions (the repository itself is cloned afresh every session).
# Needs network access to www.aozora.gr.jp, files.catbox.moe (n-gram tables) and PyPI.
#
# Usage: scripts/cloud-corpus.sh [OUT_DIR]   (default: /opt/izayoi/corpus)
set -euo pipefail

out="${1:-/opt/izayoi/corpus}"
repo="$(cd "$(dirname "$0")/.." && pwd)"
count="${IZAYOI_CORPUS_COUNT:-150}"

mkdir -p "$out"
cd "$repo"
uv sync --locked --quiet
uv run --quiet izayoi corpus-fetch --dest "$out/raw/aozora" --count "$count" --delay 0.5
uv run --quiet izayoi corpus-build --raw "$out/raw" -o "$out/kana.txt"
uv run --quiet izayoi corpus-fetch-ngram --dest "$out/ngram/logos" || echo "n-gram tables not fetched" >&2
