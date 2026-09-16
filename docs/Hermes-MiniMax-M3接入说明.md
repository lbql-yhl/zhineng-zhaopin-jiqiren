# Hermes MiniMax-M3 接入说明

> 当前主流程运行口径仍为 `openai-codex / gpt-5.5`。
> MiniMax-M3 已配置在 Hermes 侧作为备用 provider，不切换主模型。

小昭机器人2.0 已提供 Hermes 侧技能和 bundle：

```text
Hermes skill: xiaozhao-robot-2
Hermes bundle: /xiaozhao-robot-2
Bundle skills: 11 个小昭/Zhipin 技能
Provider: minimax
Model: MiniMax-M3
```

## 当前本机检查

Hermes 主模型配置保持：

```text
model.default=gpt-5.5
model.provider=openai-codex
model.base_url=https://chatgpt.com/backend-api/codex
```

Hermes fallback provider 配置：

```text
fallback_providers:
- provider: minimax-cn
  model: MiniMax-M3
  base_url: https://api.minimaxi.com/anthropic
- provider: minimax
  model: MiniMax-M3
  base_url: https://api.minimax.io/anthropic
```

MiniMax API key 配置在 Hermes 本机环境和 credential pool 中；本包不包含任何密钥。

本机已验证：

```bash
hermes -z '只回复：M3_OK' --provider minimax-cn --model MiniMax-M3 --ignore-rules
hermes -z '只回复：M3_OK' --provider minimax --model MiniMax-M3 --ignore-rules
```

两个 smoke test 均可正常返回 `M3_OK`。

## 启动

```bash
/Users/helloworld/Desktop/小昭机器人2.0/bin/start-hermes-minimax-m3.sh
```

或手动运行：

```bash
cd /Users/helloworld/Documents/小昭机器人
hermes --provider minimax --model MiniMax-M3 --skills xiaozhao-robot-2 --tui
```

注意：上述命令是手动指定 MiniMax M3 的备用运行方式，不会修改默认主模型。

## 在 Hermes 里使用

进入 Hermes 后发送：

```text
/xiaozhao-robot-2
```

再输入你要执行的流程，例如：

```text
执行工作日筛选流程，但先只检查启动状态，不操作候选人
```

或：

```text
执行日报流程，只读取 SQLite，不打开 BOSS
```

## 重要边界

- 启动 Hermes 不等于开始操作 BOSS。
- 真实 BOSS 操作前，必须确认当前浏览器、登录态、安全红线和运行时间窗口。
- 遇到登录异常、验证码、滑动验证、安全验证或账号异常，停止操作并按技能规则通知。
