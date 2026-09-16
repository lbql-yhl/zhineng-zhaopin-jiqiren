---
name: zhipin-recommend-job-select
description: Use after a target BOSS/Zhipin open job is confirmed, to enter 推荐牛人 and select the same job for candidate recommendations.
---

# Zhipin Recommend Job Select

Use this skill after the target open job has been selected from `职位管理 -> 开放中`.

## Boundaries

- Prefer the Codex-supported Chrome plugin on the user's existing Google Chrome session. Use Computer Use only as a fallback when the Chrome plugin is unavailable, blocked, or visible-screen interaction is required.
- Only navigate to 推荐牛人 and select the matching open job.
- Do not greet, message, invite, favorite, reject, exchange contact information, or change candidate state.
- Do not select a job unless its visible title and other available evidence match the target open job.
- Stop on login, CAPTCHA, SMS, security verification, account abnormality, or ambiguous candidate/job-affecting UI.

## Matching Rules

Match the target job conservatively using visible evidence:

1. exact job title;
2. city/workplace if visible;
3. salary range if visible;
4. job status/open availability if visible.

If multiple jobs still match, return `need_review` and ask the user to choose.

## Workflow

1. Focus BOSS/Zhipin in Google Chrome.
2. Enter `推荐牛人` using visible navigation.
3. Open the job selector/filter if needed.
4. Select the job that matches the target open job.
5. Verify the recommendation list is filtered for the selected job.

## Output

Return plain text fields:

```text
target_job_ref=<目标岗位身份>
selected_job_ref=<已选择岗位身份>
selected_job_title=<已选择岗位名称>
selection_status=success|need_review|blocked
candidate_list_visible=yes|no
stop_reason=<如有>
```

## Next Step

Use `zhipin-recommend-candidate-resume-read` for each visible recommended candidate that the user wants to review.
