#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
WIKI_BIN="$REPO_DIR/.venv/bin/wiki"
SOURCE_FILE="$REPO_DIR/pipeline_output/team_profiles.txt"

if [[ ! -x "$WIKI_BIN" ]]; then
  echo "Missing wiki CLI at $WIKI_BIN. Activate or create the repo venv first." >&2
  exit 1
fi

cd "$SCRIPT_DIR"
exec "$WIKI_BIN" watch "$SOURCE_FILE"
