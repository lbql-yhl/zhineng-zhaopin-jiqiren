# Manifest

Package: `小昭招聘机器人`
Version: `2.2`

## Entry Points

- Codex skill: `xiaozhao-robot-2`
- Hermes skill: `xiaozhao-robot-2`
- Hermes bundle: `/xiaozhao-robot-2`
- Hermes provider/model: `openai-codex / gpt-5.5`

## Skills

- `xiaozhao-robot-2`
- `zhipin-boss-recruitment-bot`
- `zhipin-recommend-screening-pipeline`
- `zhipin-open-jobs-read`
- `zhipin-open-job-jd-read` (legacy/manual recovery only; not used by the normal 2.0 automation flow)
- `zhipin-recommend-job-select`
- `zhipin-recommend-candidate-resume-read`
- `zhipin-archive-jd-resume-match`
- `zhipin-candidate-match-forward-flow`
- `zhipin-scheduled-forward-report`
- `zhipin-weekly-work-report`
- `zhipin-desktop-archive-export`

## Data

- `.zhipin-copilot/recruitment.sqlite3` is initialized by `bin/install.sh` in the target workspace.
- Runtime SQLite data, backups, logs, and recovered session exports are not included in the GitHub source package.
- Read-only report metrics helper: `skills/zhipin-boss-recruitment-bot/scripts/report_metrics.py`
- SQLite backup helper: `skills/zhipin-boss-recruitment-bot/scripts/sqlite_store.py backup-create`

## Automation Templates

- `boss-1-workday-flow.toml`
- `boss-2-sunday-flow.toml`
- `boss-3-daily-report.toml`
- `boss-4-weekly-report.toml`
- `boss-5-daily-report-data-prep.toml`
- `boss-6-weekly-report-data-prep.toml`
- `boss-7-sqlite-backup.toml`
- `xiaozhao-unfinished-tickets.toml`

## Security Notes

No Feishu secret, browser cookie, Hermes auth, Codex auth, or launchd runtime
state is included.
