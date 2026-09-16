# MiniMax Code 接入说明

> 历史参考：小昭招聘机器人 2.2 当前运行口径已统一为 `openai-codex / gpt-5.5`。
> 本文仅用于追溯旧 MiniMax Code 接入方式，不作为当前部署要求。

小昭机器人2.0 已接入 MiniMax Code。

## 本机路径

```text
MiniMax Code home: ~/.minimax
MiniMax Code skills: ~/.minimax/skills
小昭入口技能: ~/.minimax/skills/xiaozhao-robot-2/SKILL.md
```

`~/.mavis` 是 `~/.minimax` 的软链接，所以 MiniMax Code agent 配置里的
`~/.mavis/skills` 会读取同一套技能。

## 模型要求

MiniMax Code 应使用：

```text
defaultModel: minimax/MiniMax-M3
```

如果配置仍是 `minimax/MiniMax-M2.7`，真实 BOSS 操作前必须停止并提示模型不匹配。

## 当前小昭技能树

MiniMax Code 侧安装 11 个技能：

```text
xiaozhao-robot-2
zhipin-boss-recruitment-bot
zhipin-recommend-screening-pipeline
zhipin-open-jobs-read
zhipin-recommend-job-select
zhipin-recommend-candidate-resume-read
zhipin-archive-jd-resume-match
zhipin-candidate-match-forward-flow
zhipin-scheduled-forward-report
zhipin-weekly-work-report
zhipin-desktop-archive-export
```

## 使用方式

在 MiniMax Code 里直接说：

```text
使用 xiaozhao-robot-2
```

或：

```text
使用小昭机器人2.0执行日报流程，只读取 SQLite，不打开 BOSS
```

真实 BOSS 操作仍必须遵守小昭2.0安全红线：只使用当前已有 BOSS 页面、先列表预筛年龄学历和查重、点击候选人名字、不点击头像、不处理验证码/滑动验证、安全异常只通知。
