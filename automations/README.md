# Automation Templates

这里保留 8 个自动化任务的导入参考。目标机器上建议用 Codex 自动化界面重新创建，不建议直接覆盖本机 `~/.codex/automations`。

## 任务

| ID | 名称 | 时间 |
| --- | --- | --- |
| boss-1 | 工作日流程 | 周一到周六 08:00 启动，持续到 20:00 |
| boss-2 | 周末流程 | 仅周日 19:00 启动，持续到 21:00 |
| boss-3 | 日报流程 | 每天 09:00 统计前一天 |
| boss-4 | 周报流程 | 每周一 08:00 统计上周 |
| boss-5 | 日报数据预整理 | 每天 23:00 整理当天日报数据 |
| boss-6 | 周报数据预整理 | 每周日 23:30 整理本周周报数据 |
| boss-7 | SQLite 自动备份 | 每天 23:10 生成本机和桌面两份数据库备份 |
| xiaozhao-unfinished-tickets | 未完成工单日报 | 每天 09:00 汇总未完成需求/Bug |

## 导入注意

- 将模板中的 `__TARGET_WORKSPACE__` 替换为目标机器 workspace 路径。
- 主流程以 `$zhipin-boss-recruitment-bot` 技能内的最新规则为准。
- 飞书侧小昭功能以 `skills/xiaozhao-robot-2/SKILL.md` 中的 `Feishu Q&A And Records` 为准。
- 不要把旧机器的绝对路径直接用于新机器。
- 自动化启用前，确认目标机器已配置 Feishu 密钥、Chrome BOSS 登录态和 Codex 权限。
- 2.2 主流程、日报发送和周报发送运行口径为 `openai-codex / gpt-5.5`；
  固定化检查/预整理任务（boss-5、boss-6、boss-7、未完成工单汇总模板）使用 `gpt-5.4`。
  旧 MiniMax 文档仅作历史参考。

## 固定运行守则

- 浏览器控制永久优先使用 Codex 支持的 Chrome 插件控制用户现有 Google Chrome 会话；当 Chrome 插件不可用、被阻断或必须进行可见屏幕交互时，再使用 Computer Use。
  禁止使用 Chrome CDP、Chrome DevTools Protocol、remote debugging、
  `127.0.0.1:9222`、`/json/version`、隐藏浏览器会话或非 Codex 浏览器自动化库。
  CDP 不可用不是故障，不得阻止流程启动。
- 每次主流程开始前必须先检查：当前时间窗口、任务暂停状态、上一轮残留任务、
  SQLite 可用性、BOSS 登录态、页面健康、开放岗位 JD 库。
- 发现上一轮残留进程、数据库锁、未完成浏览器自动化、登录/验证/账号异常或
  歧义 UI 时，不开始筛选，先记录 blocker 并按故障规则通知。
- 每个自动化流程启动后应写入 `automation_runs` 并定期 heartbeat；启动前、
  日报/周报发送前可用 `automation-heartbeat-check` 检查当天流程是否缺失、
  超时或已完成。
- 启动前、日报/周报发送前可用 `health-check` 一次性检查 SQLite integrity、
  关键表、WAL、当天候选人统计和自动化心跳状态。
- 每次主流程结束前必须先完成当前候选人的读取、硬性条件检查、转发或缺失记录。
- 收工前必须写入当天候选人、匹配、转发、处理记录、在线简历查看事件、
  run events 和日报/周报所需统计数据，确保第二日 09:00 日报和周一 08:00
  周报无需重新打开 BOSS 即可准时发送。
- 每天 23:00 必须执行 `boss-5` 日报数据预整理，只读/写 SQLite，不打开 BOSS，
  将当天工作日报聚合正文以 `sent_status=PREPARED` 写入 `reports`。
- 每周日 23:30 必须执行 `boss-6` 周报数据预整理，只读/写 SQLite，不打开 BOSS，
  将本周周报聚合正文以 `sent_status=PREPARED` 写入 `reports`。
- 每天 23:10 必须执行 `boss-7` SQLite 自动备份，只读/写 SQLite 和备份目录，
  默认写入 `data/backups/sqlite/` 与
  `/Users/helloworld/Desktop/小昭机器人2.0/backups/sqlite/`。备份目录禁止放在
  Codex/Hermes 配置、技能、缓存或运行目录下。备份成功后必须发送“SQLite
  自动备份成功”飞书通知，包含本机备份路径、桌面备份路径、integrity 和 sha256；
  该通知不是日报/周报。
- 收工后必须检查残留小昭/BOSS 自动化进程、子命令、未完成浏览器自动化、
  SQLite WAL/lock 和未关闭任务状态。
- 只停止明确属于本次小昭自动化的残留；不得停止无关浏览器、系统、Codex、
  Hermes 或用户进程。无法安全清理时，记录 blocker 并按故障规则通知。
- 如果 GPT/Codex/Hermes 主模型通道无法启动、认证失败、长时间无响应或被确认不可用，
  不继续启动 BOSS 自动筛选；先运行
  `skills/zhipin-boss-recruitment-bot/scripts/risk_feishu_alert.py` 通知程序/管理员。
  该脚本直接调用飞书 OpenAPI，不依赖 GPT。`--fallback-provider deepseek|minimax`
  只作为可选补充说明生成通道；provider 不可用时仍发送固定告警文本。
- 为避免 GPT/Codex 无法启动时无人触发告警，目标机器应安装独立 launchd 监控：
  `bin/install-gpt-codex-monitor.sh /Users/helloworld/Documents/小昭机器人`。
  该监控每 5 分钟运行一次，连续 2 次核心通道异常后直接飞书通知程序/管理员。
- 日报/周报发送前必须先做 SQLite 报表就绪检查和当天自动化心跳检查。数据缺失时，
  不打开 BOSS 补数据；写出当前可用的最佳聚合报表，记录问题并按规则通知。

## crontab 定时任务

本机可用 crontab 直接启用这些模板：

```bash
bin/install-crontab-automations.sh
```

安装脚本会维护 `# BEGIN XIAOZHAO ROBOT AUTOMATIONS` 到
`# END XIAOZHAO ROBOT AUTOMATIONS` 之间的 crontab block，并保留其它既有
crontab 内容。每个任务由 `bin/run-cron-automation.sh` 启动，对应模板位于
`automations/*.toml`。

运行 wrapper 会先在 SQLite `automation_runs` 获取对应流程锁；Hermes 运行期间
每 4 分钟写入一次 heartbeat；任务退出后写入 `COMPLETED` 或 `FAILED`。健康检查由
crontab 每 5 分钟调用一次：

```bash
bin/check-cron-automation-health.sh
```

该检查脚本是一次性脚本，不会在后台驻留。它会检查 crontab block、每个任务入口、
主流程运行窗口内是否有新鲜 heartbeat，以及一次性任务在计划时间后是否有当天记录。
日志默认写入 `~/.hermes/logs/xiaozhao_cron/`。

如果任务 wrapper 检测到流程非 0 退出，或健康检查检测到流程缺失、心跳过期、
飞书发送失败、BOSS 转发相关失败，会立即调用
`skills/zhipin-boss-recruitment-bot/scripts/automation_fault_alert.py` 发送飞书告警。
告警前会运行 `automations/diagnose_automation_fault.py` 做一次本地诊断，检查
crontab、Hermes、飞书网络预检、SQLite 和近期失败事件。相同故障默认 15 分钟冷却，
避免每 5 分钟刷屏；首次发现会立即通知。

告警正文会明确说明 Codex 已接管故障诊断/修复；如果无法通过本地自动诊断确认已恢复，
会通知程序负责人继续处理，恢复前不继续自动筛选。同一类流程/飞书转发故障使用稳定
签名，默认 7 天内只发一次，避免每 5 分钟重复刷屏。

健康检查在 `boss-1` 或 `boss-2` 运行窗口内发现主流程没有 `RUNNING` 心跳时，
会通过 `run-cron-automation.sh` 立即重新拉起对应每日主流程。若 09:00 的日报流程
或未完成工单日报在计划时间后仍没有当天运行记录，也会由健康检查补跑一次。
