# XiaoZhao Robot 2.0 Installed Package

This is the current packaged BOSS/Zhipin HR automation skill set.

## Default Entrypoint

- `xiaozhao-robot-2`

## Internal Execution Package

- `zhipin-boss-recruitment-bot`

## Packaged Child Skills

- `zhipin-recommend-screening-pipeline`
- `zhipin-open-jobs-read`
- `zhipin-recommend-job-select`
- `zhipin-recommend-candidate-resume-read`
- `zhipin-archive-jd-resume-match`
- `zhipin-candidate-match-forward-flow`
- `zhipin-scheduled-forward-report`
- `zhipin-weekly-work-report`
- `zhipin-desktop-archive-export`

## Current Flow Summary

1. Read open jobs.
2. Check user-provided JD library.
3. Select matching recommendation job.
4. Global SQLite duplicate check.
5. List prefilter by hard age and hard education.
6. Open online resume only when needed.
7. Record `online_resume_viewed` immediately after the online resume opens.
8. Scroll online resume to bottom.
9. Match hard requirements only; no score.
10. Forward passing resumes directly to `张女士` / `张晓珠`.
11. When a candidate satisfies every hard requirement for the current job,
    forward the resume directly in BOSS to `张女士` / `张晓珠`.
12. Store only minimal candidate identity data.
13. Use only `推荐牛人 -> 最新`: each open job opens up to 30 online resumes.
14. At workflow startup or recovery, at most one BOSS page refresh/reload is
    allowed to synchronize state. After that single refresh, the same run must
    not refresh or reload the page again.
15. When switching jobs or restarting the job cycle, do not refresh the browser
    page; select the next job from the current page state.
16. There is no separate total daily local quota; do not wait for a forwarding
    quota.
17. Checkpoint every 5 handled candidates or on forwarding/job switch/fault.

## Storage Contract

SQLite is the only persistent data source:

```text
.zhipin-copilot/recruitment.sqlite3
```

Durable candidate data is limited to:

```text
岗位、姓名、年龄、学历
```

Internal dedupe metadata:

- `candidate_key`

Do not persist:

- JSON artifacts
- full resume text
- JD archive files from BOSS normal automation
- match archives
- resume summaries
- work histories
- projects
- skills
- languages
- city
- target role
- salary
- years
- status notes
- skip reasons
- recommendation reasons
- risk notes

## Fixed Notices

- Start: `现在开始工作`
- End: `到点了，下班！`
- Missing JD: `jd库里没有xxx岗位的jd，请提供。`
- Login/security abnormality: `boss登陆异常，请检查～`
- Failed startup: `BOSS筛选任务未正常启动，请检查～`
