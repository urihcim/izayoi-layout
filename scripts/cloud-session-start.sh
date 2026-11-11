#!/bin/bash
# SessionStart hook: prepare a cloud session. Does nothing on a local machine.
#
# - installs the Python dependencies (fast when the uv cache is warm)
# - links corpus/ to the corpus built by scripts/cloud-corpus.sh
if [ "$CLAUDE_CODE_REMOTE" != "true" ]; then
  exit 0
fi

repo="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$repo" || exit 0

uv sync --locked --quiet || echo "uv sync failed" >&2

shared="${IZAYOI_SHARED_CORPUS:-/opt/izayoi/corpus}"
if [ ! -e corpus/kana.txt ]; then
  if [ -f "$shared/kana.txt" ]; then
    rm -rf corpus && ln -s "$shared" corpus
  else
    echo "corpus not found at $shared; run scripts/cloud-corpus.sh (see docs/design.md)" >&2
  fi
fi
exit 0
