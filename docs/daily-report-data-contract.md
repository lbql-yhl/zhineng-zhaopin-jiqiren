# 日报数据契约

日报和周报数据是高优先级生产数据。生成、预整理、发送或人工查询日报时，必须使用 `report_metrics.py` 的统一口径，不得临时手写 SQL 后直接对外发送。

## 核心原则

- 只读 SQLite，不打开或操作 BOSS。
- 所有对外数字必须可由 SQLite 复算。
- 不得只依赖单表。尤其是成功转发，必须合并多条写入路径。
- 本地日报、飞书日报、预整理日报和补发日报必须使用同一口径。
- 飞书日报和周报必须使用富文本 post 样式加粗可见标题和标题行；正文文字、字段顺序、统计口径不得因此分成两套模板。对外可见正文不得展示“数据源/数据来源”、数据库路径、内部表名、SQL、脚本名或缓存/链路细节。
- 发现口径冲突时，先复算并记录数据质量问题，再发送或展示报告。

## 表口径

| 报表字段 | 权威数据源 |
| --- | --- |
| 全局已筛选候选人 | BOSS 推荐列表实际读取人数，优先 `screening_run_seen_candidates`，并与覆盖充分的 `batch_list_prefilter` 事件核对 |
| 岗位入库候选人 | `processed_candidates`，按规范化岗位合并 |
| 成功转发 | 去重合并 `forward_records.status=SUCCESS`、`processed_candidates.status='forwarded'`、`run_events` 中 `boss_forward_success` / `forward_success` / `boss_forward success` |
| 硬性条件缺失未转发 | 进入预筛/硬性条件判断但未通过转发的候选人，不包含重复候选人 |
| 列表读取 | `screening_run_seen_candidates`；若 `batch_list_prefilter` 事件覆盖更完整，可用批次事件 |
| 重复候选人 | `screening_run_seen_candidates.status='duplicate_global'` 和同轮重复状态 |
| 列表预筛弃选 | `screening_run_seen_candidates.status IN ('REJECT_LIST_AGE_PRECHECK','REJECT_LIST_EDUCATION_PRECHECK')` |
| 打开在线简历 | 去重后的列表预筛通过候选人，必须是全局已筛选候选人的子集；用 `online_resume_viewed` / `online_resume_view` 事件交叉校验 |
| 岗位总数据 | 岗位列表读取人数；不得与打开在线简历数相加 |
| 岗位不符合原因 | 优先 `processed_candidates.status/note`，按岗位+候选人去重记录主因；旧数据缺原因时回退 hard gate 事件 |
| 打开在线简历信息 | 不保存完整在线简历明细；只记录 `online_resume_viewed` 事件用于统计 |

## 必须展示

每个岗位必须展示：

- 岗位总数据
- 列表读取
- 重复
- 列表弃选
- 打开在线简历
- 入库候选人
- 硬性条件通过并转发
- 硬性条件缺失未转发

## 禁止事项

- 禁止只看 `forward_records` 判断转发数。
- 禁止把飞书日报和本地日报用不同 SQL 口径生成。
- 禁止直接输出英文原始 note 作为未转发原因分析。
- 禁止在数据不一致时“猜一个数”发出日报。
