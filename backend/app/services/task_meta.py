"""任务元数据的落盘与检索。

每个任务在 note_results/ 下除结果文件外还有一份 {task_id}_meta.json（sidecar），
保存生成时的表单参数与视频元信息快照，供「生成历史」列表与恢复（重试/AI 问答）使用。

刻意只用标准库 logging 而非 app.utils.logger：本模块是文件扫描/恢复的基础设施，
被多个测试以 importlib 单文件方式加载（参考 tests/test_task_meta.py），避免拉起
整个 app 包——同时杜绝给 sys.modules 打 stub 造成的跨测试污染（见 agent-docs/gotchas.md）。
"""
import json
import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)

NOTE_OUTPUT_DIR = Path(os.getenv("NOTE_OUTPUT_DIR", "note_results"))

# 裸 UUID 形式的 task_id。note_results 下其他文件（{id}_transcript.json、
# {id}.status.json、{id}.gpt.checkpoint.json 等）的 stem 都带后缀，fullmatch 天然排除。
TASK_ID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _meta_path(task_id: str) -> Path:
    return NOTE_OUTPUT_DIR / f"{task_id}_meta.json"


def save_task_meta(task_id: str, data: dict, merge: bool = True) -> None:
    """写入任务元数据。

    :param task_id: 任务 ID
    :param data: 要写入的字段
    :param merge: True 时与已有内容合并（新值覆盖旧值），用于成功后补 title 等字段
    """
    if not task_id:
        return
    try:
        NOTE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        if merge:
            existing = load_task_meta(task_id)
            existing.update(data)
            data = existing

        target = _meta_path(task_id)
        tmp = target.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp.replace(target)  # 原子写，与 _update_status 同模式
    except Exception as e:
        logger.warning(f"写入任务元数据失败 (task_id={task_id})：{e}")


def load_task_meta(task_id: str) -> dict:
    """读取任务元数据；文件不存在或损坏时返回空 dict。"""
    try:
        path = _meta_path(task_id)
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"读取任务元数据失败 (task_id={task_id})：{e}")
        return {}


def list_task_ids() -> list[str]:
    """扫描 note_results 目录，返回所有任务的 task_id（按最新活动 mtime 降序）。

    只认裸 UUID 命名的 {task_id}.json / {task_id}.status.json，
    其他辅助文件（转写缓存、音频缓存、markdown 缓存、checkpoint、meta）一律排除。
    """
    try:
        NOTE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        mtime: dict[str, float] = {}
        for name in os.listdir(NOTE_OUTPUT_DIR):
            stem, ext = os.path.splitext(name)
            if ext != ".json":
                continue
            # {task_id}.status.json 的 stem 还带 .status，需再剥一层
            inner = os.path.splitext(stem)[0]
            for candidate in (stem, inner):
                if TASK_ID_RE.fullmatch(candidate):
                    try:
                        m = os.path.getmtime(NOTE_OUTPUT_DIR / name)
                    except OSError:
                        continue
                    mtime[candidate] = max(mtime.get(candidate, 0), m)
                    break
        return [tid for tid, _ in sorted(mtime.items(), key=lambda kv: -kv[1])]
    except Exception as e:
        logger.error(f"扫描任务列表失败：{e}")
        return []


NOTE_OUTPUT_DIR = Path(os.getenv("NOTE_OUTPUT_DIR", "note_results"))

# 裸 UUID 形式的 task_id。note_results 下其他文件（{id}_transcript.json、
# {id}.status.json、{id}.gpt.checkpoint.json 等）的 stem 都带后缀，fullmatch 天然排除。
TASK_ID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _meta_path(task_id: str) -> Path:
    return NOTE_OUTPUT_DIR / f"{task_id}_meta.json"


def save_task_meta(task_id: str, data: dict, merge: bool = True) -> None:
    """写入任务元数据。

    :param task_id: 任务 ID
    :param data: 要写入的字段
    :param merge: True 时与已有内容合并（新值覆盖旧值），用于成功后补 title 等字段
    """
    if not task_id:
        return
    try:
        NOTE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        if merge:
            existing = load_task_meta(task_id)
            existing.update(data)
            data = existing

        target = _meta_path(task_id)
        tmp = target.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp.replace(target)  # 原子写，与 _update_status 同模式
    except Exception as e:
        logger.warning(f"写入任务元数据失败 (task_id={task_id})：{e}")


def load_task_meta(task_id: str) -> dict:
    """读取任务元数据；文件不存在或损坏时返回空 dict。"""
    try:
        path = _meta_path(task_id)
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"读取任务元数据失败 (task_id={task_id})：{e}")
        return {}


def list_task_ids() -> list[str]:
    """扫描 note_results 目录，返回所有任务的 task_id（按最新活动 mtime 降序）。

    只认裸 UUID 命名的 {task_id}.json / {task_id}.status.json，
    其他辅助文件（转写缓存、音频缓存、markdown 缓存、checkpoint、meta）一律排除。
    """
    try:
        NOTE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        mtime: dict[str, float] = {}
        for name in os.listdir(NOTE_OUTPUT_DIR):
            stem, ext = os.path.splitext(name)
            if ext != ".json":
                continue
            # {task_id}.status.json 的 stem 还带 .status，需再剥一层
            inner = os.path.splitext(stem)[0]
            for candidate in (stem, inner):
                if TASK_ID_RE.fullmatch(candidate):
                    try:
                        m = os.path.getmtime(NOTE_OUTPUT_DIR / name)
                    except OSError:
                        continue
                    mtime[candidate] = max(mtime.get(candidate, 0), m)
                    break
        return [tid for tid, _ in sorted(mtime.items(), key=lambda kv: -kv[1])]
    except Exception as e:
        logger.error(f"扫描任务列表失败：{e}")
        return []
