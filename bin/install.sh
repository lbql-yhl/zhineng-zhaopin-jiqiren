#!/bin/zsh
set -eu

PACKAGE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
TARGET_WORKSPACE="${1:-$PWD}"
TARGET_DATA_DIR="$TARGET_WORKSPACE/.zhipin-copilot"
TARGET_DB="$TARGET_DATA_DIR/recruitment.sqlite3"

mkdir -p "$CODEX_HOME/skills"
mkdir -p "$HERMES_HOME/skills/business"
mkdir -p "$HERMES_HOME/skill-bundles"
mkdir -p "$TARGET_WORKSPACE"
mkdir -p "$TARGET_DATA_DIR"

rsync -a --delete "$PACKAGE_ROOT/skills/" "$CODEX_HOME/skills/"
for skill_dir in "$PACKAGE_ROOT"/skills/*; do
  [ -d "$skill_dir" ] || continue
  skill_name="$(basename "$skill_dir")"
  mkdir -p "$HERMES_HOME/skills/business/$skill_name"
  rsync -a --delete "$skill_dir/" "$HERMES_HOME/skills/business/$skill_name/"
done

rsync -a --delete "$PACKAGE_ROOT/hermes/skills/business/xiaozhao-robot-2/" "$HERMES_HOME/skills/business/xiaozhao-robot-2/"
rsync -a "$PACKAGE_ROOT/hermes/skill-bundles/xiaozhao-robot-2.yaml" "$HERMES_HOME/skill-bundles/xiaozhao-robot-2.yaml"

if [ -d "$PACKAGE_ROOT/data/.zhipin-copilot" ]; then
  rsync -a "$PACKAGE_ROOT/data/.zhipin-copilot/" "$TARGET_DATA_DIR/"
fi

python3 "$PACKAGE_ROOT/skills/zhipin-boss-recruitment-bot/scripts/sqlite_store.py" --db "$TARGET_DB" init >/dev/null

printf 'Installed Codex skills to: %s\n' "$CODEX_HOME/skills"
printf 'Installed Hermes skills to: %s\n' "$HERMES_HOME/skills/business"
printf 'Installed Hermes bundle to: %s\n' "$HERMES_HOME/skill-bundles/xiaozhao-robot-2.yaml"
printf 'Installed SQLite data to: %s\n' "$TARGET_DATA_DIR"
printf 'Next: ensure Hermes model is openai-codex / gpt-5.5, configure Feishu secret, and log in to BOSS in Chrome.\n'
