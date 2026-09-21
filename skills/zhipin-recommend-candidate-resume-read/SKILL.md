---
name: zhipin-recommend-candidate-resume-read
description: Use after the recommended job is selected in BOSS/Zhipin 推荐牛人, to batch-prefilter all visible candidates by SQLite duplicate state plus list-visible age/education, click only queued candidate names, open online resumes, scroll to the bottom, fully read them for hard-gate analysis, ignore similar-candidate sections, and keep only lightweight SQLite processing records.
---

# Zhipin Recommend Candidate Resume Read

Use this skill after `zhipin-recommend-job-select` confirms that 推荐牛人 is
filtered to the target job.

## SQLite And Dedup Policy

Store candidate data in:

```text
.zhipin-copilot/recruitment.sqlite3
```

Before opening a candidate, check SQLite `processed_candidates` by
the normalized candidate identity globally. The stored `candidate_key` must
treat separator differences such as `姓名-岗位-城市` and
`姓名 | 岗位 | 城市` as the same candidate. If the same candidate was already
processed in any job, skip it. Do not rely on BOSS red dots.

Do not write resume archive files or full online-resume section records during
normal screening. Use the live online resume only for hard-requirement judgment,
and persist only lightweight processing/dedupe state plus run events.

## Boundaries

- Prefer the Codex-supported Chrome plugin on the user's existing Google Chrome session. Use Computer Use only as a fallback when the Chrome plugin is unavailable, blocked, or visible-screen interaction is required.
- Read only the selected recommended candidate's online resume.
- Click only the candidate name or safe resume preview entry.
- Do not greet, message, invite, favorite, reject, exchange contact
  information, request attachments, or change candidate state.
- Do not infer protected attributes or use them for screening.
- Stop on login, CAPTCHA, SMS, security verification, account abnormality, or
  ambiguous candidate-affecting UI.

## Batch List Prefilter

- Before opening any resume, read all visible candidate rows on the current
  推荐牛人 list page/screen.
- For each visible row, extract only name, age, and education when visible.
- After list screening, write the current batch's minimal candidate information
  to SQLite before opening any online resume for candidates who passed the list
  screen. Whether a candidate is suitable or not, minimal information must be
  recorded for later dedupe.
- Run one SQLite batch prefilter command for the visible rows:

```bash
python3 /Users/helloworld/.codex/skills/zhipin-boss-recruitment-bot/scripts/sqlite_store.py batch-list-prefilter --job-ref "<岗位>" --candidate "<姓名>|<年龄>|<学历>" --candidate "<姓名2>|<年龄2>|<学历2>"
```

- The command checks SQLite duplicates globally and applies hard age/education
  gates for the selected job.
- The list-stage prefilter is age/education-only. Do not judge product,
  region, years of experience, language, business type, tool/platform, or any
  other hard requirement from the list page; open the online resume and judge
  those requirements from the live resume.
- Pass `--run-id "<本轮run_id>"` whenever the automation has acquired an
  `automation_runs.run_id`; this enables `screening_run_seen_candidates` to skip
  candidates already seen during the same list-scroll loop.
- The command reads structured SQLite `job_hard_gates`; run
  `sqlite_store.py seed-jd-hard-gates` once after JD seeding and
  `sqlite_store.py get-jd-hard-gates --job-ref "<岗位>"` once after selecting a
  job.
- Open only names returned in `open_candidates`.
- If visible age or education fails, do not open that candidate's online
  resume. The command writes only name, age, education, and job ref.
- These list-stage age/education failures are processed candidates. They must
  stay in SQLite `processed_candidates` and count in daily/weekly processed
  totals even though no online resume was opened.
- If age or education is not visible, keep the candidate in `open_candidates`
  so the online resume can verify it.
- After the queued visible candidates are handled, scroll the candidate list to
  load the next batch and repeat.

## Resume Scope

- Only open candidates that pass the batch list prefilter or need online
  verification because list-visible age/education is missing.
- Read all resume information for the current candidate from top to bottom,
  scrolling until the end is reached. Never judge, reject, or forward from a
  partial online resume.
- After opening the online resume, record `online_resume_viewed`. After reaching
  the bottom, use the visible resume only for hard-requirement judgment; do not
  persist full resume sections to a separate table.
- Ignore bottom sections for other people, including `其他名校毕业的牛人`,
  `其他相似经历的牛人`, `相似经历`, `相似牛人`, and similar-candidate information.
- Do not copy those similar-candidate blocks into SQLite and do not let them
  affect judgment.

## Workflow

1. Confirm 推荐牛人 is showing candidates for the selected target job.
2. Read all visible candidate rows and run `batch-list-prefilter`.
3. Build the open queue from `open_candidates`.
4. Identify each queued candidate row by visible row index/name/title evidence.
5. Click the candidate name or safe resume entry.
6. Confirm an online resume panel/page opens for the same candidate.
7. Read all resume information for the current candidate from top to bottom,
   scrolling until the end is reached.
8. Analyze the current candidate's resume against the JD hard requirements,
   excluding bottom sections for other people and similar-candidate sections.
9. Store only lightweight processing status in SQLite; do not store full opened
   online-resume sections in a separate table.

## Output

Return plain text fields and write only minimal candidate index fields to SQLite:

```text
candidate_ref=<候选人身份>
candidate_name=<候选人名称>
job_ref=<岗位身份>
resume_id=<SQLite row id>
database_path=.zhipin-copilot/recruitment.sqlite3
duplicate_status=new|already_processed|unknown
age=<年龄>
education_level=<学历>
target_role=<求职意向>
read_status=success|need_review|blocked|skipped
stop_reason=<如有>
```

## Next Step

Use `zhipin-archive-jd-resume-match` with the SQLite `job_ref` and
`candidate_ref`.


## Performance Optimization

- Keep BOSS browser operations serial, but batch-read the visible candidate list before opening resumes.
- Read one candidate's online resume completely once, then reuse the structured snapshot for matching; do not repeatedly screenshot or reread the same page.
- Load `get-jd-hard-gates` once after selecting a job and reuse the returned `jd_version` until the job changes.
- Run deterministic age, education, experience, region, and keyword gates before any model-based ambiguity review.
- Reuse `candidate_analysis_cache` when candidate snapshot, `jd_version`, and `matcher_version` are unchanged.
- Record stage duration and cache status with `screening_metrics.py` so optimization is based on measured bottlenecks.
- Do not use vector similarity as the sole duplicate decision; use it only to recall candidates for review after exact and strong-fingerprint checks.
