# BOSS/Zhipin Skill Tree

Last updated: 2026-06-04

```text
zhipin-recommend-screening-pipeline
├── jobs
│   └── zhipin-open-jobs-read
│       └── 读取「职位管理 -> 开放中」岗位列表，并校验是否存在于用户提供 JD 库
│   └── zhipin-open-job-jd-read
│       └── 旧版/手动恢复技能：仅在用户明确要求刷新 JD 时读取岗位详情
├── recommend
│   ├── zhipin-recommend-job-select
│   │   └── 进入「推荐牛人」并选择对应开放岗位
│   └── zhipin-recommend-candidate-resume-read
│       └── 批量预筛列表年龄/学历/重复状态，只打开需要在线确认的简历并完整滑到底读取候选人所有简历信息
├── match
│   └── zhipin-archive-jd-resume-match
│       └── 根据 HR 提供 JD 的硬性要求分析判断候选人是否合适，缺少直接证据就视为硬性条件未满足
├── forward
│   └── zhipin-candidate-match-forward-flow
│       └── 单候选人链路：入库 -> 硬性条件检查 -> 全部满足直接 BOSS 转发给HR
├── scheduled-report
│   └── zhipin-scheduled-forward-report
│       └── 工作日报：运行状态、Token、漏斗、岗位拆解、小昭洞察与建议，次日 09:00 发飞书群
└── export
    └── zhipin-desktop-archive-export
        └── 用户明确要求时，导出 SQLite 聚合信息
```

## Fixed Rules

- 正常自动流程不再每天点击岗位详情读取或更新 JD。
- `zhipin-open-job-jd-read` 已从恢复目录还原，但只作为手动 legacy 能力保留，默认自动化不调用。
- 每天开始处理候选人前，只读取 `职位管理 -> 开放中` 岗位列表，检查开放岗位是否存在于用户提供 JD 库。
- 如果开放岗位缺少 JD，视为流程资料缺失，通过飞书告知钟苗：`jd库里没有xxx岗位的jd，请提供。`
- 候选人匹配使用 SQLite 中的用户提供 JD；正常封装流程不包含 BOSS JD 详情读取技能。
- 判断标准根据 HR 提供 JD 的硬性要求去分析判断是否合适，缺少直接证据就视为硬性条件未满足。
- 硬性条件全部满足：不再飞书确认，直接 BOSS 站内转发给 `HR`。
- 候选人是否合格都必须记录最小信息，确保后续查重使用。
- 打开在线简历后，必须完整滑到底，读取候选人的所有简历信息并按照硬性要求去分析。
- 忽略底部的其他名校毕业的牛人、相似候选人信息。
- 候选人是否已处理只以 SQLite `processed_candidates` 为准；筛选前必须按规范化 `candidate_key` 全局查重，只要任意岗位已处理过同一候选人，就跳过。
- 每天筛选开始和结束只发普通飞书群通知，不 @ 钟苗；只有故障、登录异常、缺 JD、无法启动等阻断事项才告知钟苗。
- Token 消耗使用本机 Codex 当天 session 总消耗。
