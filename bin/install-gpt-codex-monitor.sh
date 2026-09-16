#!/bin/zsh
set -eu

PACKAGE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3}"
LABEL="com.xiaozhao.gpt-codex-monitor"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$HOME/.hermes/logs"
STATE_DIR="$HOME/.hermes/state"
INSTALL_DIR="$HOME/.hermes/bin/xiaozhao-monitor"
SOURCE_SCRIPT="$PACKAGE_ROOT/skills/zhipin-boss-recruitment-bot/scripts/gpt_codex_outage_monitor.py"
SCRIPT="$INSTALL_DIR/gpt_codex_outage_monitor.py"

mkdir -p "$HOME/Library/LaunchAgents" "$LOG_DIR" "$STATE_DIR" "$INSTALL_DIR"
cp "$SOURCE_SCRIPT" "$SCRIPT"
chmod 755 "$SCRIPT"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON_BIN</string>
    <string>$SCRIPT</string>
    <string>--threshold</string>
    <string>2</string>
    <string>--cooldown-minutes</string>
    <string>60</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$INSTALL_DIR</string>
  <key>RunAtLoad</key>
  <true/>
  <key>StartInterval</key>
  <integer>300</integer>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/xiaozhao_gpt_codex_monitor.launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/xiaozhao_gpt_codex_monitor.launchd.err.log</string>
</dict>
</plist>
EOF

chmod 644 "$PLIST"

launchctl bootout "gui/$(id -u)" "$PLIST" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl kickstart -k "gui/$(id -u)/$LABEL"

printf 'Installed GPT/Codex outage monitor: %s\n' "$PLIST"
printf 'Installed monitor script: %s\n' "$SCRIPT"
printf 'Status: launchctl print gui/%s/%s\n' "$(id -u)" "$LABEL"
printf 'Logs: %s\n' "$LOG_DIR/xiaozhao_gpt_codex_monitor.log"
