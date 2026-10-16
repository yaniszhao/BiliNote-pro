# 后端架构（`backend/`）

Python 3.11 + FastAPI。入口 `backend/main.py`，`app/__init__.py:create_app` 把所有 router 挂在 `/api` 前缀下。

## 启动流程（`main.py` lifespan）

1. `register_handler()` — 注册 Blinker 事件（`backend/events/`，如转写后清理临时文件）
2. `init_db()` — 初始化 SQLite
3. `TranscriberConfigManager().get_config()` — 只读取配置；转写器在首次生成笔记时按需创建，不可用的类型会在使用时报错而不是静默回退
4. `seed_default_providers()` — 写入默认 LLM 供应商
5. `ProxyConfigManager().apply_to_env()` — 把 UI 配置的代理导出到环境变量（让 huggingface 模型下载走代理，issue #417）

每步都有 `[startup N/5]` 日志，失败时打 `[startup FAILED]`。另外：CORS（`CORS_ORIGIN_REGEX`）、GZip、异常处理器、静态目录 `/static`（截图）和 `/uploads`（上传的本地视频）。`ffmpeg_helper.ensure_ffmpeg_or_raise` 会检查 FFmpeg，支持 `FFMPEG_BIN_PATH`。

## 核心流水线

`app/services/note.py:NoteGenerator.generate` 负责编排整条流程，任务由 `task_serial_executor.py` 执行（线程池，`TASK_MAX_WORKERS` 默认 3）。

```
解析 URL → 下载（或直接取字幕）→ FFmpeg 抽音频 → 转写 → LLM 总结（长文本分块）
→ Markdown 后处理（插入截图、链接）→ 保存元数据/结果
```

状态枚举 `app/enmus/task_status_enums.py:TaskStatus`：
`PENDING → PARSING → DOWNLOADING → TRANSCRIBING → SUMMARIZING → FORMATTING → SAVING → SUCCESS / FAILED`。
前端轮询 `/api/task_status/{task_id}` 获取进度。

## 模块地图（`backend/app/`）

- `routers/` — `note.py`（生成/上传/状态/删除/图片代理）、`provider.py`、`model.py`、`config.py`（cookie、转写器、whisper 模型、代理、系统检查）、`chat.py`（RAG 问答）
- `services/`
  - `note.py` — `NoteGenerator`
  - `task_serial_executor.py` — 任务队列
  - `chat_service.py` + `chat_tools.py` + `vector_store.py` — 基于转写稿和视频元数据的 RAG 问答，用 Function Calling（`VECTOR_DB_DIR`）
  - `model_fallback.py` — 模型兜底逻辑
  - `cookie_manager.py` — 按平台存 cookie，由下载器注入 yt-dlp
  - `transcriber_config_manager.py` / `proxy_config_manager.py` — 运行时配置持久化
- `downloaders/` — 平台适配器，统一接口在 `base.py`：bilibili（含 `bilibili_subtitle.py`、`bilibili_dm_patch.py`）、youtube（含 `youtube_subtitle.py`，有字幕时跳过音频下载）、douyin（`douyin_helper/abogus.py` 签名）、kuaishou、xiaoyuzhoufm、local
- `transcriber/` — fast-whisper、groq、bcut、kuaishou、mlx-whisper（仅 Apple Silicon）；工厂在 `transcriber_provider.py`，模型清单/下载状态在 `whisper_models.py`、`model_download_state.py`
- `gpt/` — 工厂 `gpt_factory.py:GPTFactory.from_config`；`universal_gpt.py`（OpenAI 兼容主实现，支持 checkpoint）；`prompt.py`/`prompt_builder.py` 提示词；`request_chunker.py` 处理长转写稿分块（`OPENAI_MAX_REQUEST_BYTES`）
- `db/` — SQLAlchemy + DAO（`provider_dao.py`、`model_dao.py`、`video_task_dao.py`）。表：`providers`、`models`、`video_tasks`（`db/models/`）
- `models/` — Pydantic 请求/领域模型
- `utils/` — `response.py`（`ResponseWrapper` 统一 JSON 格式）、`video_helper.py`（FFmpeg 截图）、`screenshot_marker.py`、`export.py`（PDF/DOCX）、`url_parser.py`、`logger.py`
- `validators/video_url_validator.py` — URL → 平台识别（浏览器插件 `src/logic/platform.ts` 有一份镜像实现，改动时两边要同步）
- `exceptions/` — `BizException` + `register_exception_handlers`
- `enmus/` — 枚举（目录名就叫 `enmus`，拼写是历史遗留，不要改）

## 新增平台/转写器/LLM 的入口

- 新平台：`downloaders/` 加实现 `base.py` 接口 → `NoteGenerator._get_downloader` 注册 → `video_url_validator.py` 和插件 `platform.ts` 加识别规则
- 新转写器：`transcriber/` 加实现 → `transcriber_provider.py` 的 `TranscriberType` 和工厂里注册
- 新 LLM：一般走 OpenAI 兼容接口，在 UI 里添加供应商即可，不用改代码
