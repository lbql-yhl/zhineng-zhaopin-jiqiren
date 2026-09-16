---
name: zhipin-open-jobs-read
description: Use when reading BOSS/Zhipin "职位管理 -> 开放中" open recruiting jobs before starting the 推荐牛人 flow. This skill is read-only and returns the visible open job list.
---

# Zhipin Open Jobs Read

Use this skill at the beginning of a BOSS/Zhipin recommended-candidate workflow to read the open recruiting jobs under `职位管理 -> 开放中`.

## Boundaries

- Prefer the Codex-supported Chrome plugin on the user's existing Google Chrome session. Use Computer Use only as a fallback when the Chrome plugin is unavailable, blocked, or visible-screen interaction is required.
- Read only the authorized BOSS/Zhipin page.
- Do not create, edit, close, pause, refresh, promote, delete, or switch jobs.
- Do not message candidates, open candidate resumes, or change candidate state.
- Stop on login, CAPTCHA, SMS, security verification, account abnormality, or ambiguous job-affecting UI.

## Workflow

1. Focus the existing Google Chrome page through the Codex-supported Chrome plugin when available; otherwise use Computer Use.
2. Confirm the page is BOSS/Zhipin and the user is authenticated.
3. Navigate by safe visible UI to `职位管理`.
4. Select `开放中` only if it is a read-only tab/filter.
5. Extract the visible open job rows. Prefer accessibility text over OCR.
6. If pagination or scrolling is visible, read only the currently visible jobs unless the user explicitly asks for all pages.

## Output

Return compact plain text or a small table, not a local structured file:

```text
page=职位管理 -> 开放中
read_status=success|need_review|blocked
job_1_ref=<岗位身份>
job_1_title=<岗位名称>
job_1_city=<城市>
job_1_salary=<薪资>
job_1_experience=<经验要求>
job_1_education=<学历要求>
job_1_status=开放中
stop_reason=<如有>
```

## Next Step

After reading open jobs, check them against the user-provided JD library:

```bash
python3 /Users/helloworld/.codex/skills/zhipin-boss-recruitment-bot/scripts/sqlite_store.py seed-user-jds
python3 /Users/helloworld/.codex/skills/zhipin-boss-recruitment-bot/scripts/check_open_jobs_jd_library.py \
  --open-job-ref "<岗位身份>"
```

Use `--notify-feishu` only when the open job is genuinely missing from the JD
library and 钟苗 should be notified. Normal XiaoZhao Robot 2.0 automation does
not open BOSS job-detail pages to capture or refresh JD text.
