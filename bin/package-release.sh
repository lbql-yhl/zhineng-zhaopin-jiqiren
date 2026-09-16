#!/bin/zsh
set -eu

VERSION="${1:-2.2}"
PACKAGE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIST_DIR="$PACKAGE_ROOT/dist"
ARCHIVE_NAME="xiaozhao-robot-${VERSION}.zip"
ARCHIVE_PATH="$DIST_DIR/$ARCHIVE_NAME"

mkdir -p "$DIST_DIR"
rm -f "$ARCHIVE_PATH"

cd "$PACKAGE_ROOT"

git archive \
  --format=zip \
  --prefix="xiaozhao-robot-${VERSION}/" \
  --output="$ARCHIVE_PATH" \
  HEAD

printf '%s\n' "$ARCHIVE_PATH"
