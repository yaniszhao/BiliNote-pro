# Git 历史存档

这份存档在 2026-10-16 清理 git 历史之前整理，数据来自当时的 `git log`。清理后下面的 commit hash 都会失效，只能作为参考；如果要查原始提交，去上游仓库搜对应的 hash 或 PR 号。

## 快照信息

- 清理前 HEAD：`90940fde4d224d0f69ad99674f4af0a1ea52d3c4`（master，2026-09-01，`docs(readme): replace KaCutAI promotion with enterprise AI consulting`）
- 当前 remote：`git@github:yaniszhao/BiliNote-pro.git`（fork 版本）
- 上游仓库：https://github.com/JefferyHcool/BiliNote，原作者 JefferyHcool（黄建武）
- 共 530 个 commit（其中 207 个是 merge，约 150 个 PR）。第一个 commit 是 `0e0b8da`（2025-04-13，`first commit`）
- 本地没有 tag、stash、git notes，也没有自定义 hook。上游的版本 tag 是 `vX.Y.Z` 格式
- 提交最活跃的月份：2025-04（91）、2025-05（111）、2025-06（55）、2026-03（51）、2026-05（123）

## 版本里程碑

v2.1.0–v2.4.4 每个版本的详细改动见 `CHANGELOG.md`。下面列的是 CHANGELOG 没写到的部分，以及每个版本对应的 commit。

### v1.x（2025-04 ～ 2025-07，上游早期）
- 2025-04-13 项目创建；事件系统（转写后清理临时文件）、日志
- 2025-04-15～20 Bilibili/YouTube 下载器改成优先下载 m4a 音频；Bcut、快手、MLX Whisper 转写器；nginx 反向代理
- 2025-04-16 v1.0.0（PR #17），之后 hotfix/1.0.1（PR #21/#22/#37）
- 2025-04-26～28 模型与供应商管理、首页重构 + 生成历史、本地视频
- 2025-05-02～04 抖音下载器 + Cookie、视频理解（截图发给多模态模型）、多版本笔记
- 2025-05-06～09 重构部署方案（nginx 代理）、快手下载器、Whisper 模型改从 ModelScope 下载、路径处理支持打包运行；v1.5.0（PR #88/#92）
- 2025-05-12～14 Groq 转写 + 供应商、思维导图、异常处理中间件、Ollama 本地模型
- 2025-05-26～06-06 模型管理与连通性测试、后端异常处理和模型管理重构；v1.7.4/v1.7.5（PR #130–#133）
- 2025-06-19～23 v1.8.0 / v1.8.1（PR #140–#158）：后端初始化与健康检查、上传体验
- 2025-07-04 Docker GPU 支持（PR #176，Paper-Dragon）

### v2.0.0（2026-01 ～ 2026-03）
- 2026-01-24 字幕优先获取 + 思维导图导出增强（PR #268）
- 2026-02-06 部署监控页（PR #275）
- 2026-03-23 一次集中更新：RAG 笔记问答（Function Calling、索引视频元信息、半屏/全屏面板）、YouTube 用 youtube-transcript-api 优先取字幕、视频封面 Banner、笔记开头加来源链接、Docker 镜像自动发布到 GHCR、桌面端构建自动创建 GitHub Release
- 2026-04-07 Zustand 持久化改用 IndexedDB（PR #318）

### v2.1.0 ～ v2.4.4（2026-05-07 ～ 2026-06-23）
详见 `CHANGELOG.md`。主要内容：
- v2.1.0 浏览器插件（P1 MVP → P2 悬浮按钮/右键菜单/cookie 直通 → P3/P4 侧边栏思维导图 + RAG），插件在浏览器里直接抓 B 站字幕
- v2.1.1 引入 CONTRIBUTING/RELEASING、develop/release 分支模型、commitlint、插件自动打包 workflow
- v2.1.2～2.1.4 发版流程修正：`Release vX.Y.Z` 格式的 merge commit 被 commitlint 拒绝，从 2.1.4 起改为 `chore(release): vX.Y.Z`（`7358cd0`）；桌面端构建矩阵去掉了 Linux
- v2.2.0 插件选项和 web 端对齐、桌面端首次启动引导 + sidecar 健康面板、Whisper 默认模型改为 tiny、deploy-resilience 修复；2.2.1/2.2.2 把 pnpm 固定到 9.15.0，修复 Docker 和 Tauri 构建失败
- v2.3.x 桌面端版本号从 tag 注入（`b740e70`，之前产物版本号一直是 2.0.0）
- v2.4.x 依赖安全修复，starlette 0.46.1→0.47.2（CVE-2025-54121，`55946b8`）

### v2.4.5（2026-08-25，CHANGELOG 中还没有这一段）
合并在 PR #446（`be38893`，release commit `8fbac5b`），包含：
- `bebf2e8` 修复 DeepSeek 模型列表为空；whisper 模型下载不走代理的问题（#417）
- `b85d7bc` 规范化各种含 BV 号的 B 站链接（稍后再看、收藏夹、带追踪参数）（PR #421）
- `7591166` 前端：视频链接缺协议头时自动补 `https://`（PR #423）
- `944985f` 必剪转写器实例复用导致上传状态残留和并发竞争（PR #422）
- `456ee60` / `e5849ca` Whisper 模型选择被缓存，且没有遵循用户显式选择的模型（PR #425）
- `3e579b1` YouTube 报 "Requested format is not available"（PR #427）
- `58ec74f` yt-dlp 没设 retries 时不重试，网络抖动一次任务就失败（PR #428）
- `f0090f9` requests 升到 2.32.4（CVE-2024-47081 / GHSA-9hjg-9r4m-mvj7，PR #438）
- `5f51b34` / `9eb0fc8` / `a8ae70a` 给上面这些修复补了测试

v2.4.5 之后：`990bc69`、`90940fd` 只改了 README 里的推广内容。

## 值得记住的事件

- 2026-05-09 `c4abaf4` 回滚了 "Fix/backend deploy resilience"，之后在 `9bbae2c` 中重新合入 release/2.2.0。这个 PR 修复了两个问题：用 `model.bin` 判断 Whisper 模型是否下载完整；没装 torch 时 `/api/deploy_status` 不再报 500
- 历史上出现过两套提交信息风格：早期是 `feat(xxx): 中文描述` 加很长的正文；从 v2.1 开始严格遵循 commitlint
- `9d1a7cd`：关于页的版本号要和 README / tauri.conf.json 同步修改，否则会显示错误版本

## 贡献者（按 commit 数）

- 主要维护者 JefferyHcool / 黄建武 / huangjianwu / 思诺特（同一个人的多个身份），约 475 个 commit
- 社区贡献者：Karasukaigan（10）、pumpkinperson996（7，v2.4.5 的大部分修复）、techotaku39（6，PR #374/#375/#377/#382）、SurfRid3r（6，MLX Whisper / 转写器）、HansYeoh（3，思维导图导出、允许所有域名）、Paper-Dragon（2，GPU Docker、本地视频修复）、wmsdsb137（2，B 站分 P 编号）、Sjshi763（PR #262/#273）、linwinfan（IndexedDB）、Lizhilin（B 站 cookie 注入）、voidborne-d（DeepSeek content 格式）、Loker-Choi（YouTube Shorts）、fivedang（nginx 默认页）、sibuchen（部署监控）、nbzcy/sunnyclubcn（字幕优先）、katsugtgz（requests CVE），以及其他各贡献 1 个 commit 的作者

## 清理后如何追溯

- 2026-10-16 已基于 `6220ff7`（在 `90940fd` 之上加了 agent-docs）重建为单个初始 commit
- 完整旧历史备份在 `/root/work_dir/BiliNote-pro-history-90940fd.bundle`（仓库外），恢复：`git clone /root/work_dir/BiliNote-pro-history-90940fd.bundle`
- 上游仓库也保留了完整历史：`git clone https://github.com/JefferyHcool/BiliNote` 后可以用上面的 hash 或 PR 号查
