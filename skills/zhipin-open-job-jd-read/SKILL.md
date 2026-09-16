---
name: zhipin-open-job-jd-read
description: Legacy/manual recovery skill for reading a BOSS/Zhipin open job JD into SQLite only when the user explicitly asks to refresh JD text. Do not use in the normal XiaoZhao Robot 2.0 automation flow.
---

# Zhipin Open Job JD Read

This is a legacy/manual recovery skill. Use it only when the user explicitly
asks to refresh or recover JD text from a visible BOSS open-job detail page.

Normal XiaoZhao Robot 2.0 automation does not use this skill: it checks open
jobs against the built-in user-provided JD library and stops for missing JD
evidence instead of clicking BOSS job-detail pages.

## SQLite Policy

Store the JD in:

```text
.zhipin-copilot/recruitment.sqlite3
```

Do not write JD archive files. The `jobs` table is the source of truth. Do not
run this automatically at the start of each screening day; only refresh JD text
after an explicit user request.

## Boundaries

- Prefer the Codex-supported Chrome plugin on the user's existing Google Chrome session. Use Computer Use only as a fallback when the Chrome plugin is unavailable, blocked, or visible-screen interaction is required.
- Read only the selected open job's detail/JD.
- Do not edit, publish, pause, close, refresh, boost, delete, copy, save, or
  switch job state.
- Do not message candidates or enter candidate-affecting flows.
- Stop on login, CAPTCHA, SMS, security verification, account abnormality, or
  ambiguous job-affecting UI.
- The JD is not complete until both the overall job-detail page and the
  `职位描述` text area/panel have been scrolled to the end and no new text
  appears.

## Workflow

1. Confirm the target open job identity from the visible list or current job
   detail.
2. Click only the safe job title/detail entry that opens the JD.
3. Verify the detail view belongs to the selected open job.
4. Expand full JD text if a read-only `展开全部` control is visible.
5. Scroll the overall job-detail page from top to bottom.
6. Separately scroll inside the `职位描述` text area/panel from top to bottom.
7. Extract structured JD fields and scroll evidence.
8. Store the JD in SQLite using
   `/Users/helloworld/.codex/skills/zhipin-open-job-jd-read/scripts/archive_open_job_jd.py`.
9. After every current open job has been stored for the day, prune stale JD rows
   with:

```bash
python3 /Users/helloworld/.codex/skills/zhipin-boss-recruitment-bot/scripts/sqlite_store.py \
  prune-jds-current-day \
  --open-job-ref "<today open job ref 1>" \
  --open-job-ref "<today open job ref 2>"
```

Include every open job from today's `开放中` list. Do not run this prune step
until the full current open-job list has been read and each current JD has been
successfully stored.

## Output

Return plain text fields:

```text
job_ref=<岗位身份>
job_id=<SQLite row id>
database_path=.zhipin-copilot/recruitment.sqlite3
last_jd_read_at=<读取时间>
read_status=success|need_review|blocked
page_scrolled_to_bottom=yes|no
job_description_scrolled_to_bottom=yes|no
stop_reason=<如有>
```

## Next Step

Use `zhipin-recommend-job-select` to enter 推荐牛人 and select the same `job_ref`.
