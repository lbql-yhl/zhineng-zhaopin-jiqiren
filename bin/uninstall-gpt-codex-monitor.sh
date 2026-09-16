#!/bin/zsh
set -eu

LABEL="com.xiaozhao.gpt-codex-monitor"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

launchctl bootout "gui/$(id -u)" "$PLIST" >/dev/null 2>&1 || true
rm -f "$PLIST"

printf 'Uninstalled GPT/Codex outage monitor: %s\n' "$LABEL"
