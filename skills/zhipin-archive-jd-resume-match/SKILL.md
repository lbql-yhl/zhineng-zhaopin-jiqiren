---
name: zhipin-archive-jd-resume-match
description: Use after an HR-provided JD is in SQLite and the current candidate has been read live or minimally indexed, to analyze whether the candidate satisfies the JD hard requirements. Candidates who satisfy every hard requirement are marked for BOSS forwarding to 张女士; every handled candidate keeps minimal SQLite information for later dedupe.
---

# Zhipin SQLite Hard Requirement Match

Use this skill after the user-provided JD library is in SQLite and
`zhipin-recommend-candidate-resume-read` has either read the current resume live
or stored a minimal candidate index row. Full resume text is not required and
must not be persisted.

## Goal

Analyze whether the candidate is suitable according to the HR-provided JD hard
requirements. Missing direct evidence means the hard requirement is not
satisfied.

## Boundaries

- Read the user-provided JD from the local SQLite index and use the current
  live resume evidence from the browser step when needed.
- Write only lightweight SQLite match and processed-candidate records.
- Do not open or operate BOSS in the browser.
- Do not send messages or change candidate state.
- Do not use age except where the user-provided JD explicitly sets a hard age
  requirement.
- HR keeps final decision authority; the skill only gives an assistant
  judgment.

## Default Input

```text
.zhipin-copilot/recruitment.sqlite3
job_ref
candidate_ref
```

Use the bundled script:

```bash
python3 /Users/helloworld/.codex/skills/zhipin-archive-jd-resume-match/scripts/match_archived_jd_resume.py \
  --job-ref "<job_ref>" \
  --candidate-ref "<candidate_ref>"
```

The match record writes only concise decision data:

- `matches` row with `decision_tier`, hard-pass result, short matched reason,
  short missing reason, summary, and risk fields. no score field is created
  because scoring is disabled.
- `processed_candidates` row for duplicate checking and candidate lifecycle,
  including candidate name, age, education, status, and short note.

## Decision Tiers

| Hard requirements | Tier | Action |
| --- | --- | --- |
| All satisfied | `BOSS_FORWARD_ZHANG` | BOSS station-forward directly to 张女士 / 张晓珠 |
| Any missing hard requirement after opened resume | `REJECT_DAILY_REPORT` | Record the hard-requirement result and keep minimal candidate information for dedupe |

## Built-In User-Provided JD Library

Only the user-provided JD library is valid for matching. Old BOSS-page JD
records must be deleted and must not be used.

- `运营负责人`: overseas Middle East region responsibility for 1+ years; voice
  chat or voice-room business; 2+ years overseas Middle East operations
  experience; college degree or above; age under 35.
- `海外广告优化师（双休）` / `高级海外广告优化师`: overseas-region experience; 1+ years advertising or
  optimization experience for at least one of 1v1 social app, live social app,
  voice-chat app, voice-room app, or AI social app; college degree or above;
  age under 35.
- `Ui设计师`: 1+ years social-app UI design experience for at least one of live
  social app, voice-chat app, voice-room app, or AI social app; college degree
  or above; age under 32.

## Matching Rules

- Candidate resumes must satisfy every hard requirement above.
- Read `get-jd-hard-gates` and follow the returned `decision_plan`: age and
  education first, then product, region, and year gates. Once any hard gate
  clearly fails, stop deep reasoning. Do not keep analyzing extra advantages.
- Missing direct resume evidence means the hard requirement is not satisfied.
- Do not compensate for a missing hard requirement with keyword overlap,
  unrelated experience, or subjective strength.
- Negated statements such as `没有语聊经验` or `未负责中东地区` do not count as
  positive evidence.
- Salary and other visible observations can be written as risk points, but they
  do not replace the hard-requirement decision unless HR adds them as hard
  requirements.
- Ignore bottom sections for other people, including `其他名校毕业的牛人` and
  similar-candidate information.
- Never use the phrase `待确认` in risk output.
- Do not write full resume text, full work history, project lists, long raw
  evidence, forwarding recommendation reasons, or forwarding risk notes into
  SQLite. Keep reasoning only long enough to decide pass/fail.

## Output

Return:

- candidate ref and candidate name if available;
- job ref;
- decision tier;
- hard-pass result;
- top advantages / matched evidence;
- risks or missing hard requirements;
- SQLite database path;
- SQLite match id;
- processed-candidate row id and status.
