# AGENTS.md

本仓库的 AI 编码代理指引统一维护在 [CLAUDE.md](CLAUDE.md)（项目概述、常用命令、关键约定），详细文档在 `agent-docs/`：

- [agent-docs/architecture.md](agent-docs/architecture.md) — 后端启动流程、笔记流水线、模块地图、如何新增平台/转写器/LLM
- [agent-docs/frontend.md](agent-docs/frontend.md) — Web 前端和浏览器插件结构
- [agent-docs/api.md](agent-docs/api.md) — 后端全部 API 路由
- [agent-docs/configuration.md](agent-docs/configuration.md) — 端口、环境变量、持久化数据、Docker、CORS、Tauri 打包
- [agent-docs/workflow.md](agent-docs/workflow.md) — 分支模型、commit 规范、测试、CI、发版
- [agent-docs/git-history.md](agent-docs/git-history.md) — 清理 git 历史前的存档（版本里程碑、重要事件、贡献者、上游仓库）

开始工作前请先阅读 CLAUDE.md。更新项目信息时只改 CLAUDE.md 和 agent-docs/，本文件只做索引。
