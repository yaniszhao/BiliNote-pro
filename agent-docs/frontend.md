# Web 前端与浏览器插件

## Web 前端（`BillNote_frontend/`，注意拼写是 Bill 不是 Bili）

React 19 + Vite + TypeScript（strict）+ Tailwind + shadcn/ui（Radix），同时用了 antd / @ant-design/x。也是 Tauri 桌面端的 UI（`src-tauri/`）。

- `src/pages/`
  - `HomePage/` — 主界面，组件在 `HomePage/components/`：`NoteForm.tsx`（输入）、`MarkdownViewer.tsx`（预览）、`MarkmapComponent.tsx`（思维导图）、`ChatPanel.tsx`（RAG 问答）、`History.tsx`/`NoteHistory.tsx`、`StepBar.tsx`、`transcriptViewer.tsx`
  - `SettingPage/` — `Model.tsx`（供应商/模型）、`transcriber.tsx`、`Downloader.tsx`（cookie）、`Prompt.tsx`、`Monitor.tsx`（系统监控）、`about.tsx`
  - `Onboarding/`、`NotFoundPage/`
- `src/store/` — Zustand：`taskStore`、`modelStore`、`configStore`、`providerStore`、`chatStore`，持久化到 IndexedDB（idb-keyval）
- `src/services/` — Axios 客户端，和后端 router 一一对应（`note.ts`、`model.ts`、`chat.ts`、`transcriber.ts`、`downloader.ts`、`proxy.ts`、`system.ts`、`upload.ts`）
- `src/hooks/useTaskPolling.ts` — 每 3 秒轮询一次任务状态；`useCheckBackend.ts` — 检查后端健康
- `src/i18n/` — react-i18next，语言包在 `i18n/locales/`，切换组件 `components/LanguageSwitcher.tsx`
- `src/components/ui/` — shadcn/ui 组件
- 路径别名 `@` → `./src`
- `vite.config.ts`：开发服务器端口 3015，把 `/api` 和 `/static` 代理到后端；env 从上级目录读，设置了 `DOCKER_BUILD` 时改为读当前目录
- 代码风格：ESLint + Prettier（2 空格、单引号、行宽 100、Tailwind 插件）

## 浏览器插件（`BillNote_extension/`）

Vue 3 + Vite + UnoCSS + webextension-polyfill，MV3（基于 vitesse-webext）。

- `src/popup/Popup.vue` — 主入口：从当前标签页 URL 识别平台，发起生成，展示进度和 Markdown
- `src/options/Options.vue` — 设置：后端地址（默认 `http://localhost:8483`）、默认供应商/模型、清晰度、截图/链接开关、笔记风格
- `src/logic/api.ts` — 后端客户端（解包 `ResponseWrapper`，把 `/static/screenshots/...` 转成绝对地址）
- `src/logic/storage.ts` — 基于 `chrome.storage.local` 存设置和最近 30 个任务
- `src/logic/platform.ts` — 平台识别，镜像 `backend/app/validators/video_url_validator.py`
- `src/logic/bilibili-subtitle.ts`、`cookies.ts` — 在浏览器侧获取字幕和 cookie
- `src/components/` — `ChatPanel.vue`、`MindMap.vue`、`MarkdownView.vue`、`TaskProgress.vue` 等
- `src/contentScripts/` — 视频页悬浮按钮（只在支持的平台注入）；`src/sidepanel/` — 侧边栏详情页（Markdown / 思维导图 / RAG 问答）
- `src/background/main.ts` — 右键菜单"用 BiliNote 总结此视频"等后台逻辑
- `src/manifest.ts` — MV3：popup 是默认 action，声明了 `contextMenus`、`content_scripts`、`side_panel`（Firefox 构建会删掉 content_scripts），`host_permissions: *://*/*`
- popup 打开期间每 3 秒轮询一次
- 调试：`chrome://extensions/` → 加载已解压的扩展 → 选 `BillNote_extension/extension/`
- 测试：Vitest（`src/**/__tests__`、`src/tests`）+ Playwright（`e2e/`）
