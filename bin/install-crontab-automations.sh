#!/bin/zsh
set -eu

PACKAGE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="${XIAOZHAO_CRON_LOG_DIR:-$HOME/.hermes/logs/xiaozhao_cron}"
RUNNER_DIR="$HOME/.hermes/bin/xiaozhao-cron"
MARK_BEGIN="# BEGIN XIAOZHAO ROBOT AUTOMATIONS"
MARK_END="# END XIAOZHAO ROBOT AUTOMATIONS"
TMP_CURRENT="$(mktemp)"
TMP_NEXT="$(mktemp)"
TMP_BLOCK="$(mktemp)"

cleanup() {
  rm -f "$TMP_CURRENT" "$TMP_NEXT" "$TMP_BLOCK"
}
trap cleanup EXIT

mkdir -p "$LOG_DIR" "$RUNNER_DIR"
cat > "$RUNNER_DIR/check-cron-automation-health.sh" <<EOF
#!/bin/zsh
set -eu
export XIAOZHAO_PACKAGE_ROOT="$PACKAGE_ROOT"
PYTHON_BIN="\${PYTHON_BIN:-/usr/bin/python3}"
exec "\$PYTHON_BIN" "$PACKAGE_ROOT/automations/check_cron_automation_health.py" "\$@"
EOF
cat > "$RUNNER_DIR/run-cron-automation.sh" <<EOF
#!/bin/zsh
set -eu
export XIAOZHAO_PACKAGE_ROOT="$PACKAGE_ROOT"
PYTHON_BIN="\${PYTHON_BIN:-/usr/bin/python3}"
exec "\$PYTHON_BIN" "$PACKAGE_ROOT/automations/run_cron_automation.py" "\$@"
EOF
chmod 755 "$RUNNER_DIR/check-cron-automation-health.sh" "$RUNNER_DIR/run-cron-automation.sh"

crontab -l > "$TMP_CURRENT" 2>/dev/null || true

awk -v begin="$MARK_BEGIN" -v end="$MARK_END" '
  $0 == begin { skip = 1; next }
  $0 == end { skip = 0; next }
  skip != 1 { print }
' "$TMP_CURRENT" > "$TMP_NEXT"

cat > "$TMP_BLOCK" <<EOF
$MARK_BEGIN
SHELL=/bin/zsh
PATH=/Users/helloworld/.hermes/node/bin:/Users/helloworld/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin
LANG=en_US.UTF-8

0 8 * * 1-6 XIAOZHAO_PACKAGE_ROOT="$PACKAGE_ROOT" "$RUNNER_DIR/run-cron-automation.sh" "$PACKAGE_ROOT/automations/boss-1-workday-flow.toml" >> "$LOG_DIR/boss-1-workday-flow.log" 2>&1
0 19 * * 0 XIAOZHAO_PACKAGE_ROOT="$PACKAGE_ROOT" "$RUNNER_DIR/run-cron-automation.sh" "$PACKAGE_ROOT/automations/boss-2-sunday-flow.toml" >> "$LOG_DIR/boss-2-sunday-flow.log" 2>&1
0 9 * * * XIAOZHAO_PACKAGE_ROOT="$PACKAGE_ROOT" "$RUNNER_DIR/run-cron-automation.sh" "$PACKAGE_ROOT/automations/boss-3-daily-report.toml" >> "$LOG_DIR/boss-3-daily-report.log" 2>&1
0 8 * * 1 XIAOZHAO_PACKAGE_ROOT="$PACKAGE_ROOT" "$RUNNER_DIR/run-cron-automation.sh" "$PACKAGE_ROOT/automations/boss-4-weekly-report.toml" >> "$LOG_DIR/boss-4-weekly-report.log" 2>&1
0 23 * * * XIAOZHAO_PACKAGE_ROOT="$PACKAGE_ROOT" "$RUNNER_DIR/run-cron-automation.sh" "$PACKAGE_ROOT/automations/boss-5-daily-report-data-prep.toml" >> "$LOG_DIR/boss-5-daily-report-data-prep.log" 2>&1
30 23 * * 0 XIAOZHAO_PACKAGE_ROOT="$PACKAGE_ROOT" "$RUNNER_DIR/run-cron-automation.sh" "$PACKAGE_ROOT/automations/boss-6-weekly-report-data-prep.toml" >> "$LOG_DIR/boss-6-weekly-report-data-prep.log" 2>&1
10 23 * * * XIAOZHAO_PACKAGE_ROOT="$PACKAGE_ROOT" "$RUNNER_DIR/run-cron-automation.sh" "$PACKAGE_ROOT/automations/boss-7-sqlite-backup.toml" >> "$LOG_DIR/boss-7-sqlite-backup.log" 2>&1
0 9 * * * XIAOZHAO_PACKAGE_ROOT="$PACKAGE_ROOT" "$RUNNER_DIR/run-cron-automation.sh" "$PACKAGE_ROOT/automations/xiaozhao-unfinished-tickets.toml" >> "$LOG_DIR/xiaozhao-unfinished-tickets.log" 2>&1

*/5 * * * * XIAOZHAO_PACKAGE_ROOT="$PACKAGE_ROOT" "$RUNNER_DIR/check-cron-automation-health.sh" >> "$LOG_DIR/automation-health.log" 2>&1
$MARK_END
EOF

{
  sed '/^[[:space:]]*$/N;/^\n$/D' "$TMP_NEXT"
  printf '\n'
  cat "$TMP_BLOCK"
} | crontab -

printf 'Installed XiaoZhao crontab automations.\n'
printf 'Workspace: %s\n' "$PACKAGE_ROOT"
printf 'Logs: %s\n' "$LOG_DIR"
printf 'Runners: %s\n' "$RUNNER_DIR"
printf 'Check: crontab -l\n'
