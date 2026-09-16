---
name: zhipin-weekly-work-report
description: "Use for BOSS/Zhipin weekly work reports: every Monday at 08:00 summarize the previous week's run status, risk controls, token usage, global resume funnel, job-level hard-requirement pass/fail bands, XiaoZhao insights, and send an ordinary Feishu group report without operating BOSS."
---

# Zhipin Weekly Work Report

Use this skill to create the weekly BOSS/Zhipin work report and send an
ordinary Feishu group notification.
It is the weekly counterpart of `zhipin-scheduled-forward-report`.

## Goal

Every Monday at 08:00, summarize the previous calendar week and send the report
to the Feishu group without at-mentioning 钟苗. Notify 钟苗 only when the weekly
report detects a fault or blocker.

The report is for HR reading. Do not include code, commands, internal data
snippets, stack traces, raw paths, or implementation details in the Feishu
visible body.

## Inputs

Read the local SQLite index only:

```text
.zhipin-copilot/recruitment.sqlite3
```

Do not open or operate BOSS.

## Weekly Report Window

- Run every Monday at `08:00`.
- Report on the previous Monday through previous Sunday.
- Use local machine time / China timezone semantics.
- If there is no previous-week data, still send a short weekly report stating
  that no screening records were found.
- Never send an old weekly report body directly just because it already exists
  in SQLite. Existing `reports` rows are only drafts or retry references.
- The weekly report must follow the latest daily report format exactly, with
  only the period wording changed from today/daily to last-week/weekly.
- Always rebuild or revalidate the weekly report from the current SQLite source
  tables before any human-visible output or Feishu send. Use the smallest
  internally consistent data set: if a metric cannot be reconciled across source
  tables, exclude or clearly downgrade that metric instead of inflating totals.
- All weekly report surfaces must use the same SQLite database and the same
  source rows for the same report period. Local Codex preview, Feishu Q&A,
  scheduled Feishu send, saved `reports.body`, and resend validation must not
  use separate data snapshots, Feishu-side caches, copied summaries, or manually
  edited numbers.
- Only send after the data has been整理清楚: the global total, job breakdown,
  forwarding total, hard-fail total, duplicate count, list-read count, online
  resume metric, and run-time window must each have a stated source and must not
  contradict one another. `上周共筛选候选人` means the candidates read from the
  BOSS recommendation list during the week, not merely rows inserted into a
  daily bookkeeping table.
- If existing `reports` has a `PREPARED` row, compare it with current SQLite
  source tables. Use it only when it still matches the current source data,
  already includes the required run-time window, and already follows the latest
  daily/weekly format; otherwise generate a corrected replacement record before
  sending.
- Do not auto-resend a previously `sent` report unless the user explicitly asks
  to resend that exact report id.
- Before sending, read only SQLite and confirm the previous week's daily
  records, processed candidates, match results, forward records, run events, and
  report-precheck data are queryable.
- If any day in the week ended with residual process, database lock, safety
  stop, missing JD, login/security, or unfinished-candidate state, mark the
  weekly report as interrupted/abnormal and include the aggregate reason.
- Do not reopen or operate BOSS to repair weekly report data. If data is
  missing or inconsistent, write the smallest consistent aggregate weekly report
  available, record the data-quality issue in SQLite, and do not send the report
  as final until the inconsistency is visible and resolved or explicitly
  approved by the user.
- Save the final weekly report body to SQLite `reports` before or at the same
  time as sending the Feishu message.

## Visible Report Format

Use the same structure as the daily report, but change wording to weekly:

This visible report format is user-owned and fixed. The weekly report must
reference the daily report format and only change the period wording from
daily/today to weekly/last week. It is the single source of truth for local
preview, saved SQLite report bodies, scheduled sends, Feishu Q&A, and Feishu
notification content. Do not maintain a second Feishu-only template or a
local-only template. Do not change headings, field order, wording structure, or
add extra fields without explicit user approval.

In Feishu post messages, render the report's visible title and section headings
with hard bold styling: `工作周报：`, numbered section headings, and subsection
headings ending in `：` must use Feishu rich-text bold style. The local Markdown
body remains the same text; only Feishu rich-text rendering adds bold style.

```text
工作周报：
1. 运行状态与风控
- 运行时长与状态：上周运行状态：正常 / 存在中断/异常。（注：若存在中断/异常，需备注原因，如触发验证码等；页面正常以刷新后能看到「职位管理」「推荐牛人」等核心入口为准）
- Token消耗：累计消耗 Token XX

2. 任务完成度与简历质量
- 全局漏斗：
    - 上周共筛选候选人 X 位
    - 硬性条件通过并转发 X 位
    - 硬性条件缺失未转发 X 位
    - 重复候选人 X 位
- 筛选过程全量统计：
    - 去除重复后进入列表预筛 X 位
    - 列表预筛通过 X 位
    - 列表预筛不通过 X 位
      原因：年龄不符合 X 位；学历不符合 X 位
    - 打开在线简历 X 位
    - 列表信息不完整 X 位；问题：无 / 缺少年龄或学历，需打开在线简历确认
- 岗位拆解：
    - [岗位A]
      岗位总数据：X 位；列表读取：X 位
      列表阶段：重复 X 位；列表弃选 X 位；打开在线简历 X 份
      入库候选人：X 位
      结果：硬性条件通过并转发 X 位，占比 X%；硬性条件缺失未转发 X 位
- 岗位不符合原因统计（按候选人去重，记录主因）：
    - [岗位A]：年龄不符合 X位；学历不符合 X位；目标产品/业务经验不符合 X位

3. 小昭洞察与建议
- 画像总结：总结今日/上周候选人的薪资、学历、经验、技能、行业背景等主要分布。
- 未转发原因分析：分析为什么大量候选人没有满足转发条件，例如学历不达标、年龄超限、经验年限不足、核心技能缺失、行业不匹配、薪资期望偏高、简历信息不足等。
- 行动建议：基于未转发原因，给出可执行建议，例如调整 JD 硬性条件、优化岗位薪资范围、补充关键词、扩大/收窄筛选范围、重新校准学历或经验要求。
```

## Counting Rules

- 周报数据和日报数据同属高优先级生产数据，必须多表交叉校验，不能只依赖单表。
- 周报必须参考最新日报格式；日报格式更新时，周报同步更新，只允许把“今日”改成“上周”。
- 这里展示、SQLite 保存、飞书问答、定时飞书发送必须完全一致：同一个 SQLite 数据库、同一批源表记录、同一正文、同一字段顺序、同一统计口径、同一格式校验。禁止为飞书单独维护简化版/旧版模板、单独缓存、手填数字或另一套数据查询。对外可见日报/周报正文不得展示“数据源/数据来源”、数据库路径、内部表名、SQL、脚本名或缓存/链路细节；如需解释口径，只用业务化说明。
- 全局漏斗：`上周共筛选候选人` 必须按上周 BOSS 推荐列表实际读取到的候选人统计，优先使用
  `screening_run_seen_candidates` 与覆盖充分的 `batch_list_prefilter` 事件核对；
  `daily_processed_candidates` 只作为补充校验表，不能在缺少岗位/列表来源信息时单独作为全局总数。
  列表中因年龄或学历不符合而未打开在线简历的候选人也必须计入上周共筛选候选人。
- `硬性条件通过并转发`: 按候选人去重合并 `forward_records.status=SUCCESS`、`processed_candidates.status='forwarded'`、`run_events` 中 `boss_forward_success` / `forward_success` / `boss_forward success`。
- `硬性条件缺失未转发`: 只统计进入预筛/硬性条件判断但未通过转发的候选人，不包含重复候选人。重复候选人必须在全局漏斗中单独展示为“重复候选人”。不得使用 `已筛选候选人总数 - 成功转发人数` 这种会把重复候选人混进去的口径。
- 重复候选人、列表预筛、打开在线简历和岗位总数据使用与日报相同的 SQLite 口径；筛选过程全量统计必须满足 `列表读取 = 重复候选人 + 去除重复后进入列表预筛`，以及 `去除重复后进入列表预筛 = 列表预筛通过 + 列表预筛不通过 + 列表信息不完整`。列表预筛不通过必须写清具体原因；列表信息不完整必须写清哪里有问题。
- 打开在线简历必须按候选人去重统计，不得直接使用事件条数。打开在线简历是列表读取候选人的后续子集，正常情况下不得大于上周共筛选候选人；若因历史事件重复、页面重开、补录或多轮日志导致原始事件数更高，只能在内部数据质量问题中记录，不得把事件数写成“打开在线简历 X 位/份”。
- 运行时长与状态必须从周内 SQLite `run_events` 计算运行窗口。优先使用筛选相关事件的最早和最晚 `created_at`，输出具体起止时间和时长；不得只写“正常”或“存在异常”而省略运行时长。
- Report aggregate counts only. Do not list candidate names in any pass/fail band.
- Do not include per-candidate match points, risks, or hard-fail
  reasons.
- Job breakdown must group by a normalized job identity, not raw `job_ref`.
  Treat separator and case variants such as `ui设计师-广州-11-18k` and
  `ui设计师 | 广州 | 11-18K` as the same job. Each job line must include job total candidates, list-read candidates, duplicates, list-stage skips, opened online resumes, stored candidates, forwarded candidates, and not-forwarded candidates.
- 未转发原因分析：详细分析候选人没有满足转发条件的主要原因，例如学历不达标、年龄超限、经验年限不足、核心技能缺失、行业不匹配、薪资期望偏高、简历信息不足等；对外输出保持简短，不展开长篇明细。
- 行动建议：只给整体建议，不按岗位拆分。
- Token usage uses the local machine's Codex total for each calendar day in the
  report window: sum `~/.codex/sessions/YYYY/MM/DD/*.jsonl`
  last `event_msg` with `payload.type=token_count` for each day, using `payload.info.total_token_usage.total_tokens`, then aggregate the week. Do not
  use Hermes credential pool quota, account limits, Feishu split totals, or
  per-flow partitions.

## Feishu Notification

- Routine weekly reports are ordinary Feishu group messages and must not
  at-mention 钟苗.
- Feishu-visible weekly reports must pass the same latest-format check as daily
  reports before sending. If the body is old-format or the core metrics
  contradict one another, do not send it as final.
- Fault, blocker, login/security abnormality, missing JD-library evidence, or
  failed-start notices should notify 钟苗 through Feishu using a real at-mention.
- Default 钟苗 open_id: `ou_606d3c2906e2fb2529d64d87308e912c`.
- Default report chat_ids: `oc_606e61cfefd9cfb4b88409f0a480ad1d`（招聘AI智能体优化-小昭） and `oc_7e0ab0f30306c580726cd38bdcdff31c`（AI-Infra业务团队）。AI-Infra业务团队只接收日报/周报，不承接 JD、问答、流程指令、反馈或其他机器人功能。
- Credentials come from `FEISHU_APP_ID` / `FEISHU_APP_SECRET` or
  `~/.hermes/.env`.

## Login And Verification Red Line

If local records show re-login, verification code, slider verification, SMS,
security verification, account abnormality, or similar BOSS risk during the
week, mark the weekly report as interrupted/abnormal and notify 钟苗 with:

```text
boss登陆异常，请检查～
```

Do not operate BOSS from this weekly report skill.

## Output

Persist the weekly report body and summary data in SQLite `reports`. If a
human-readable copy is explicitly requested, write Markdown under:

```text
.zhipin-copilot/reports/weekly/
```

Suggested export filename:

```text
work-weekly-YYYY-MM-DD_to_YYYY-MM-DD.md
```

Return the SQLite database path, report row id, any optional human-readable
report paths, and the Feishu notification result.
