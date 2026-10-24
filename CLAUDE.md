# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

BiliNote：AI 视频笔记生成工具。输入视频链接（Bilibili、YouTube、抖音、快手、小宇宙、本地文件），经过 下载 → FFmpeg 抽音频 → 转写 → LLM 总结 生成结构化 Markdown 笔记（含截图、思维导图、RAG 问答）。

- `backend/` — Python 3.11 + FastAPI，入口 `main.py`，路由统一挂在 `/api`，端口 8483
- `BillNote_frontend/` — React 19 + Vite + TS + Tailwind/shadcn，开发端口 3015；也是 Tauri 桌面端的 UI（目录名是 **Bill**Note，不是 Bili）
- `BillNote_extension/` — Vue 3 + MV3 浏览器插件，调用同一个后端

## 常用命令

```bash
# 后端
cd backend && pip install -r requirements.txt && python main.py
cd backend && pytest                                   # 全部测试
cd backend && pytest tests/test_request_chunker.py::test_name

# Web 前端
cd BillNote_frontend && pnpm install && pnpm dev       # /api、/static 代理到后端
pnpm build / pnpm lint

# 插件
cd BillNote_extension && pnpm dev | pnpm build | pnpm typecheck | pnpm test | pnpm test:e2e

# Docker
docker-compose up                                      # 后端 + 前端 + nginx
docker-compose -f docker-compose.gpu.yml up
```

## 关键约定与注意事项

- 核心编排在 `backend/app/services/note.py:NoteGenerator`；任务状态见 `app/enmus/task_status_enums.py`，前端每 3 秒轮询 `/api/task_status/{id}`
- 后端响应统一用 `app/utils/response.py:ResponseWrapper`，业务异常抛 `BizException`
- LLM API key 在 UI 里配置并存到 SQLite（`backend/bili_note.db`），不要写进 `.env`
- `VITE_*` 是构建时变量；其他 env 是后端运行时变量
- URL → 平台识别有两份实现：`backend/app/validators/video_url_validator.py` 和 `BillNote_extension/src/logic/platform.ts`，改一边要同步另一边
- CORS 白名单 `backend/main.py:CORS_ORIGIN_REGEX` 覆盖了 Tauri 三个平台的 origin 和浏览器扩展 origin，不要随意收紧
- FFmpeg 是必需的系统依赖（`FFMPEG_BIN_PATH` 可指定路径）
- 提交遵循 Conventional Commits（commitlint 会校验）；日常 PR 的 base 是 `develop`，不是 `master`
- 代码风格：前端 ESLint + Prettier（2 空格、单引号、行宽 100）；后端写 type hints + Pydantic，没有配置 linter

## 详细文档索引（`agent-docs/`）

- [agent-docs/architecture.md](agent-docs/architecture.md) — 后端启动流程、笔记流水线、模块地图、如何新增平台/转写器/LLM
- [agent-docs/frontend.md](agent-docs/frontend.md) — Web 前端（页面、store、services、i18n）和浏览器插件结构
- [agent-docs/api.md](agent-docs/api.md) — 后端全部 API 路由
- [agent-docs/configuration.md](agent-docs/configuration.md) — 端口、环境变量、持久化数据位置、Docker、CORS、Tauri 打包
- [agent-docs/workflow.md](agent-docs/workflow.md) — 分支模型、commit 规范、测试、CI、发版要点
- [agent-docs/git-history.md](agent-docs/git-history.md) — 清理 git 历史前的存档：版本里程碑、v2.4.5 未写进 CHANGELOG 的改动、重要事件、贡献者、上游仓库
- [agent-docs/fixes/](agent-docs/fixes/) — 具体问题的修复存档（根因分析 + 方案），新修复往这里加
- [agent-docs/gotchas.md](agent-docs/gotchas.md) — 踩坑记录：跨会话运维/开发注意事项，随问题持续追加

其他参考：`CONTRIBUTING.md`（贡献规范）、`RELEASING.md`（发版手册）、`CHANGELOG.md`、`.env.example`。
