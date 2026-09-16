# Hermes Cron Reference

这些命令是迁移到 Hermes cron 时的参考，不会由安装脚本自动启用。

## 周一到周六流程

```bash
hermes cron create "0 8 * * 1-6" \
  --name "小昭招聘机器人2.2 周一到周六流程" \
  --skill xiaozhao-robot-2 \
  --workdir "/path/to/workspace" \
  "使用 /xiaozhao-robot-2 执行周一到周六 08:00-20:00 完整筛选流程。必须使用 openai-codex/gpt-5.5 绑定、SQLite-only 数据规则、安全红线和候选人全局去重。"
```

## 周日流程

```bash
hermes cron create "0 19 * * 0" \
  --name "小昭招聘机器人2.2 周日流程" \
  --skill xiaozhao-robot-2 \
  --workdir "/path/to/workspace" \
  "使用 /xiaozhao-robot-2 执行周日 19:00-21:00 筛选流程。星期六不执行。"
```

## 日报流程

```bash
hermes cron create "0 9 * * *" \
  --name "小昭招聘机器人2.2 日报流程" \
  --skill xiaozhao-robot-2 \
  --workdir "/path/to/workspace" \
  "执行日报流程，只读取 SQLite，不打开或操作 BOSS，通过飞书通知钟苗。"
```

## 周报流程

```bash
hermes cron create "0 8 * * 1" \
  --name "小昭招聘机器人2.2 周报流程" \
  --skill xiaozhao-robot-2 \
  --workdir "/path/to/workspace" \
  "执行周报流程，只读取 SQLite，不打开或操作 BOSS，通过飞书通知钟苗。"
```

## 未完成工单日报

```bash
hermes cron create "0 9 * * *" \
  --name "小昭招聘机器人2.2 未完成工单日报" \
  --workdir "/path/to/workspace" \
  "运行 skills/zhipin-boss-recruitment-bot/scripts/unfinished_ticket_report.py，汇总未完成 xq/bug 工单，写入 SQLite reports，并通过飞书真实 at 通知叶海淋。"
```

创建前请先确认 Hermes Gateway / Feishu 小昭绑定为：

```text
provider=openai-codex
model=gpt-5.5
```
