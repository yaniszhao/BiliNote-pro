# 开发流程、测试与发版

详细规范见 `CONTRIBUTING.md`（分支/提交）和 `RELEASING.md`（发版）。这里只列要点。

## 分支模型
- `master` 只放已发布代码；`develop` 是唯一的长期集成分支，日常 PR 的 base 是 `develop`
- 短分支命名 `<type>/<scope>-<事项>`，全小写 + 中划线；scope 取值例如 `extension` / `frontend` / `backend` / `bilibili` / `youtube` / `douyin` / `kuaishou` / `transcriber` / `gpt` / `chat` / `docker` / `ci` / `docs`
- 发版走 `release/X.Y.Z`（合入 master 后再回灌 develop，都用 `--no-ff` merge commit），紧急修复走 `hotfix/*`

## Commit 规范（`.commitlintrc.json`，CI 会校验）
- Conventional Commits：`type(scope): subject`
- type：feat / fix / docs / style / refactor / perf / test / build / ci / chore / ui / revert
- 标题最多 100 字符（超出只告警）；merge commit 标题也必须符合格式（例如 `chore(release): vX.Y.Z`）

## 测试
- 后端：`cd backend && pytest`（`backend/tests/`，没有 pytest.ini）。测试按模块命名，例如 `test_request_chunker.py`、`test_ydl_retry_*.py`、`test_transcriber_provider_model_selection.py`。修 bug 时一般会补一个对应的测试
- 前端：只有 `pnpm lint`，没有单元测试
- 插件：`pnpm typecheck`、`pnpm test`（Vitest）、`pnpm test:e2e`（Playwright）
- 后端没有配置 linter

## CI（`.github/workflows/`）
- `commitlint.yml` — 校验提交信息
- `docker-build.yml` — 推 tag 时构建并发布 Docker 镜像
- `main.yml` — 推 `v*` tag 时构建 Tauri 桌面端（Python 3.11 + pnpm 9 + Node 20）并挂到 Release
- `release-extension.yml` — 推 tag 时构建插件 zip/xpi/crx 并挂到 Release；商店上传目前是手动的
- `claude.yml` / `claude-code-review.yml` — Claude 自动 review

## 发版时要更新的文件
`CHANGELOG.md`（Keep a Changelog 格式）、`README.md` 顶部版本号，有重大变更时同步更新 `CLAUDE.md` 和 `agent-docs/`。
