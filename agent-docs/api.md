# 后端 API 一览

所有路由前缀都是 `/api`，返回体统一由 `app/utils/response.py:ResponseWrapper` 包装。前端客户端在 `BillNote_frontend/src/services/`，插件客户端在 `BillNote_extension/src/logic/api.ts`。

## 笔记 `routers/note.py`
- `POST /generate_note` — 提交生成任务，返回 task_id
- `GET /task_status/{task_id}` — 查询任务状态/结果（前端和插件都在轮询这个接口）
- `POST /delete_task`
- `POST /upload` — 上传本地视频（存到 `uploads/`）
- `GET /image_proxy` — 代理平台图片（防盗链）

## 供应商 / 模型 `routers/provider.py`、`routers/model.py`
- `POST /add_provider`、`POST /update_provider`、`GET /get_all_providers`、`GET /get_provider_by_id/{id}`、`POST /connect_test`
- `GET /model_list`、`GET /model_list/{provider_id}`、`POST /models`、`GET /models/delete/{model_id}`、`GET /model_enable/{provider_id}`

## 配置 / 系统 `routers/config.py`
- Cookie：`GET /get_downloader_cookie/{platform}`、`POST /update_downloader_cookie`
- 转写器：`GET|POST /transcriber_config`、`GET /transcriber_models_status`、`POST /transcriber_download`
- Whisper 模型：`GET|POST /whisper_models`、`DELETE /whisper_models/{name}`
- 代理：`GET|POST /proxy_config`
- 系统：`GET /sys_health`（docker healthcheck 用）、`GET /sys_check`、`GET /deploy_status`

## RAG 问答 `routers/chat.py`
- `POST /chat/index` — 为某条笔记建立向量索引
- `GET /chat/status`
- `POST /chat/ask`

## 静态资源（不带 `/api` 前缀）
- `/static/...` — 截图（`OUT_DIR`，默认 `./static/screenshots`）
- `/uploads/...` — 上传的本地视频
