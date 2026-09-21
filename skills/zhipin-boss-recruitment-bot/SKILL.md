---
name: zhipin-boss-recruitment-bot
description: Internal execution package for XiaoZhao Robot 2.0. Use for BOSS/Zhipin open-job checks, recommendation job selection, candidate list prefiltering, online-resume hard-gate matching, direct BOSS forwarding to HR, and aggregate reports.
---

# Zhipin Boss Recruitment Bot

This is the internal execution package for `xiaozhao-robot-2`. Use it for BOSS
screening, reports, and export requests. Do not use older JSON archive,
attachment-resume, scoring, Feishu-forwarding-approval, BOSS JD scraping, or
forwarding-note flows.

## Skill Tree

```text
xiaozhao-robot-2
└── zhipin-boss-recruitment-bot
    ├── zhipin-recommend-screening-pipeline
    ├── zhipin-open-jobs-read
    ├── zhipin-recommend-job-select
    ├── zhipin-recommend-candidate-resume-read
    ├── zhipin-archive-jd-resume-match
    ├── zhipin-candidate-match-forward-flow
    ├── zhipin-scheduled-forward-report
    ├── zhipin-weekly-work-report
    └── zhipin-desktop-archive-export
```

Load `zhipin-recommend-screening-pipeline` first for runtime policy, then use
the narrow child skill for the current step.

## Browser Control Binding

For BOSS/Zhipin browser control, prefer the Codex-supported Chrome plugin on the user's existing Google Chrome session. Use Computer Use as the fallback when the Chrome plugin is unavailable, blocked, or visible-screen interaction is required. Do not use Chrome CDP, Chrome DevTools Protocol, remote debugging ports, `127.0.0.1:9222`, `/json/version`, hidden browser sessions, or non-Codex browser automation libraries. CDP availability is irrelevant to startup health and must never block a run.

## SQLite Store

Default database:

```text
.zhipin-copilot/recruitment.sqlite3
```

Use `scripts/sqlite_store.py` for all persistent state. The database enforces
candidate uniqueness through internal `candidate_key` values.

Durable candidate data is limited to:

```text
岗位、姓名、年龄、学历、求职期望/目标岗位、城市、薪资、工作年限
```

Do not persist full online-resume section records during normal screening.
Read the live resume only as needed for hard-requirement judgment, and keep
only lightweight candidate list/dedupe fields plus run events. For common names
such as `王先生`, never rely on the name alone for second-pass dedupe; preserve
age, education, expectation/target role, current screening job, city, salary,
and years of experience whenever visible.

Useful commands:

```bash
python3 /Users/helloworld/.codex/skills/zhipin-boss-recruitment-bot/scripts/sqlite_store.py init
python3 /Users/helloworld/.codex/skills/zhipin-boss-recruitment-bot/scripts/sqlite_store.py seed-user-jds
python3 /Users/helloworld/.codex/skills/zhipin-boss-recruitment-bot/scripts/sqlite_store.py processed-check --job-ref "<岗位>" --candidate-ref "<候选人>"
python3 /Users/helloworld/.codex/skills/zhipin-boss-recruitment-bot/scripts/sqlite_store.py processed-check --job-ref "<岗位>" --candidate-ref "<候选人>" --age <年龄> --education-level "<学历>"
python3 /Users/helloworld/.codex/skills/zhipin-boss-recruitment-bot/scripts/sqlite_store.py seed-jd-hard-gates
python3 /Users/helloworld/.codex/skills/zhipin-boss-recruitment-bot/scripts/sqlite_store.py get-jd-hard-gates --job-ref "<岗位>"
python3 /Users/helloworld/.codex/skills/zhipin-boss-recruitment-bot/scripts/sqlite_store.py list-prefilter --job-ref "<岗位>" --candidate-name "<姓名>" --age <年龄> --education-level "<学历>"
python3 /Users/helloworld/.codex/skills/zhipin-boss-recruitment-bot/scripts/sqlite_store.py batch-list-prefilter --job-ref "<岗位>" --run-id "<本轮run_id>" --candidate "<姓名>|<年龄>|<学历>" --candidate "<姓名2>|<年龄2>|<学历2>"
python3 /Users/helloworld/.codex/skills/zhipin-boss-recruitment-bot/scripts/sqlite_store.py upsert-candidate-minimal --job-ref "<岗位>" --candidate-name "<姓名>" --age <年龄> --education-level "<学历>" --target-role "<求职期望>" --city "<城市>" --salary "<薪资>" --years-experience "<工作年限>"
python3 /Users/helloworld/.codex/skills/zhipin-boss-recruitment-bot/scripts/sqlite_store.py health-check
python3 skills/zhipin-boss-recruitment-bot/scripts/risk_feishu_alert.py --task "小昭/BOSS 自动化" --reason "GPT/主模型通道无法使用"
```

If GPT/Codex/Hermes cannot start, cannot authenticate, times out repeatedly, or
is confirmed unavailable, do not begin BOSS screening. Send the Feishu risk
alert above first. The alert script does not depend on GPT; optional
`--fallback-provider deepseek|minimax` only adds a short supplemental message
when those provider credentials are configured and working.

## Full Screening Flow

1. Read current open jobs from BOSS `职位管理 -> 开放中`.
2. Seed/check the built-in user-provided JD library in SQLite.
2a. Run `seed-jd-hard-gates` once after JD seeding. Use SQLite `job_hard_gates`
    as the structured hard-requirement cache for age, education, and hard-gate
    labels instead of repeatedly reading/parsing JD text. The same row contains
    `decision_plan`, which defines the fast-fail order for resume analysis.
3. Compare open jobs against the JD library. If an open job is missing, notify
   钟苗: `jd库里没有xxx岗位的jd，请提供。`
4. Enter `推荐牛人` and select the matching job.
5. For the current 推荐牛人 list page/screen, read all visible candidate rows
   before opening any resume. Extract name, age, education, expectation/target
   role, city, salary, and years of experience whenever visible.
6. Run `batch-list-prefilter` once for the visible rows, passing the current
   automation `run_id`. It checks `screening_run_seen_candidates` for same-run
   duplicates, checks SQLite duplicates globally with the name/age/education
   fingerprint when visible, then applies list-visible age/education hard gates
   from SQLite `job_hard_gates`. After list screening, it first writes the
   current batch's minimal candidate information to SQLite. Whether a candidate
   is suitable or not, minimal information must be recorded for later dedupe.
7. Build the `open_resume` queue from the batch result:
   - age hard requirement;
   - education hard requirement.
8. If list age or education fails, do not open the online resume. Store
   岗位/姓名/年龄/学历/求职期望/目标岗位/城市/薪资/工作年限 in `processed_candidates`,
   write the date/name to
   `daily_processed_candidates`, and move on.
9. If list prefilter passes or visible data is insufficient, click the
   candidate name, open the online resume, scroll the online resume completely
   to the bottom, read all resume information for the current candidate, and
   analyze it against the hard requirements before judging, rejecting, or
   forwarding.
10. After the online resume is successfully opened, run
    `sqlite_store.py record-online-resume-view` for the current job/candidate.
11. Ignore bottom sections for other people, including `其他名校毕业的牛人`,
    `其他相似经历的牛人`, `相似经历`, `相似牛人`, and similar-candidate information.
12. Judge whether the candidate is suitable by analyzing the complete live
    resume against the HR-provided JD hard requirements. Missing direct
    evidence means the hard requirement is not satisfied.
13. If all hard requirements pass, BOSS-forward the resume directly to
    `HR`.
14. After the batch queue is finished, scroll the recommendation list to load
    the next visible batch and repeat.
16. Use only `推荐牛人 -> 最新`: per job, open up to 30 online resumes. Count
    every successfully opened online resume, regardless of whether it is
    forwarded.
17. At workflow startup or recovery, at most one BOSS page refresh/reload is
    allowed to synchronize state. After that single refresh, the same run must
    not refresh or reload the page again.
18. When the current job reaches 30 opened online resumes in `最新`, move to the
    next open job without refreshing or reloading the current BOSS page.
18a. When all jobs reach 30 opened online resumes in `最新`, return to the first
     open job without refreshing the BOSS page, and start the same
     30-online-resume cycle again.
19. There is no separate total daily local quota. Continue until the runtime
    window ends, no processable candidates remain, the user stops the flow, or
    a safety stop is triggered. Do not use a forwarding-count quota.

## Runtime Windows

- Workday/main flow: Monday-Saturday `08:00-20:00` local machine time / China
  timezone semantics.
- Sunday flow: Sunday `19:00-21:00`.
- China legal holidays are skipped unless the user provides a new rule.
- At the end of the runtime window, finish the current candidate first, then
  send the end notice.

## Checkpoint Policy

Do not compress context after every candidate.

Create a checkpoint:

- after every 5 handled candidates;
- immediately after successful forwarding;
- when switching jobs;
- on fault, blocker, or safety stop.

The checkpoint can mention the batch and row ids, but do not persist detailed
candidate reasoning as database candidate information.

## Built-In JD Library

`运营负责人`

- 海外中东地区负责经历 1 年以上
- 语聊或语音房业务
- 2 年以上海外中东地区运营经验
- 大专以上
- 35 岁以下

`海外广告优化师（双休）` / `高级海外广告优化师`

- 海外地区广告优化经验
- 1 年以上 1v1 社交 / 直播社交 / 语聊 / 语音房 / AI 社交产品投放经验，满足其一即可
- 新增符合条件：a=海外；b=1v1 / 社交 / 语音 / 语聊 / 直播社交 / AI 社交任一关键词。简历全文满足 a+b（分别出现海外和 b 任一关键词，不要求相邻）或 ab（如“海外社交”等连写，同时包含海外和 b 任一关键词）都符合目标产品/业务要求
- 大专以上
- 35 岁以下

`Ui设计师`

- 1 年以上直播社交 / 语聊 / 语音房 / AI 社交 App UI 设计经验，满足其一即可
- 大专以上
- 32 岁以下

## Matching Policy

- Judge suitability by analyzing the candidate against the HR-provided JD hard
  requirements. Missing direct evidence means the hard requirement is not
  satisfied.
- Ignore bottom sections for other people, including `其他名校毕业的牛人` and
  similar-candidate information.
- Use the SQLite `decision_plan` from `get-jd-hard-gates` for each selected
  job: age, education, then product/region/year gates. Once any hard gate
  clearly fails, stop deep reasoning and do not forward.
- Do not match by keywords alone. Identify whether each item is an actual
  product/business, an ad channel, an analytics tool, or a conversion page.
- Facebook, Instagram, TikTok, Google Ads, Meta Ads, AppLovin, YouTube,
  小红书, 快手, 巨量, 广点通, ASA, Twitter/X, and similar items are ad/media
  channels unless the resume separately proves the actual product was a
  qualifying social app.
- If a candidate fits another open JD better, rematch to that JD and forward
  only when all hard requirements pass.

Reference product categories:

- 1v1 social / random matching: Azar, LivU, Chamet, OmeTV, Monkey, CooMeet,
  Bermuda, Holla, Tango.
- Live social: BIGO LIVE, MICO, Tango, LiveMe, or clearly named live-social
  products.
- Voice-chat / voice-room: Yalla, Yalla Ludo, HelloTalk, Litmatch, Soul,
  SoulChill, TIYA, Discord voice, Clubhouse, Stereo.
- AI social / AI companion: Character.AI, Replika, Nomi.AI, Kindroid, Chai,
  Janitor AI, Candy AI, Talkie, Poly.AI, TIYA.

## Forwarding Policy

- When a candidate satisfies every hard requirement for the current job,
  forward the resume directly in BOSS to `HR`.
- Fixed recipient: `HR`.
- Click the visible `HR` option directly when available. Do not type
  `HR` as the default search path; use it only as identity verification.
- Suitable candidates are forwarded directly in BOSS to `HR`.
- Hard-fail candidates are not forwarded.
- Before final forwarding, verify the selected recipient and confirm the message
  box is empty/untouched.

## Browser And Safety Rules

- Use only the already visible BOSS browser/session.
- Do not open or close browser windows, tabs, apps, or BOSS pages unless the
  current step explicitly requires normal in-page navigation.
- Do not use any single visible person name or candidate name to judge page
  health or login state. Treat the current BOSS page as normal only when BOSS
  core navigation such as `职位管理` and `推荐牛人` is visible, and no login,
  CAPTCHA, slider, SMS, security verification, or account abnormality is
  visible. Do not refresh more than once in the same run.
- Click candidate names only; never click avatars.
- Never click candidate controls: `打招呼`, `举报`, `不合适`, `收藏`.
- Never click job controls: `删除`, `复制`, `保存并发布`, `关闭`, or job-state
  controls.
- Before state-changing BOSS clicks, confirm screenshot position, accessibility
  text, and page layer agree.
- Stop on CAPTCHA, slider, SMS verification, security verification, account
  abnormality, ambiguous UI, or login failure.

## Feishu Notification Policy

Routine notices are ordinary group notices and do not @ 钟苗:

- Start: `现在开始工作`
- End: `到点了，下班！`

Notify 钟苗 only for blockers/faults:

- Missing JD: `jd库里没有xxx岗位的jd，请提供。`
- Login/security abnormality: `boss登陆异常，请检查～`
- Failed startup: `BOSS筛选任务未正常启动，请检查～`
- Runtime fault:

```text
流程故障，故障如下
<具体故障原因、当前步骤、岗位/候选人（如有）、已停止的操作>
```

Only real faults/blockers require a screenshot and 钟苗 notification. Normal
end notices and BOSS purchase-limit quota end notices do not include screenshots.

If a visible ordinary logged-out page shows the upper-right `登录`, click it
only when no CAPTCHA/slider/SMS/security/account abnormality is visible. Send
the QR screenshot to 钟苗 with `请扫码登陆`; retry up to 3 times, 15 seconds apart.

## Reports

- Daily report: every day `09:00`, previous day, aggregate only.
- Weekly report: Monday `08:00`, previous Monday-Sunday, aggregate only.
- Reports read SQLite and persist to SQLite `reports`.
- Visible reports must not include candidate names, code, commands, raw paths,
  raw internal data, or local cache mechanics.

## Output

Report only high-signal operational state:

- current step and child skill;
- current job and candidate batch count;
- SQLite DB path and useful row ids;
- duplicate/prefilter/hard-gate/forwarding outcome;
- safety stop or Feishu notification result.
