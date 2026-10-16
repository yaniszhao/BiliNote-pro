# 配置、运行与部署

## 端口
- 后端 8483（`BACKEND_PORT`/`BACKEND_HOST`）
- 前端开发服务器 3015
- Docker：nginx 对外暴露 `APP_PORT`（默认 3015）→ 80；backend/frontend 容器只在内部网络暴露

## 环境变量
根目录 `.env`（从 `.env.example` 复制）。LLM API key 不放 env，在 UI 里录入并存到 SQLite。

- `VITE_*` 是构建时变量，会打进前端 bundle；Docker 下修改后要 `docker-compose build frontend` 才能生效
- 其余是后端运行时变量。代码里实际读取的有：
  - 路径：`STATIC`、`OUT_DIR`、`NOTE_OUTPUT_DIR`、`IMAGE_BASE_URL`、`DATA_DIR`、`VECTOR_DB_DIR`
  - 数据库：`DATABASE_URL`（默认 `sqlite:///bili_note.db`）、`DB_POOL_SIZE`、`DB_MAX_OVERFLOW`、`SQLALCHEMY_ECHO`
  - 转写：`TRANSCRIBER_TYPE`（fast-whisper / bcut / kuaishou / mlx-whisper / groq）、`WHISPER_MODEL_SIZE`（默认 tiny）、`GROQ_TRANSCRIBER_MODEL`、`HF_ENDPOINT`
  - LLM 请求：`OPENAI_MAX_REQUEST_BYTES`、`OPENAI_RETRY_ATTEMPTS`、`OPENAI_RETRY_BACKOFF_SECONDS`
  - 其他：`FFMPEG_BIN_PATH`、`TASK_MAX_WORKERS`（默认 3）、`HTTP_PROXY`/`HTTPS_PROXY`

## 持久化数据（相对后端工作目录，即 `backend/`）
- `bili_note.db` — SQLite（供应商、模型、任务记录），首次运行自动创建。注意它在 `backend/` 下，不在 `backend/app/db/` 下
- `config/transcriber.json` — 转写器运行时配置
- `static/screenshots/` — 截图；`uploads/` — 上传的视频
- Docker 把整个 `./backend` 挂载到 `/app`，所以上面这些都会落到宿主机

## Docker
- `docker-compose.yml`：backend（`backend/Dockerfile`，python:3.11-slim + ffmpeg，默认用清华 apt/pip 镜像，`HF_ENDPOINT=https://hf-mirror.com`）、frontend、nginx（`nginx/default.conf`）
- 构建参数 `BASE_REGISTRY` / `APT_MIRROR` / `PIP_INDEX`，国内拉不到 docker.io 时可以替换
- backend `mem_limit: 4g`；Whisper 用 medium 及以上建议调到 8g+
- `docker-compose.gpu.yml`（`backend/Dockerfile.gpu`）为 GPU 版本；`Dockerfile.complete` + `nginx/standalone.conf` 为单镜像版本

## CORS
`backend/main.py:CORS_ORIGIN_REGEX` 放行 localhost/127.0.0.1、Tauri（`tauri://localhost`、`http(s)://tauri.localhost`，三个平台的 origin 都不一样，缺一个都不行）、`chrome-extension://`、`moz-extension://`。如果后端日志全是 200 但前端仍报连不上，先排查这里。

## 桌面端（Tauri）
`cd backend && ./build.sh`（PyInstaller 打包后端二进制）→ `cd BillNote_frontend && pnpm tauri build`。
