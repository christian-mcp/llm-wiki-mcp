#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DEST_DIR="${1:-$REPO_DIR/.quartz-build/quartz}"
QUARTZ_REPO="${QUARTZ_REPO:-https://github.com/jackyzha0/quartz.git}"
QUARTZ_REF="${QUARTZ_REF:-v4}"
SOURCE_WIKI="${SOURCE_WIKI:-$REPO_DIR/research-wiki/wiki}"

if [[ ! -d "$SOURCE_WIKI" ]]; then
  echo "Source wiki folder not found: $SOURCE_WIKI" >&2
  exit 1
fi

mkdir -p "$(dirname "$DEST_DIR")"

if [[ ! -d "$DEST_DIR/.git" ]]; then
  git clone --depth 1 --branch "$QUARTZ_REF" "$QUARTZ_REPO" "$DEST_DIR"
else
  git -C "$DEST_DIR" fetch origin "$QUARTZ_REF" --depth 1
  git -C "$DEST_DIR" checkout -f "$QUARTZ_REF"
  git -C "$DEST_DIR" reset --hard "origin/$QUARTZ_REF"
  git -C "$DEST_DIR" clean -fd
fi

mkdir -p "$DEST_DIR/content"
rsync -a --delete \
  --exclude ".obsidian" \
  --exclude ".gitkeep" \
  "$SOURCE_WIKI/" "$DEST_DIR/content/"

cp "$SCRIPT_DIR/quartz.config.ts" "$DEST_DIR/quartz.config.ts"
cp "$SCRIPT_DIR/quartz.layout.ts" "$DEST_DIR/quartz.layout.ts"

echo "Prepared Quartz build tree at $DEST_DIR"
