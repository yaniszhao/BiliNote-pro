# 修复记录：Groq 转写 413（长视频音频超限）→ 分片转写

时间：2026-10-24。记录一次线上任务失败的根因分析与修复方案，供后续维护参考。

## 问题现象

- 任务 `7abf79ed-d552-49e0-a0ea-412894cfc111` 失败，状态文件 `note_results/7abf79ed-....status.json` 写入：
  `{"status": "FAILED", "message": "Error code: 413 ... code: 'request_too_large'"}`
- 日志（`backend/logs/app.log`）关键行：
  `音频转写失败：Error code: 413 - {'error': {'message': 'Request Entity Too Large', 'type': 'invalid_request_error', 'code': 'request_too_large'}}`
- 视频：BV1c9EK6KEW4（cid=38944114658），时长 3517.38s（约 58.6 分钟），转写器 groq，代理 `http://172.31.48.1:7890`

## 根因

Groq 转写 API（免费档）有 **25MB multipart 请求体上限**。该视频产出的 mp3
（`backend/data/data/BV1c9EK6KEW4.mp3`，28,139,916 字节 ≈ 26.8MB，64kbps CBR）超限。

旧代码（`backend/app/transcriber/groq.py`）只有一条路：超过 `MAX_SIZE_MB = 18` 时做一次
64k 压缩再单请求发送。但源音频本来就是 64k，压缩无效果（no-op），长视频仍然超限 → 413。

调用链：`app/services/note.py:193 generate` → `note.py:525 _get_transcript` →
`note.py:562 _transcribe_audio` → `groq.py transcript()`。

## 修复方案：分片转写（`backend/app/transcriber/groq.py`）

设计要点：

1. **≤18MB 走原路**：单请求直接转写，行为不变。
2. **超限时切片**：
   - `_get_audio_duration()`：ffmpeg-python probe 音频总时长，失败返回 `None`。
   - `_compute_chunk_seconds(file_size, duration)`：按目标片大小
     `CHUNK_TARGET_BYTES = 24MB` 反算片长（`24MB*8 / 平均码率`），假设码率均匀
     （下载器产出 CBR 64k mp3，假设成立）；probe 失败时兜底
     `CHUNK_TARGET_SECONDS = 600s`，并且片长下限 30s。
     例：26.8MB / 58.6 分钟 → 每片 ≈3146s，共 2 片。
   - `split_audio(file_path, chunk_seconds, output_dir)`：ffmpeg `-c copy`
     **无损流式切片**（不重编码），已记录时长时最后一片不设 `t`（截到末尾）；
     时长未知模式按兜底片长循环切，切到空片为止。边界不做语音对齐——Whisper
     各片独立解码，边界可能损失/多出半句话，对摘要场景可接受。
3. **逐片转写 + 时间戳平移合并**：每片转写结果按累计偏移
   `offset += chunk_seconds`（已知总时长时非末片用精确片长；末片/未知时长用
   `max(seg.end)` 估算）平移到全局时间轴，合并为单一 `TranscriptResult`；
   空文本 segment 跳过；单片时 `raw` 不包 `chunks`，多片时 `raw = {"chunks": [...]}`。
4. **临时文件清理**：切片写入 `tempfile.mkdtemp(prefix="groq_chunks_")`，
   `finally` 中 `shutil.rmtree` 清理，原始音频不动。

## 测试覆盖（`backend/tests/test_groq_chunked_transcript.py`，10 个用例）

- `TestGetAudioDuration`：有效 mp3 返回时长 / 无效文件返回 None
- `TestComputeChunkSeconds`：时长未知走兜底 / 已知时长按时长与码率缩放
- `TestSplitAudio`：低于片长不切 / 已知时长切出预期片数（**真实 ffmpeg** 造小 mp3）
- `TestGroqTranscriberMerge`：空段文本跳过 / 多片偏移累计 / 30s 真实 mp3 端到端
  冒烟（切片临时目录被清理）/ 低于上限走单片路径（mock API，无网络）

结果：**10 passed**。全量套件 92 passed + 4 个预先存在失败（见下）。

> 运维/测试相关的踩坑（容器跑 pytest、预先存在的测试失败）已提取到
> [gotchas.md](../gotchas.md)，本文件只保留修复方案本身。

