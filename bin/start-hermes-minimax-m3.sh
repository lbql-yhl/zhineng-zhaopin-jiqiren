#!/bin/zsh
set -eu

WORKSPACE="${1:-/Users/helloworld/Documents/Codex/2026-05-26/https-www-zhipin-com-web-chat}"
cd "$WORKSPACE"

exec hermes \
  --provider minimax \
  --model MiniMax-M3 \
  --skills xiaozhao-robot-2 \
  --tui
