"""delete_task 真删除测试：文件/截图目录清理、路径穿越防护、DAO 调用。

依赖完整 app 包，在装好 requirements 的环境（容器）里运行。
"""
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import app.routers.note as rn
import app.services.vector_store as vs


class TestDeleteTask(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.shots = self.base / "static" / "screenshots"
        self.shots.mkdir(parents=True)

        self.dao_delete = MagicMock()
        self.dao_delete_video = MagicMock()
        self.dao_get_by_video = MagicMock(return_value=[])

        patches = [
            patch.object(rn, "NOTE_OUTPUT_DIR", str(self.base)),
            patch.object(rn, "IMAGE_OUTPUT_DIR", str(self.shots)),
            patch.object(rn, "delete_task_by_task_id", self.dao_delete),
            patch.object(rn, "delete_task_by_video", self.dao_delete_video),
            patch.object(rn, "get_tasks_by_video", self.dao_get_by_video),
            # 避免测试依赖 chromadb 真实客户端
            patch.object(vs, "VectorStoreManager", MagicMock()),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def _make_artifacts(self, tid: str) -> None:
        for suffix in (
            ".json", ".status.json", "_transcript.json", "_audio.json",
            "_markdown.md", "_markdown.status.json", ".gpt.checkpoint.json", "_meta.json",
        ):
            (self.base / f"{tid}{suffix}").write_text("{}", encoding="utf-8")
        shot_dir = self.shots / tid
        shot_dir.mkdir()
        (shot_dir / "screenshot_000_x.jpg").write_bytes(b"jpg")

    def test_deletes_all_artifacts(self):
        tid = str(uuid.uuid4())
        self._make_artifacts(tid)

        res = rn.delete_task(rn.RecordRequest(task_id=tid))

        body = __import__("json").loads(res.body)
        self.assertEqual(body["code"], 0)
        remaining = [p.name for p in self.base.iterdir()]
        self.assertFalse(any(tid in name for name in remaining))
        self.assertFalse((self.shots / tid).exists())
        self.dao_delete.assert_called_once_with(tid)

    def test_missing_task_id_and_video_returns_error(self):
        res = rn.delete_task(rn.RecordRequest())
        body = __import__("json").loads(res.body)
        self.assertNotEqual(body["code"], 0)

    def test_legacy_call_uses_video_id_platform(self):
        """旧调用（video_id+platform）走 DAO 兜底查询并整组删除。"""
        t1, t2 = str(uuid.uuid4()), str(uuid.uuid4())
        self.dao_get_by_video.return_value = [MagicMock(task_id=t1), MagicMock(task_id=t2)]
        self._make_artifacts(t1)

        res = rn.delete_task(rn.RecordRequest(video_id="BV1", platform="bilibili"))

        body = __import__("json").loads(res.body)
        self.assertEqual(body["code"], 0)
        self.dao_delete_video.assert_called_once_with("BV1", "bilibili")
        self.assertFalse((self.base / f"{t1}.json").exists())

    def test_path_traversal_is_rejected(self):
        """task_id 带 ../ 时必须直接拒绝，绝不能删到 screenshots 父目录。"""
        victim = self.shots / "keep_me.jpg"
        victim.write_bytes(b"jpg")

        res = rn.delete_task(rn.RecordRequest(task_id="../static"))

        body = __import__("json").loads(res.body)
        self.assertNotEqual(body["code"], 0)
        self.assertTrue(victim.exists())
        self.dao_delete.assert_not_called()

    def test_media_files_are_deleted(self):
        """删除任务时清理 audio.json 指向的音/视频缓存文件。"""
        import json as jsonlib
        tid = str(uuid.uuid4())
        self._make_artifacts(tid)

        media_dir = self.base / "data"
        media_dir.mkdir()
        mp3 = media_dir / "BV1xx.mp3"
        mp4 = media_dir / "BV1xx.mp4"
        mp3.write_bytes(b"mp3")
        mp4.write_bytes(b"mp4")
        (self.base / f"{tid}_audio.json").write_text(jsonlib.dumps({
            "file_path": str(mp3), "video_path": None, "video_id": "BV1xx",
        }), encoding="utf-8")

        rn.delete_task(rn.RecordRequest(task_id=tid))

        self.assertFalse(mp3.exists())
        self.assertFalse(mp4.exists())

    def test_media_shared_with_other_task_is_kept(self):
        """同一视频被另一个任务引用时，媒体文件保留，只删本任务的。"""
        import json as jsonlib
        tid, other = str(uuid.uuid4()), str(uuid.uuid4())
        self._make_artifacts(tid)

        media_dir = self.base / "data"
        media_dir.mkdir()
        mp3 = media_dir / "BV1xx.mp3"
        mp3.write_bytes(b"mp3")
        (self.base / f"{tid}_audio.json").write_text(jsonlib.dumps({
            "file_path": str(mp3), "video_path": None, "video_id": "BV1xx",
        }), encoding="utf-8")
        (self.base / f"{other}_audio.json").write_text(jsonlib.dumps({
            "file_path": str(mp3), "video_path": None, "video_id": "BV1xx",
        }), encoding="utf-8")

        rn.delete_task(rn.RecordRequest(task_id=tid))

        self.assertTrue(mp3.exists())


if __name__ == "__main__":
    unittest.main()
