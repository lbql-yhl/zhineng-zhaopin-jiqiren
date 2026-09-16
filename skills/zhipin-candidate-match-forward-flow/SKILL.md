---
name: zhipin-candidate-match-forward-flow
description: Use on BOSS/Zhipin 推荐牛人 when one recommended candidate should be opened, fully read into SQLite, kept open, checked against the user-provided JD hard requirements, and if all hard requirements pass directly forwarded in BOSS to 张女士 without Feishu approval.
---

# Zhipin Candidate Match Forward Flow

Use this skill after:

1. The user-provided JD library has the target job in SQLite.
2. `zhipin-recommend-job-select` has selected the same job in `推荐牛人`.

## Goal

Process exactly one recommended candidate at a time:

```text
打开 1 个候选人在线简历 -> 完整读取并入库 -> 保持在线简历页面打开 -> 检查 JD 硬性条件 -> 全部满足直接 BOSS 转发给张女士；任一硬性条件缺失只进入次日 09:00 工作日报聚合统计
```

## Absolute Red Lines

- Never click `打招呼`, `不合适`, `收藏`, or `举报`.
- Never send a BOSS message to the candidate.
- When a candidate satisfies every hard requirement for the current job, forward
  the resume directly in BOSS to `张女士` / `张晓珠`.
- Do not ask 钟苗 for A/B forwarding approval.
- The forwarding recipient is fixed: `张女士` in BOSS, real name `张晓珠`.
- Never forward before the current candidate resume has been fully read, stored
  in SQLite, and matched against the SQLite JD.
- Never process multiple candidates in one run of this skill.
- Before opening a candidate, check SQLite `processed_candidates` by
  `job_ref + candidate_ref`. If already processed, skip it.
- After the current candidate is fully processed, write/update
  `processed_candidates` with final status, hard-gate result, note, and processed time.
- Do not force context compression after every candidate. The parent pipeline
  compresses after every 5 handled candidates, and immediately on successful
  forwarding, job switch, fault, blocker, or safety stop.

## One Candidate Rule

Each run handles only the currently selected or next chosen candidate.

Do not close the online resume immediately after reading. Keep it open after
storing so the same opened resume page can be used for the later `转发` action.

If the candidate misses any hard requirement, close the online resume with the
allowed resume-detail top-right `X`, keep only aggregate report data in SQLite,
and return to the recommendation list.

## Context Compression Checkpoint

At the end of this one-candidate run, update the lightweight batch counter. A
compact handoff summary is required only when this candidate completes a batch
of 5 handled candidates, or when this candidate is forwarded, triggers a job
switch, or hits a fault/blocker/safety stop. Include:

- job ref and selected recommendation job;
- candidate ref and normalized duplicate key;
- duplicate-check result before opening;
- resume row id, match row id, processed-candidate row id;
- hard-gate decision and whether BOSS forwarding ran;
- forwarding recipient and forwarding record id if applicable;
- current browser/page state and the next intended candidate/job;
- any red-line stop, ambiguity, or user action needed.

For ordinary duplicate skips and hard-requirement failures, defer compression
until the 5-candidate batch checkpoint unless a safety condition appears.

## Workflow

### 1. Open and Read One Candidate

Use `zhipin-recommend-candidate-resume-read` in single-candidate keep-open mode:

- click only the candidate name or clear read-only profile entry;
- fully scroll the online resume detail to the bottom;
- ignore `其他相似经历的牛人`, `相似经历`, `相似牛人`, and other similar-candidate
  recommendation blocks;
- store the complete current-candidate online resume in SQLite;
- record that the resume is intentionally left open for match/forward review;
- do not click the top-right `X` yet.

### 2. Match Against JD

Use `zhipin-archive-jd-resume-match` with SQLite `job_ref` and `candidate_ref`.
Before matching, read `sqlite_store.py get-jd-hard-gates --job-ref "<job_ref>"`
and follow the returned `decision_plan`: age, education, then product, region,
and year gates. Once any hard gate clearly fails, stop deep reasoning, write the
missing hard-gate result, and do not forward.

Before forwarding, verify all of the following:

- SQLite has the target job in the user-provided JD library, or a user-approved
  manual JD replacement;
- SQLite has the current opened candidate resume row;
- the match row belongs to the same `job_ref + candidate_ref`;
- `hard_pass` is true;
- `decision_tier` is `BOSS_FORWARD_ZHANG`.

Do not use guessed or placeholder hard-gate results for a real BOSS forwarding
flow.

Decision:

- If any hard requirement is missing, record the hard-requirement result, keep
  minimal candidate information for later dedupe, close the online resume with
  the allowed detail `X`, and stop.
- If all hard requirements pass, continue directly to BOSS forwarding to `张女士`.

### 3. Forward in BOSS

Prefer the Codex-supported Chrome plugin on the user's existing Google Chrome session for the already opened online resume page. Use Computer Use only as a fallback when the Chrome plugin is unavailable, blocked, or visible-screen interaction is required.

Allowed operation:

- click `转发`;
- in the new forwarding page/dialog, click the visible `张女士` option directly
  when it appears in recent contacts or the recipient list;
- do not type `张晓珠` into the search box as the default path. `张晓珠` is only
  an identity alias for verifying that the selected `张女士` is the correct
  person;
- click only that recipient option;
- before any final send/confirm action, verify the selected recipient name
  exactly matches `张女士` or confirmed alias `张晓珠`.

If the candidate passes all hard requirements, click the final `转发` to send the
resume directly in BOSS to `张女士` / `张晓珠`.

Recipient selection:

- Click `张女士` directly when visible.
- `张晓珠` = `张女士`, but use it only as an alias for verification, not as the
  default typed search term.

Final pre-click checklist:

```text
1. 当前候选人已满足全部用户提供 JD 硬性要求。
2. 选中的 BOSS 站内同事是 `张女士` 或 `张晓珠`。
4. 页面不会给候选人发送消息。
5. 当前候选人仍是本次匹配结果对应的候选人。
```

Stop and ask the user if:

- `张女士` / `张晓珠` is not visible;
- multiple identical names appear and cannot be distinguished;
- the UI asks for additional confirmation not covered by this skill;
- forwarding would also send a candidate-facing message;
- the online resume page has closed or changed unexpectedly.

## Output

Always report:

- SQLite database path;
- job ref;
- candidate ref;
- resume row id;
- match row id;
- processed-candidate duplicate/add/update status;
- fixed recipient `张女士` / `张晓珠`, if forwarded;
- whether BOSS forwarding was executed;
- if not executed, the exact reason.
