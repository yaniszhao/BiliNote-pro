# 变更记录：生成历史持久化到后端 + 截图分目录 + 任务真删除

时间：2026-11-02，提交 `f529a7a`。三个关联问题一起解决：历史丢失、截图堆
平铺目录、删除任务不清理数据。

## 问题现象

1. **清浏览器缓存 → 「生成历史」全丢**：历史只存浏览器 IndexedDB
   （zustand persist，键 `task-storage`），而后端 `note_results/` 其实已有
   全量数据（result/status/transcript/markdown 缓存），只是没有列表入口，
   清缓存后前端无法从后端恢复。
2. **截图全堆 `backend/static/screenshots/` 平铺**：1453 张混在一起，无法按
   笔记归属，删除任务时也没法清理对应截图。
3. **删除任务只从本地列表移除**：后端 `delete_task` 是空实现，结果文件、
   转写/检查点缓存、截图、下载的音视频、向量索引、DB 记录全部残留，永久累积。

## 实现方案

### 后端：元数据落盘（`backend/app/services/task_meta.py`，新文件）

每个任务在 `note_results/` 下新增 sidecar `{task_id}_meta.json`：

- **任务入口即写入**（`generate_note` 路由开头）：`video_url/video_id/platform/
  created_at/form_data`（表单参数完整快照，含 reasoning_effort）——失败、进行中
  的任务也有记录，是 task_list 的数据源；
- **成功后 merge 补齐**（`save_note_to_file` 时）：`title/cover_url/duration/
  finished_at`；
- 重试复用 task_id 时 `merge=True`，新表单覆盖旧值；
- `list_task_ids()` 只认**裸 UUID** 文件名（`TASK_ID_RE` fullmatch），天然排除
  所有带后缀的辅助文件（`_transcript.json`、`.status.json` 等）；
- 原子写（`.tmp` + `replace`），与 `_update_status` 同模式；
- **刻意零 app 包依赖**（标准库 logging）：本模块被测试以 importlib 单文件方式
  加载，避免 sys.modules 桩污染（详见 gotchas.md 对应条目）。

### 后端：列表 API（`GET /api/task_list`）

轻量返回 `task_id / status / message / created_at / video_id / platform /
title / cover_url / has_result / form_data`，**不含 markdown/transcript 全文**；
全文由前端按需调现成的 `GET /api/task_status/{task_id}`（SUCCESS 时返回完整
result）。数据源为文件扫描——`status.json` 在任务入口就写，覆盖进行中/失败态；
`video_tasks` 表只在成功后才有记录，故只作兜底。

### 后端：截图分目录（`app/services/note.py`）

- `_insert_screenshots` 接收 `task_id`，输出目录与 URL 均为
  `static/screenshots/{task_id}/screenshot_{idx}_{uuid}.jpg`；
- 不传 task_id 时退回平铺（旧调用兼容）；
- 存量平铺截图**不迁移**：旧笔记 URL 仍指向旧路径且有效。

### 后端：真删除（`POST /api/delete_task`，`app/routers/note.py`）

`_delete_task_artifacts` 按序清理（task_id 必须 UUID 形式，防 `../` 穿越）：

1. `_delete_media_files`：读 `{task_id}_audio.json` 拿媒体路径，删
   `data/data/{video_id}.mp3` 与 `.mp4`；**同一视频被其他任务引用时保留**
   （重复生成不重新下载时指向同一文件）；必须在删 audio.json 之前调用；
2. `note_results/` 下 8 种产物：result `.json`、`.status.json`、
   `_transcript.json`、`_audio.json`、`_markdown.md`、`_markdown.status.json`、
   `.gpt.checkpoint.json`、`_meta.json`；
3. 截图子目录 `static/screenshots/{task_id}/`；
4. 向量索引（chromadb collection）+ chat 内存状态 `_index_status`；
5. `video_tasks` 表记录（`video_task_dao.delete_task_by_task_id`，新增）。

请求体兼容：新调用传 `task_id`（前端 task.id），旧 `video_id+platform` 走
`get_tasks_by_video`（新增）兜底查整组删除。

### 前端：恢复链路（`BillNote_frontend/src/hooks/useTaskRestore.ts`，新文件）

挂 `App.tsx`，由 `useCheckBackend` 的 `initialized` 触发（后端就绪才拉）：

1. `get_task_list()` 拉 10 条轻量列表 + 本地 IndexedDB 读取合并：
   - 后端有、本地无 → upsert 骨架（全文稍后按需拉）；
   - 本地终态（SUCCESS/FAILD/FAILED）不回滚——本地可能比后端新；
   - 本地进行中 + 后端已成功 → 标成功并拉全文（清缓存前提交、后端已跑完）；
   - 本地进行中 + 后端已失败无结果（后端重启）→ 标失败；
2. 缺全文的任务并发（≤3）调 `get_task_status` 拉全文，复用轮询链路的响应结构；
3. `mergeRestoredTasks`（taskStore 新增）：新任务 upsert 骨架、本地已有只补
   缺失字段，不动 `currentTaskId`。

其他前端配套：`removeTask` 改为**先调后端真删除、成功才动本地状态**（失败则
保留条目）；`updateTaskStatus` 补上（`useTaskPolling` 引用的现存缺失 bug）；
`TaskStatus` 增加 `'FAILED'` 正确拼写，保留遗留 `'FAILD'` 兼容旧持久化数据。

### 插件

无需改动：截图 URL 正则匹配 `/static/` 任意深度、`/static/screenshots/{task_id}/`
嵌套路径天然兼容。

## 测试覆盖（backend/tests，共 4 个新文件）

- `test_task_meta.py`：list_task_ids 的 UUID 过滤、save 的 merge 语义、空 ID 不写
- `test_task_list_api.py`：字段透传、仅有 status（进行中）任务、仅有 result
  （status 缺失兜底 SUCCESS）、损坏 status.json 不炸接口
- `test_delete_task.py`：8 种产物 + 截图目录全清、路径穿越拒绝（`../static`
  被拒且不动 victim 文件）、旧 video_id+platform 兜底、媒体文件删除、
  媒体被其他任务引用时保留
- `test_screenshot_subdir.py`：URL 含 `{task_id}/` 子目录、缺省退回平铺

容器内全量：**115 passed**（含新用例），5 个失败为预存基线（与本次无关，
见 gotchas.md）。

## 实跑验证（BV1HxQSBgEvC）

- 99 张截图全部落 `static/screenshots/ab48fd00-*/`，markdown 中 99 个 URL 与
  目录文件一一对应；
- `_meta.json` 含完整 form_data（reasoning_effort=low）+ 成功后补的 title/
  cover/duration/finished_at；
- 任务入口与 LLM 调用日志均正常输出（见 reasoning-effort-support.md）。

## 已知边界

- 存量任务无 `_meta.json` → 历史列表可见、可看全文，但**重试/问答会缺模型配置**
  （前端对空 formData 提示）；
- 存量平铺截图不迁移，仅新笔记用子目录；
- 重试复用 task_id 时子目录内旧截图不清理（防重试失败丢旧图）；
- 本地视频仅删转码产物（`.mp3`），用户上传的原始文件（`uploads/`）不动。
