---
name: zhipin-recommend-screening-pipeline
description: Use as the root orchestrator for the latest BOSS/Zhipin 推荐牛人 workflow. It coordinates open-job reading, user-provided JD-library checks, recommendation job selection, candidate resume reading, hard-requirement matching, direct BOSS forwarding to HR for candidates who pass all hard requirements, Feishu work reports, and optional desktop export.
---

# Zhipin Recommend Screening Pipeline

This is the root skill for the latest BOSS/Zhipin 推荐牛人 workflow. It chooses
the next child skill, tracks state, and keeps the flow recoverable.

## Skill Tree

```text
zhipin-recommend-screening-pipeline
├── jobs
│   └── zhipin-open-jobs-read
├── recommend
│   ├── zhipin-recommend-job-select
│   └── zhipin-recommend-candidate-resume-read
├── match-forward
│   ├── zhipin-archive-jd-resume-match
│   └── zhipin-candidate-match-forward-flow
└── export
    └── zhipin-desktop-archive-export
```

## SQLite Source Of Truth

Use this SQLite file as the primary store:

```text
.zhipin-copilot/recruitment.sqlite3
```

Normal operation writes JD, minimal candidate index, match,
processed-candidate, forwarding, run-event, and report records to SQLite. Do
not write JD/resume/match archive files by default, and do not persist full
resume text during screening.

Duplicate handling is mandatory:

- Before opening a candidate, check `processed_candidates` by the normalized
  candidate identity globally.
- At startup, seed the structured SQLite hard-gate cache with
  `sqlite_store.py seed-jd-hard-gates`; after each job selection, read
  `sqlite_store.py get-jd-hard-gates --job-ref "<岗位>"` once and reuse it until
  the job changes.
- If the candidate has been processed in any job, skip the candidate. The
  unique `candidate_key` must absorb separator differences such as
  `姓名-岗位-城市` versus `姓名 | 岗位 | 城市`.
- During one automation run, pass the current `automation_runs.run_id` to
  `batch-list-prefilter --run-id` so `screening_run_seen_candidates` skips
  candidates already seen during the same list-scroll loop before doing extra
  browser work.
- SQLite must also keep `resumes.candidate_key`,
  `processed_candidates.candidate_key`, and
  `forward_records(candidate_key, recipient)` unique.
- After a candidate is matched and either forwarded or rejected, candidate
  durable information must remain limited to name, age, education, and job ref.
  The normalized candidate key is internal dedupe metadata.
- After a candidate's online resume actually opens, record one
  `online_resume_viewed` run event. This is the quota source for the
  dynamic per-job switching rule.
- Every visible-list candidate that is actually screened must be written to
  `processed_candidates`. Candidates skipped because list-visible age or
  education fails the selected JD hard gate count as processed candidates even
  when no online resume is opened.

## Stability Rules

- Treat browser operations as fragile and SQLite operations as stable.
- Run one browser intent at a time; do not combine reading jobs, selecting jobs,
  and reading resumes in one uncontrolled step.
- At the beginning and end of a screening run, send only ordinary Feishu group
  notices: `现在开始工作` and `到点了，下班！`. These routine notices must not
  at-mention 钟苗.
- Only faults, blockers, missing JD-library evidence, failed-start states, or
  login/security abnormalities should notify 钟苗.
- Stop on login, CAPTCHA, slider verification, SMS, security verification,
  account abnormality, or any ambiguous candidate/job-affecting control. Do
  not click, drag, type, refresh, open, or close browser pages in that state;
  notify 钟苗 through Feishu with exactly `boss登陆异常，请检查～`.
- For any non-login runtime fault, UI blocker, script/database error,
  unexpected page state, or unrecoverable ambiguity in the full screening
  pipeline, stop the current flow, capture only the visible browser page when a
  browser page is involved, record the fault in SQLite, and notify 钟苗 through
  Feishu with:

```text
流程故障，故障如下
<具体故障原因、当前步骤、岗位/候选人（如有）、已停止的操作>
```

- Do not use any single visible person name or candidate name to judge page
  health or login state. After refreshing the current BOSS page, treat the page
  as normal only when BOSS core navigation such as `职位管理` and `推荐牛人` is
  visible, and no login, CAPTCHA, slider, SMS, security verification, or account
  abnormality is visible.
- Never send messages, greet candidates, reject candidates, favorite candidates,
  exchange contact information, request attachments, edit jobs, pause jobs, or
  close jobs.
- Do not ask Feishu for forwarding approval. All candidates who pass every hard
  requirement are forwarded to `HR`.
- Prefer exact visible evidence over inference. If two jobs or candidates may
  match, return `need_review`.
- Store minimum candidate identity fields for dedupe and reporting. Do not
  persist full online-resume sections to a separate table during normal
  screening; use the live resume only for hard-requirement judgment.
- Do not compress context after every candidate. Compress after every 5 handled
  candidates, and immediately on successful forwarding, job switch, fault,
  blocker, or safety stop.
- Do not refresh open-job JDs from BOSS during normal automation. Candidate
  matching uses the user-provided JD library stored in SQLite.
- At task start, read only the current `职位管理 -> 开放中` list and check whether
  each open job exists in the user-provided JD library. If a job is missing,
  notify 钟苗 through Feishu with exactly:
  `jd库里没有xxx岗位的jd，请提供。`
- Use only `推荐牛人 -> 最新`: process each open job until that job has opened 30
  online resumes in the `最新` tab, then switch to the next open job without
  refreshing or reloading the browser page.
- After every open job has opened 30 online resumes in `最新`, return to the
  first open job without refreshing or reloading the browser page, and start
  the same 30-online-resume cycle again.
- There is no separate total daily local quota. Continue until the scheduled
  runtime window ends, no processable candidates remain, the user stops the
  flow, or a safety stop is triggered. Do not use a forwarding-count quota.
- At workflow startup or recovery, at most one BOSS page refresh/reload is
  allowed to synchronize state. After that single refresh, job switches and
  job-cycle restarts must continue in the current page without refreshing.
- Every screening-flow end must send a Feishu notice unless the user explicitly
  says not to send Feishu notices for the current run.

## JD Library Policy

- The JD source of truth is the user-provided JD library, seeded into SQLite
  with `sqlite_store.py seed-user-jds`.
- Open-job checking is read-only: compare visible open jobs against the JD
  library by canonical job name.
- Do not click open-job detail pages, expand descriptions, or overwrite the JD
  library from BOSS unless the user explicitly asks for manual JD capture.
- The current built-in JD library contains `运营负责人`, `海外广告优化师（双休）`,
  `高级海外广告优化师`, and `Ui设计师`.

## Resume Read Policy

- Read exactly the current candidate's online resume.
- Before opening resumes in either the `推荐` tab or the `最新` tab, read the
  current list page/screen as a batch. Extract all visible candidates' name,
  age, and education, then run one SQLite batch prefilter to check duplicates
  plus hard age/education gates.
- After list screening, write the current batch's minimal candidate information
  to SQLite before opening any online resume for candidates who passed the list
  screen. Whether a candidate is suitable or not, minimal information must be
  recorded for later dedupe.
- Permanent screening rule: the list page may judge only age and education.
  Product, region, years of experience, language, business type, tool/platform,
  and every other hard requirement must wait until the online resume is opened
  and read.
- Open only the batch candidates returned as `open_resume`. If list-visible age
  or education violates the selected JD hard requirement, do not open that
  resume; write only name, age, education, and job ref to `processed_candidates`,
  count the candidate as processed for daily/weekly reports, then continue.
- If age or education is missing from the visible row, keep the candidate in the
  open queue so the online resume can verify it.
- Fully scroll the online resume page/panel to the bottom, read all resume
  information for the current candidate, and analyze it against the hard
  requirements before storing, judging, rejecting, or forwarding.
- Follow the SQLite `decision_plan` returned by `get-jd-hard-gates` only after
  the online resume is open for all non-age/non-education gates. Once a hard
  gate clearly fails, stop deep reasoning for that candidate and do not forward.
- Ignore bottom sections for other people, including `其他名校毕业的牛人`,
  `其他相似经历的牛人`, `相似经历`, `相似牛人`, and similar-candidate information.
  These sections must not enter the resume record or affect judgment.

## Scheduled Runtime Window

- Use local machine time / China timezone semantics.
- `boss-1` candidate screening runs Monday-Saturday from `08:00-20:00`.
- Sunday uses `boss-2` from `19:00-21:00`. Outside those windows, on China
  legal holidays, or when the user pauses automation, record the skip reason
  and do not operate BOSS.

## Pipeline States

Record pipeline events in SQLite `run_events`:

```text
open_jobs_read
-> jd_library_checked
-> target_job_confirmed
-> recommend_job_selected
-> candidate_resume_indexed
-> jd_resume_matched
-> boss_forward_or_hard_fail_recorded
-> boss_forwarded_or_stopped
-> desktop_exported
```

Each event should include event type, job ref, candidate ref, status, note, and
plain detail text when needed.

## Workflow

1. Use `zhipin-open-jobs-read` to read `职位管理 -> 开放中`.
2. Seed/check the user-provided JD library, then compare all open jobs against
   it. If any open job is missing, notify 钟苗 and stop or wait for JD input.
3. Enter `推荐牛人 -> 最新`. Iterate open jobs in order. For each job, continue
   processing candidates until that job has opened 30 online resumes in `最新`.
4. Before every job switch, verify the current page is healthy, then select the
   next open job without refreshing or reloading the browser page.
5. After all open jobs have reached 30 opened online resumes in `最新`, return
   to the first open job without refreshing or reloading the browser page, and
   repeat the same 30-online-resume cycle.
6. Continue until the runtime window ends, no processable candidates remain,
   the user stops the flow, or a safety stop is triggered. Do not use any total
   daily local quota or forwarding-count quota.
7. Use `zhipin-recommend-job-select` to enter 推荐牛人 and select the matching
   open job/tab for the current stage.
8. Before opening candidates, use
   `zhipin-recommend-candidate-resume-read` to batch-read the current visible
   recommendation list and run SQLite `batch-list-prefilter`; skip candidates
   already processed in any job and candidates whose visible age/education
   fails hard gates. Do not reject candidates from the list for any other hard
   requirement.
9. Open only the resulting batch queue. Immediately after each online resume
   actually opens, record `online_resume_viewed`, then fully read the current
   online resume to the bottom for complete live hard-gate analysis. Store only
   the minimal candidate index in SQLite: name, age, education, and job ref.
8. Use `zhipin-archive-jd-resume-match` to analyze the resume against the
   HR-provided JD hard requirements. Missing direct evidence means the hard
   requirement is not satisfied.
9. When every hard requirement is satisfied, use
   `zhipin-candidate-match-forward-flow` to forward the candidate in BOSS to
   `HR` directly.
10. Use `zhipin-desktop-archive-export` only when the user wants
    human-readable files grouped by job.

## Forwarding Scope

Forwarding is never automatic from a resume card. The required order is:

```text
列表年龄/学历预筛通过 -> 在线简历完整读取 -> JD硬性条件检查 -> 全部满足 -> BOSS 站内转发给HR
```

The BOSS forwarding step is simple: when a candidate satisfies every hard
requirement for the current job, forward the resume directly in BOSS to
`HR`.

## Daily Reporting

- Daily 09:00 report is a work report, not a code report.
- It must send an ordinary Feishu group notice and include runtime/status,
  token usage, global funnel, job-level hard-gate pass/fail bands, and
  XiaoZhao insights/recommendations.
- Do not at-mention 钟苗 for routine daily/weekly report delivery; notify 钟苗
  only when the report contains a fault, login/security abnormality, missing JD,
  or failed-start condition.
- Daily and weekly summary records must be persisted in SQLite `reports`.
- Visible Feishu report must not include code, commands, raw internal data, raw paths,
  or implementation details.
- Visible report must not include candidate names or per-candidate lists in any
  pass/fail band.
- Token usage must use the local machine's Codex total for that calendar day:
  sum `~/.codex/sessions/YYYY/MM/DD/*.jsonl`
  last `event_msg` with `payload.type=token_count` for that day, using `payload.info.total_token_usage.total_tokens`. Do not use Hermes credential
  pool quota, Feishu split totals, or per-flow token partitions for the visible
  report.
- Report bands are hard-requirement passed/forwarded and hard-requirement
  failed/not-forwarded.
- Daily and weekly totals are processed-candidate totals from
  `processed_candidates`, not online-resume-open totals. List age/education
  failures are included in the processed count.

## Output

Return:

- current pipeline state;
- child skill used;
- SQLite database path and updated row ids;
- processed-candidate duplicate/add/skip status;
- candidates/jobs completed;
- any `need_review` or `blocked` reason;
- next recommended child skill.
