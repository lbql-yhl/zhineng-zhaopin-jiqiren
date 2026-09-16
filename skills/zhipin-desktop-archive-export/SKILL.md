---
name: zhipin-desktop-archive-export
description: Use when exporting SQLite-stored BOSS/Zhipin open-job JDs and recommended-candidate resumes into a job-grouped desktop folder for human review.
---

# Zhipin Desktop Archive Export

Use this skill only when the user wants human-readable files on the Desktop.
Normal screening stores JD, resume, match, forwarding, and report data in
SQLite instead of local archive files.

## Boundaries

- Work only with the local SQLite index.
- Do not touch the browser.
- Do not upload resume or JD data externally.
- Keep sensitive contact details minimized unless the user explicitly asks for
  full details.
- Do not delete or mutate SQLite source records while exporting.

## Default Paths

Read from:

```text
.zhipin-copilot/recruitment.sqlite3
```

Export to:

```text
~/Desktop/zhipin-recommend-archive/
```

Use a user-specified export path when provided.

## Folder Structure

```text
zhipin-recommend-archive/
└── <job-title>/
    ├── JD.md
    ├── candidates.md
    └── matches.md
```

## Workflow

1. Read jobs, resumes, and matches from SQLite.
2. Group resumes and matches by `job_ref`.
3. Create one folder per job.
4. Export human-readable Markdown summaries.
5. Return the export path and counts.

## Output

Return plain text fields:

```text
database_path=.zhipin-copilot/recruitment.sqlite3
export_path=<导出目录>
exported_at=<导出时间>
jobs_count=<岗位数量>
candidates_count=<候选人数量>
group_1=<岗位名> | <候选人数> | <文件夹路径>
warnings=<如有>
```
