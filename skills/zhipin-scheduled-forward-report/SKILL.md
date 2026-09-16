---
name: zhipin-scheduled-forward-report
description: "Use for BOSS/Zhipin daily work reports: summarize run status, risk controls, token usage, global resume funnel, job-level hard-requirement pass/fail bands, XiaoZhao insights, and send an ordinary Feishu group report at 09:00 without operating BOSS."
---

# Zhipin Daily Work Report

Use this skill after the BOSS/Zhipin screening flow has produced local match
results and operation records.

## Goal

Create a daily work report for the previous calendar day and send an ordinary
Feishu group notification. Do not at-mention 钟苗 for routine reports; notify
钟苗 only when the report detects a fault or blocker.

The report must be written for HR reading. Do not include code, commands,
internal data snippets, stack traces, raw paths, or implementation details in
the Feishu visible body.

## Fixed HR Rules

- 不再做评分，不按分数转发。
- 候选人必须满足用户提供 JD 的全部硬性条件才允许 BOSS 转发。
- 硬性条件全部满足：直接 BOSS 转发给 `张女士` / `张晓珠`，不需要飞书 A/B 审批。
- 硬性条件全部满足并已转发：计入日报漏斗中的 `硬性条件通过`。
- 历史 `UNSUITABLE_REVIEW` 记录仍属于硬性条件缺失，不计入 `硬性条件通过并转发`。当前流程中任一硬性条件缺失均不转发，计入日报漏斗中的 `硬性条件缺失`。
- 根据 HR 提供 JD 的硬性要求分析判断是否合适，缺少直接证据就视为硬性条件未满足。

## Inputs

Read the local SQLite index only:

```text
.zhipin-copilot/recruitment.sqlite3
```

Do not open or operate BOSS.

## Daily Report

At 09:00, summarize the previous calendar day's work.

Before sending, run a report readiness check:

- Never send an old report body directly just because it already exists in
  SQLite. Existing `reports` rows are only drafts or retry references.
- Always rebuild or revalidate the target day's report from the current SQLite
  source tables before any human-visible output or Feishu send. Use the smallest
  internally consistent data set: if a metric cannot be reconciled across source
  tables, exclude or clearly downgrade that metric instead of inflating totals.
- All report surfaces must use the same SQLite database and the same source rows
  for the same report period. Local Codex preview, Feishu Q&A, scheduled Feishu
  send, saved `reports.body`, and resend validation must not use separate data
  snapshots, Feishu-side caches, copied summaries, or manually edited numbers.
- Only send after the data has been整理清楚: the global total, job breakdown,
  forwarding total, hard-fail total, duplicate count, list-read count, online
  resume metric, and run-time window must each have a stated source and must not
  contradict one another. `今日共筛选候选人` means the candidates read from the
  BOSS recommendation list, not merely rows inserted into a daily bookkeeping
  table.
- If existing `reports` has a `PREPARED` row, compare it with current SQLite
  source tables. Use it only when it still matches the current source data and
  already includes the required run-time window; otherwise generate a corrected
  replacement record before sending.
- Do not auto-resend a previously `sent` report unless the user explicitly asks
  to resend that exact report id.
- Read only SQLite and confirm the previous day's run events, processed
  candidates, match results, forward records, and report-precheck data are
  queryable.
- If the previous screening task ended with residual process, database lock,
  safety stop, missing JD, login/security, or unfinished-candidate state, mark
  the daily report as interrupted/abnormal and include the reason in aggregate
  form.
- Do not reopen or operate BOSS to repair missing report data. If data is
  missing or inconsistent, write the smallest consistent aggregate report
  available, record the data-quality issue in SQLite, and do not send the report
  as final until the inconsistency is visible and resolved or explicitly
  approved by the user.
- If no prepared record exists, generate the best available aggregate report
  from SQLite, save it to `reports`, and then send. Never reopen BOSS to repair
  missing report data.
- Save or update the final daily report body in SQLite `reports` before or at
  the same time as sending the Feishu message, so retries do not require
  recalculation from BOSS.

Use this exact visible structure in the Feishu daily report and Markdown report:

This visible report format is user-owned and fixed. It is the single source of
truth for local preview, saved SQLite report bodies, scheduled sends, Feishu
Q&A, and Feishu notification content. Do not maintain a second Feishu-only
template or a local-only template. Do not change headings, field order, wording
structure, or add extra fields without explicit user approval.

In Feishu post messages, render the report's visible title and section headings
with hard bold styling: `工作日报：`, numbered section headings, and subsection
headings ending in `：` must use Feishu rich-text bold style. The local Markdown
body remains the same text; only Feishu rich-text rendering adds bold style.

```text
工作日报：
1. 运行状态与风控
- 运行时长与状态：今日运行状态：正常 / 存在中断/异常。（注：若存在中断/异常，需备注原因，如触发验证码等；页面正常以刷新后能看到「职位管理」「推荐牛人」等核心入口为准）
- Token消耗：累计消耗 Token XX

2. 任务完成度与简历质量
- 全局漏斗：
    - 今日共筛选候选人 X 位
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

The report body and all summary data must be saved in SQLite `reports`. A
Markdown copy is optional only when the user explicitly asks to export a
human-readable file. The Feishu visible body must not include code.

Field guidance:

- 运行状态：不要使用任何单个人名或候选人姓名判断页面是否正常，也不要靠反复刷新判断健康；
  当前 BOSS 页面能看到 `职位管理`、`推荐牛人` 等 BOSS 核心入口，且没有登录、验证码、
  滑动验证、短信验证、安全验证或账号异常提示，就按页面正常处理。
- 若存在中断/异常，必须写清原因，例如验证码、滑动验证、登录失效、安全验证、页面异常。
- 运行时长与状态：必须从当天 SQLite `run_events` 计算运行窗口。优先使用筛选相关事件
  （如 open job/JD check/list prefilter/online resume/hard gate/forward/job
  switch/checkpoint）的最早和最晚 `created_at`，输出具体起止时间和时长；如果只能得到
  自动化启动/检查事件，也必须说明该时长口径。不得只写“正常”或“存在异常”而省略运行时长。
- Token消耗：直接使用本机 Codex 当天总消耗，统计
  `~/.codex/sessions/YYYY/MM/DD/*.jsonl` 中
  当天最后一条 `event_msg` 且 `payload.type=token_count` 的 `payload.info.total_token_usage.total_tokens`，作为当天 Codex 累计消耗。不要使用 Hermes
  credential pool、账号额度、飞书分项或 BOSS 流程分项来替代日报 Token 消耗。
- 全局漏斗：`今日共筛选候选人` 必须按当天 BOSS 推荐列表实际读取到的候选人统计，优先使用
  `screening_run_seen_candidates` 与覆盖充分的 `batch_list_prefilter` 事件核对；
  `daily_processed_candidates` 只作为补充校验表，不能在缺少岗位/列表来源信息时单独作为全局总数。
  列表中因年龄或学历不符合而未打开在线简历的候选人也必须计入今日共筛选候选人。
- 日报数据是高优先级生产数据，生成和发送前必须多表交叉校验，不能只依赖单表。若任一核心口径不一致，必须先按最小一致口径重算并记录数据质量问题；不得把未经核对或互相矛盾的日报发到飞书。
- 这里展示、SQLite 保存、飞书问答、定时飞书发送必须完全一致：同一个 SQLite 数据库、同一批源表记录、同一正文、同一字段顺序、同一统计口径、同一格式校验。禁止为飞书单独维护简化版/旧版模板、单独缓存、手填数字或另一套数据查询。对外可见日报/周报正文不得展示“数据源/数据来源”、数据库路径、内部表名、SQL、脚本名或缓存/链路细节；如需解释口径，只用业务化说明。
- `硬性条件通过并转发`：按候选人去重合并 `forward_records.status=SUCCESS`、`processed_candidates.status='forwarded'`、`run_events` 中 `boss_forward_success` / `forward_success` / `boss_forward success`，但必须排除 `forward_records.note` 或 `run_events.note` 以 `UNSUITABLE_REVIEW` 开头的历史不合适复核转发。历史不合适复核转发仍属于硬性条件缺失，飞书日报和本地日报必须使用同一合并口径。
- `硬性条件缺失未转发`：只统计进入预筛/硬性条件判断但未通过转发的候选人，不包含重复候选人。重复候选人必须在全局漏斗中单独展示为“重复候选人”。不得使用 `已筛选候选人总数 - 成功转发人数` 这种会把重复候选人混进去的口径；也不得因为 `forward_records` 缺记录就把已转发候选人算成未转发。
- 重复候选人：优先读取 `screening_run_seen_candidates.status='duplicate_global'` 与同轮重复状态；若有 `batch_list_prefilter` 结构化事件，只有当其覆盖数不低于 seen 表时才使用批次事件口径。
- 筛选过程全量统计：列表读取、重复候选人、去除重复后进入列表预筛、列表预筛通过、列表预筛不通过来自 `screening_run_seen_candidates` 和 `batch_list_prefilter`。必须满足 `列表读取 = 重复候选人 + 去除重复后进入列表预筛`，以及 `去除重复后进入列表预筛 = 列表预筛通过 + 列表预筛不通过 + 列表信息不完整`。列表预筛不通过必须写清具体原因，如年龄不符合、学历不符合；列表信息不完整必须写清哪里有问题，如缺少年龄或学历，不能只写“待确认”。打开在线简历必须按候选人去重统计，不得直接使用事件条数。打开在线简历是列表读取候选人的后续子集，正常情况下不得大于今日共筛选候选人；若因历史事件重复、页面重开、补录或多轮日志导致原始事件数更高，只能在内部数据质量问题中记录，不得把事件数写成“打开在线简历 X 位/份”。
- 岗位拆解：按规范化岗位身份统计。每个岗位必须展示“岗位总数据、列表读取、重复、列表弃选、打开在线简历、入库候选人、转发、未转发”。其中岗位总数据等于列表读取人数，不能再与打开在线简历相加；打开在线简历只是列表读取候选人的后续过程指标。`ui设计师-广州-11-18k` 和 `ui设计师 | 广州 | 11-18K` 这类分隔符、大小写差异必须合并为同一个岗位。
- 岗位不符合原因统计：优先用 `processed_candidates` 最终状态和 note，按岗位+候选人去重，只记录主因；旧数据缺少最终原因时，才回退 `run_events` 中 hard gate 失败事件。禁止输出含糊兜底分类，必须判断清楚候选人不满足哪一项硬性条件。原因分类至少包括年龄不符合、学历不符合、目标产品/业务经验不符合、广告投放经验不符合、中东/海外区域经验不符合、相关经验年限不足；若原始 note 不够结构化，也必须按岗位硬性条件归到具体方向，例如目标社交/直播/语聊/AI社交产品UI经验不符合、目标海外社交/直播/语聊/AI社交广告投放经验不符合、中东/海外运营及语聊项目经验不符合。若出现未配置岗位映射，必须先补充映射规则再对外发送日报。
- 未转发原因分析：基于岗位不符合原因统计汇总输出，避免直接输出英文原始 note 或长篇明细。
- 小昭洞察与建议：由 Agent 根据薪资风险、学历分布、技能缺口、岗位转发表现生成，不要堆原始数据。
- 行动建议：只给整体建议，不按岗位拆分。
- 不要使用 `待确认`。

## Login And Verification Red Line

If the BOSS page shows re-login, verification code, slider verification, SMS,
security verification, account abnormality, or any similar control:

1. Stop all BOSS operations immediately.
2. Do not click, drag, type, refresh, open, or close browser pages.
3. Notify 钟苗 through Feishu with a real at-mention and exactly:

```text
boss登陆异常，请检查～
```

4. Record the blocked state locally.

Only fault/blocker notices use a real at-mention for 钟苗. Do not notify
candidates.

Routine daily reports are sent to both `oc_606e61cfefd9cfb4b88409f0a480ad1d`
（招聘AI智能体优化-小昭） and `oc_7e0ab0f30306c580726cd38bdcdff31c`
（AI-Infra业务团队）. AI-Infra业务团队 is report-only: it only receives daily
and weekly reports, and must not handle JD, Q&A, flow commands, feedback, or
other XiaoZhao bot functions.

## Output Paths

Persist reports in SQLite `reports`. If a human-readable copy is explicitly
requested, write Markdown under:

```text
.zhipin-copilot/reports/daily/
```

Suggested export filename:

```text
work-daily-YYYY-MM-DD.md
```

Return the SQLite database path, report row id, any optional human-readable
report paths, and the Feishu notification result.

## Red Lines

- Do not click BOSS controls.
- Do not handle verification code or slider verification.
- Do not include code in the daily report visible body.
- Do not send any candidate-facing message.
- Do not use protected attributes for ranking.
- Do not say salary risk auto-rejects or auto-deducts.
- Do not use `待确认` in BOSS forwarding risk text; use concrete risk wording.
