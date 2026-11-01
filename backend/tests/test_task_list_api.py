"""GET /api/task_list 路由测试：字段透传、杂质文件排除、单文件损坏不炸接口。

依赖完整 app 包（fastapi/pydantic 等），在装好 requirements 的环境（容器）里运行。
"""
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import app.routers.note as rn
import app.services.task_meta as tm


class TestTaskListApi(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)

    def _make_task(self, tid: str, *, status=None, result=False, meta=None):
        if status is not None:
            (self.base / f"{tid}.status.json").write_text(
                json.dumps({"status": status}), encoding="utf-8")
        if result:
            (self.base / f"{tid}.json").write_text(
                json.dumps({"markdown": "m"}), encoding="utf-8")
        if meta is not None:
            (self.base / f"{tid}_meta.json").write_text(
                json.dumps(meta, ensure_ascii=False), encoding="utf-8")

    def test_fields_are_passed_through(self):
        tid = str(uuid.uuid4())
        self._make_task(tid, status="SUCCESS", result=True, meta={
            "created_at": "2026-01-01T00:00:00",
            "video_id": "BV1xx",
            "platform": "bilibili",
            "title": "标题",
            "cover_url": "http://x/c.jpg",
            "form_data": {"style": "minimal", "reasoning_effort": "low"},
        })

        with patch.object(rn, "NOTE_OUTPUT_DIR", str(self.base)), \
             patch.object(tm, "NOTE_OUTPUT_DIR", self.base):
            res = rn.get_task_list()

        self.assertEqual(res.status_code, 200)
        body = json.loads(res.body)
        self.assertEqual(body["code"], 0)
        tasks = body["data"]["tasks"]
        self.assertEqual(len(tasks), 1)
        t = tasks[0]
        self.assertEqual(t["task_id"], tid)
        self.assertEqual(t["status"], "SUCCESS")
        self.assertTrue(t["has_result"])
        self.assertEqual(t["title"], "标题")
        self.assertEqual(t["form_data"]["reasoning_effort"], "low")
        self.assertEqual(t["video_id"], "BV1xx")

    def test_status_without_result_is_not_success(self):
        """只有 status.json（进行中/失败）的任务 has_result=False、状态透传。"""
        tid = str(uuid.uuid4())
        self._make_task(tid, status="TRANSCRIBING", meta={"platform": "bilibili"})

        with patch.object(rn, "NOTE_OUTPUT_DIR", str(self.base)), \
             patch.object(tm, "NOTE_OUTPUT_DIR", self.base):
            tasks = json.loads(rn.get_task_list().body)["data"]["tasks"]

        self.assertEqual(tasks[0]["status"], "TRANSCRIBING")
        self.assertFalse(tasks[0]["has_result"])

    def test_result_without_status_counts_as_success(self):
        tid = str(uuid.uuid4())
        self._make_task(tid, result=True)

        with patch.object(rn, "NOTE_OUTPUT_DIR", str(self.base)), \
             patch.object(tm, "NOTE_OUTPUT_DIR", self.base):
            tasks = json.loads(rn.get_task_list().body)["data"]["tasks"]

        self.assertEqual(tasks[0]["status"], "SUCCESS")
        self.assertTrue(tasks[0]["has_result"])

    def test_corrupt_status_file_does_not_break_api(self):
        """status.json 损坏 → 该任务按 result 文件兜底，接口不炸。"""
        tid = str(uuid.uuid4())
        self._make_task(tid, result=True)
        (self.base / f"{tid}.status.json").write_text("{broken", encoding="utf-8")

        with patch.object(rn, "NOTE_OUTPUT_DIR", str(self.base)), \
             patch.object(tm, "NOTE_OUTPUT_DIR", self.base):
            tasks = json.loads(rn.get_task_list().body)["data"]["tasks"]

        self.assertEqual(tasks[0]["status"], "SUCCESS")

    def test_meta_without_form_data_defaults(self):
        tid = str(uuid.uuid4())
        self._make_task(tid, status="SUCCESS", result=True)

        with patch.object(rn, "NOTE_OUTPUT_DIR", str(self.base)), \
             patch.object(tm, "NOTE_OUTPUT_DIR", self.base):
            tasks = json.loads(rn.get_task_list().body)["data"]["tasks"]

        self.assertEqual(tasks[0]["form_data"], {})
        self.assertEqual(tasks[0]["title"], "")


if __name__ == "__main__":
    unittest.main()
