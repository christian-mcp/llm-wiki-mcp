#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_DIR="${BUILD_DIR:-$REPO_DIR/.quartz-build/quartz}"

"$SCRIPT_DIR/prepare-build.sh" "$BUILD_DIR"

cd "$BUILD_DIR"
npm ci
npx quartz build --serve
