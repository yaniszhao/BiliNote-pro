# app/routers/note.py
import json
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File
from pydantic import BaseModel, validator, field_validator, model_validator
from dataclasses import asdict

from app.db.video_task_dao import delete_task_by_task_id, delete_task_by_video, get_tasks_by_video
from app.enmus.exception import NoteErrorEnum
from app.enmus.note_enums import DownloadQuality
from app.exceptions.note import NoteError
from app.services.note import IMAGE_BASE_URL, IMAGE_OUTPUT_DIR, NoteGenerator, logger
from app.services.task_meta import TASK_ID_RE, load_task_meta, list_task_ids, save_task_meta
from app.services.task_serial_executor import task_serial_executor
from app.utils.response import ResponseWrapper as R
from app.utils.url_parser import extract_video_id, normalize_video_url
from app.validators.video_url_validator import is_supported_video_url
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
import httpx
from app.enmus.task_status_enums import TaskStatus

# from app.services.downloader import download_raw_audio
# from app.services.whisperer import transcribe_audio

router = APIRouter()


class RecordRequest(BaseModel):
    # 新调用传 task_id（前端 task.id）；旧调用传 video_id+platform（兼容）
    task_id: Optional[str] = None
    video_id: Optional[str] = None
    platform: Optional[str] = None


class VideoRequest(BaseModel):
    video_url: str
    platform: str
    quality: DownloadQuality
    screenshot: Optional[bool] = False
    link: Optional[bool] = False
    model_name: str
    provider_id: str
    # 思考强度：low / medium / high，None 走模型端默认
    reasoning_effort: Optional[str] = "low"
    task_id: Optional[str] = None
    format: Optional[list] = []
    style: str = None
    extras: Optional[str]=None
    video_understanding: Optional[bool] = False
    video_interval: Optional[int] = 0
    grid_size: Optional[list] = []
    # 客户端（如浏览器插件）已经在用户浏览器里抓到字幕，直接传给后端复用，
    # 跳过 download_subtitles 和音频转写。形如：
    #   {"language": "zh", "full_text": "...", "segments": [{"start","end","text"}, ...]}
    prefetched_transcript: Optional[dict] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_url(cls, data):
        # 稍后再看/收藏夹/带追踪参数的 B 站链接先规范化成标准 /video/BVxxx 形式，
        # 后续校验和 yt-dlp 下载拿到的都是干净链接
        if isinstance(data, dict) and data.get("platform") == "bilibili" and data.get("video_url"):
            data["video_url"] = normalize_video_url(str(data["video_url"]))
        return data

    @field_validator("video_url")
    def validate_supported_url(cls, v):
        url = str(v)
        parsed = urlparse(url)
        if parsed.scheme in ("http", "https"):
            # 是网络链接，继续用原有平台校验
            if not is_supported_video_url(url):
                raise NoteError(code=NoteErrorEnum.PLATFORM_NOT_SUPPORTED.code,
                                message=NoteErrorEnum.PLATFORM_NOT_SUPPORTED.message)

        return v


NOTE_OUTPUT_DIR = os.getenv("NOTE_OUTPUT_DIR", "note_results")
UPLOAD_DIR = "uploads"


def save_note_to_file(task_id: str, note):
    os.makedirs(NOTE_OUTPUT_DIR, exist_ok=True)
    with open(os.path.join(NOTE_OUTPUT_DIR, f"{task_id}.json"), "w", encoding="utf-8") as f:
        json.dump(asdict(note), f, ensure_ascii=False, indent=2)

    # 把标题等摘要信息合并进任务元数据，历史列表无需读重量级结果文件即可展示/搜索
    try:
        audio_meta = getattr(note, "audio_meta", None)
        save_task_meta(task_id, {
            "title": getattr(audio_meta, "title", "") or "",
            "cover_url": getattr(audio_meta, "cover_url", "") or "",
            "duration": getattr(audio_meta, "duration", None),
            "finished_at": datetime.now().isoformat(timespec="seconds"),
        }, merge=True)
    except Exception as e:
        logger.warning(f"补写任务元数据失败 (task_id={task_id})：{e}")


def _persist_prefetched_transcript(task_id: str, transcript: dict) -> None:
    """把客户端预取的字幕写到 NoteGenerator 期望的转写缓存文件里。

    NoteGenerator.generate 会优先读 <task_id>_transcript.json，命中即跳过 download_subtitles
    与音频转写流程。要求字段：language(可空)/full_text/segments[{start,end,text}]
    """
    segments = transcript.get("segments") or []
    cleaned_segments = []
    for s in segments:
        text = (s.get("text") or "").strip()
        if not text:
            continue
        cleaned_segments.append({
            "start": float(s.get("start", 0)),
            "end": float(s.get("end", 0)),
            "text": text,
        })
    if not cleaned_segments:
        raise ValueError("prefetched_transcript 没有可用的 segments")

    full_text = transcript.get("full_text") or " ".join(s["text"] for s in cleaned_segments)
    payload = {
        "language": transcript.get("language") or "zh",
        "full_text": full_text,
        "segments": cleaned_segments,
    }

    os.makedirs(NOTE_OUTPUT_DIR, exist_ok=True)
    target = os.path.join(NOTE_OUTPUT_DIR, f"{task_id}_transcript.json")
    with open(target, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.info(f"已写入客户端预取字幕缓存: {target} ({len(cleaned_segments)} 段)")


def run_note_task(task_id: str, video_url: str, platform: str, quality: DownloadQuality,
                  link: bool = False, screenshot: bool = False, model_name: str = None, provider_id: str = None,
                  reasoning_effort: str = "low",
                  _format: list = None, style: str = None, extras: str = None, video_understanding: bool = False,
                  video_interval=0, grid_size=[]
                  ):

    if not model_name or not provider_id:
        raise HTTPException(status_code=400, detail="请选择模型和提供者")

    def _execute_note_task():
        return NoteGenerator().generate(
            video_url=video_url,
            platform=platform,
            quality=quality,
            task_id=task_id,
            model_name=model_name,
            provider_id=provider_id,
            reasoning_effort=reasoning_effort,
            link=link,
            _format=_format,
            style=style,
            extras=extras,
            screenshot=screenshot,
            video_understanding=video_understanding,
            video_interval=video_interval,
            grid_size=grid_size,
        )

    logger.info(f"任务进入执行队列 (task_id={task_id})")
    note = task_serial_executor.run(_execute_note_task)
    logger.info(f"Note generated: {task_id}")
    if not note or not note.markdown:
        logger.warning(f"任务 {task_id} 执行失败，跳过保存")
        return
    save_note_to_file(task_id, note)

    # 自动建立向量索引（用于 AI 问答），失败不影响笔记生成
    try:
        from app.services.vector_store import VectorStoreManager
        VectorStoreManager().index_task(task_id)
    except Exception as e:
        logger.warning(f"向量索引失败（不影响笔记）: {e}")


@router.post('/delete_task')
def delete_task(data: RecordRequest):
    """真正删除任务：结果/缓存文件 + 截图目录 + 向量索引 + 数据库记录。"""
    try:
        if data.task_id:
            if not TASK_ID_RE.fullmatch(data.task_id):
                # 非法 ID 一律拒绝，防止 ../ 路径穿越
                return R.error(msg='非法 task_id')
            task_ids = [data.task_id]
        elif data.video_id and data.platform:
            # 旧调用兼容：按 video_id+platform 查出关联的所有 task_id
            task_ids = [t.task_id for t in get_tasks_by_video(data.video_id, data.platform)]
        else:
            return R.error(msg='缺少 task_id 或 video_id+platform')

        for tid in task_ids:
            _delete_task_artifacts(tid)

        if not data.task_id and data.video_id and data.platform:
            # 旧调用兜底路径：整组删除 DB 记录
            delete_task_by_video(data.video_id, data.platform)

        return R.success(msg='删除成功')
    except Exception as e:
        logger.error(f"删除任务失败：{e}", exc_info=True)
        return R.error(msg=str(e))


def _delete_media_files(task_id: str) -> None:
    """删除该任务下载的音/视频缓存文件（data 目录下的 {video_id}.mp3/.mp4）。

    同一视频可能被多个任务引用（重复生成不重新下载时 audio.json 指向同一路径），
    删除前先检查其他任务的 _audio.json 是否仍引用同一文件，有引用则保留，
    避免误删别的笔记的缓存。必须在删 {task_id}_audio.json 之前调用。
    """
    audio_cache = Path(NOTE_OUTPUT_DIR) / f"{task_id}_audio.json"
    if not audio_cache.exists():
        return
    try:
        info = json.loads(audio_cache.read_text(encoding="utf-8"))
    except Exception:
        return

    file_path = info.get("file_path")
    video_path = info.get("video_path")
    video_id = info.get("video_id")
    targets = {t for t in (file_path, video_path) if t and isinstance(t, str)}
    # download_video 的固定命名：与音频同目录的 {video_id}.mp4（video_path 为空时兜底）
    if file_path and video_id:
        targets.add(os.path.join(os.path.dirname(file_path), f"{video_id}.mp4"))
    if not targets:
        return

    referenced: set[str] = set()
    try:
        for name in os.listdir(NOTE_OUTPUT_DIR):
            if not name.endswith("_audio.json") or name.startswith(task_id):
                continue
            try:
                other = json.loads((Path(NOTE_OUTPUT_DIR) / name).read_text(encoding="utf-8"))
                referenced.add(other.get("file_path") or "")
                referenced.add(other.get("video_path") or "")
            except Exception:
                continue
    except Exception:
        pass

    for target in targets:
        try:
            p = Path(target)
            if p.is_file() and target not in referenced:
                p.unlink()
                logger.info(f"已删除媒体文件: {target}")
        except Exception as e:
            logger.warning(f"删除媒体文件失败 ({target})：{e}")


def _delete_task_artifacts(task_id: str) -> None:
    """删除一个任务的全部本地产物。task_id 必须是 UUID 形式，防路径穿越。"""
    from app.services.task_meta import TASK_ID_RE
    if not TASK_ID_RE.fullmatch(task_id or ""):
        logger.warning(f"拒绝删除非法 task_id: {task_id!r}")
        return

    # 先读 audio.json 拿媒体路径并删除（顺序敏感：audio.json 之后就被删了）
    _delete_media_files(task_id)

    base = Path(NOTE_OUTPUT_DIR).resolve()
    # note_results 下的结果与缓存文件（含 checkpoint / meta）
    suffixes = (
        ".json", ".status.json", "_transcript.json", "_audio.json",
        "_markdown.md", "_markdown.status.json", ".gpt.checkpoint.json", "_meta.json",
    )
    for suffix in suffixes:
        p = (base / f"{task_id}{suffix}")
        if p.parent == base:
            p.unlink(missing_ok=True)

    # 截图子目录：resolved 后必须是 IMAGE_OUTPUT_DIR 的直接子目录，防 ../static 穿越
    screenshot_dir = Path(IMAGE_OUTPUT_DIR).resolve() / task_id
    screenshot_root = Path(IMAGE_OUTPUT_DIR).resolve()
    if screenshot_dir.parent == screenshot_root and screenshot_dir.is_dir():
        shutil.rmtree(screenshot_dir, ignore_errors=True)
        logger.info(f"已删除截图目录: {screenshot_dir}")

    # 向量索引（RAG 问答），失败不影响删除流程
    try:
        from app.services.vector_store import VectorStoreManager
        VectorStoreManager().delete_index(task_id)
    except Exception as e:
        logger.warning(f"删除向量索引失败 (task_id={task_id})：{e}")

    # 问答面板的内存索引状态
    try:
        from app.routers.chat import _index_status
        _index_status.pop(task_id, None)
    except Exception:
        pass

    # 数据库记录
    delete_task_by_task_id(task_id)
    logger.info(f"任务产物已清理 (task_id={task_id})")


@router.post("/upload")
async def upload(file: UploadFile = File(...)):
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    file_location = os.path.join(UPLOAD_DIR, file.filename)

    with open(file_location, "wb+") as f:
        f.write(await file.read())

    # 假设你静态目录挂载了 /uploads
    return R.success({"url": f"/uploads/{file.filename}"})


@router.post("/generate_note")
def generate_note(data: VideoRequest, background_tasks: BackgroundTasks):
    try:
        # 就绪门禁：本地转写引擎（fast-whisper / mlx-whisper）必须等模型下载完才能跑视频，
        # 否则任务会卡在首次下载（慢 / OOM / 截断），用户只看到一个静默失败的任务。
        # 客户端已抓好字幕（prefetched_transcript）则不需要转写，跳过检查。
        if not data.prefetched_transcript:
            from app.services.transcriber_config_manager import TranscriberConfigManager
            readiness = TranscriberConfigManager().is_model_ready()
            if not readiness["ready"]:
                logger.warning(f"拒绝 generate_note：{readiness['reason']}")
                return R.error(
                    msg=readiness["reason"],
                    code=300102,
                    data={
                        "reason": "transcriber_model_not_ready",
                        "transcriber_type": readiness["transcriber_type"],
                        "model_size": readiness["model_size"],
                        "downloading": readiness["downloading"],
                    },
                )

        video_id = extract_video_id(data.video_url, data.platform)
        # if not video_id:
        #     raise HTTPException(status_code=400, detail="无法提取视频 ID")
        # existing = get_task_by_video(video_id, data.platform)
        # if existing:
        #     return R.error(
        #         msg='笔记已生成，请勿重复发起',
        #
        #     )
        if data.task_id:
            # 如果传了task_id，说明是重试！
            task_id = data.task_id
            logger.info(f"重试模式，复用已有 task_id={task_id}")
        else:
            # 正常新建任务
            task_id = str(uuid.uuid4())

        # 统一先写入 PENDING，表示已进入队列等待串行执行
        NoteGenerator()._update_status(task_id, TaskStatus.PENDING)

        # 入口即落盘表单参数（{task_id}_meta.json）：进行中/失败的任务也能从「生成历史」
        # 恢复出完整 formData，支持重试与 AI 问答。重试复用 task_id 时 merge 覆盖为最新参数。
        save_task_meta(task_id, {
            "task_id": task_id,
            "video_url": data.video_url,
            "video_id": video_id,
            "platform": data.platform,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "form_data": data.model_dump(exclude={"prefetched_transcript"}),
        }, merge=True)

        # 客户端已经抓好字幕的话，写到转写缓存文件，NoteGenerator 的 cache-hit 逻辑会直接用上
        if data.prefetched_transcript:
            try:
                _persist_prefetched_transcript(task_id, data.prefetched_transcript)
            except Exception as e:
                logger.warning(f"写入预取字幕失败 (task_id={task_id}): {e}")

        background_tasks.add_task(run_note_task, task_id, data.video_url, data.platform, data.quality, data.link,
                                  data.screenshot, data.model_name, data.provider_id, data.reasoning_effort,
                                  data.format, data.style, data.extras, data.video_understanding,
                                  data.video_interval, data.grid_size)
        return R.success({"task_id": task_id})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/task_list")
def get_task_list():
    """列出所有历史任务（轻量：不含 markdown/transcript 全文）。

    数据源为 note_results/ 文件扫描（status.json 在任务入口就写，覆盖进行中/失败态；
    video_tasks 表只在成功后才有记录，故只作兜底而不是主数据源）。
    全文由前端按需调 /task_status/{task_id} 获取。
    """
    tasks = []
    for tid in list_task_ids():
        try:
            meta = load_task_meta(tid)
            status_data = {}
            status_path = os.path.join(NOTE_OUTPUT_DIR, f"{tid}.status.json")
            if os.path.exists(status_path):
                try:
                    with open(status_path, "r", encoding="utf-8") as f:
                        status_data = json.load(f)
                except Exception:
                    status_data = {}
            has_result = os.path.exists(os.path.join(NOTE_OUTPUT_DIR, f"{tid}.json"))
            status = status_data.get("status") or (TaskStatus.SUCCESS.value if has_result else TaskStatus.PENDING.value)
            tasks.append({
                "task_id": tid,
                "status": status,
                "message": status_data.get("message", ""),
                "created_at": meta.get("created_at", ""),
                "video_id": meta.get("video_id", ""),
                "platform": meta.get("platform", ""),
                "title": meta.get("title", ""),
                "cover_url": meta.get("cover_url", ""),
                "has_result": has_result,
                "form_data": meta.get("form_data", {}),
            })
        except Exception as e:
            # 单个任务的文件损坏不影响整个列表
            logger.warning(f"读取任务 {tid} 信息失败，跳过：{e}")
    return R.success({"tasks": tasks})


@router.get("/task_status/{task_id}")
def get_task_status(task_id: str):
    status_path = os.path.join(NOTE_OUTPUT_DIR, f"{task_id}.status.json")
    result_path = os.path.join(NOTE_OUTPUT_DIR, f"{task_id}.json")

    # 优先读状态文件
    if os.path.exists(status_path):
        with open(status_path, "r", encoding="utf-8") as f:
            status_content = json.load(f)

        status = status_content.get("status")
        message = status_content.get("message", "")

        if status == TaskStatus.SUCCESS.value:
            # 成功状态的话，继续读取最终笔记内容
            if os.path.exists(result_path):
                with open(result_path, "r", encoding="utf-8") as rf:
                    result_content = json.load(rf)
                return R.success({
                    "status": status,
                    "result": result_content,
                    "message": message,
                    "task_id": task_id
                })
            else:
                # 理论上不会出现，保险处理
                return R.success({
                    "status": TaskStatus.PENDING.value,
                    "message": "任务完成，但结果文件未找到",
                    "task_id": task_id
                })

        if status == TaskStatus.FAILED.value:
            return R.error(message or "任务失败", code=500)

        # 处理中状态
        return R.success({
            "status": status,
            "message": message,
            "task_id": task_id
        })

    # 没有状态文件，但有结果
    if os.path.exists(result_path):
        with open(result_path, "r", encoding="utf-8") as f:
            result_content = json.load(f)
        return R.success({
            "status": TaskStatus.SUCCESS.value,
            "result": result_content,
            "task_id": task_id
        })

    # 什么都没有，默认PENDING
    return R.success({
        "status": TaskStatus.PENDING.value,
        "message": "任务排队中",
        "task_id": task_id
    })


@router.get("/image_proxy")
async def image_proxy(request: Request, url: str):
    headers = {
        "Referer": "https://www.bilibili.com/",
        "User-Agent": request.headers.get("User-Agent", ""),
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)

            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail="图片获取失败")

            content_type = resp.headers.get("Content-Type", "image/jpeg")
            return StreamingResponse(
                resp.aiter_bytes(),
                media_type=content_type,
                headers={
                    "Cache-Control": "public, max-age=86400",  #  缓存一天
                    "Content-Type": content_type,
                }
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
