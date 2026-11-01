"""task_meta 模块测试：list_task_ids 的 UUID 过滤与 save_task_meta 的 merge 语义。

task_meta.py 刻意零 app 包依赖（见其模块 docstring），这里可用 importlib 单文件
加载，不需要任何 sys.modules 桩——避免污染全局命名空间影响其他测试收集。
"""
import importlib.util
import pathlib
import tempfile
import unittest
import uuid
from pathlib import Path


def _load_task_meta():
    root = pathlib.Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "task_meta_under_test", root / "app" / "services" / "task_meta.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


task_meta = _load_task_meta()


class TestListTaskIds(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.old_dir = task_meta.NOTE_OUTPUT_DIR
        task_meta.NOTE_OUTPUT_DIR = Path(self.tmp.name)

    def tearDown(self):
        task_meta.NOTE_OUTPUT_DIR = self.old_dir

    def _write(self, name: str, content: str = "{}") -> None:
        (Path(self.tmp.name) / name).write_text(content, encoding="utf-8")

    def test_only_bare_uuid_files_are_listed(self):
        """transcript/audio/markdown/checkpoint/meta 等带后缀文件必须全部被排除。"""
        tid = str(uuid.uuid4())
        other = str(uuid.uuid4())
        self._write(f"{tid}.json", '{"markdown": "m"}')
        self._write(f"{tid}.status.json", '{"status": "SUCCESS"}')
        self._write(f"{tid}_transcript.json")
        self._write(f"{tid}_audio.json")
        self._write(f"{tid}_markdown.md", "x")
        self._write(f"{tid}_markdown.status.json")
        self._write(f"{tid}.gpt.checkpoint.json")
        self._write(f"{tid}_meta.json")
        self._write(f"{other}.status.json")
        self._write("not-a-uuid.json")
        self._write("random.txt")

        self.assertEqual(sorted(task_meta.list_task_ids()), sorted([tid, other]))

    def test_sorted_by_mtime_desc(self):
        a, b = str(uuid.uuid4()), str(uuid.uuid4())
        self._write(f"{a}.json")
        self._write(f"{b}.json")
        # 把 a 的 mtime 调旧，b 应排在前
        import os
        os.utime(Path(self.tmp.name) / f"{a}.json", (0, 0))

        self.assertEqual(task_meta.list_task_ids()[0], b)

    def test_missing_dir_returns_empty(self):
        task_meta.NOTE_OUTPUT_DIR = Path(self.tmp.name) / "not-exist"
        self.assertEqual(task_meta.list_task_ids(), [])


class TestSaveTaskMeta(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.old_dir = task_meta.NOTE_OUTPUT_DIR
        task_meta.NOTE_OUTPUT_DIR = Path(self.tmp.name)

    def tearDown(self):
        task_meta.NOTE_OUTPUT_DIR = self.old_dir

    def test_merge_preserves_existing_fields(self):
        """成功后补 title 不应抹掉入口时写的 form_data。"""
        tid = str(uuid.uuid4())
        task_meta.save_task_meta(tid, {"form_data": {"style": "minimal"}, "platform": "bilibili"})
        task_meta.save_task_meta(tid, {"title": "t"}, merge=True)

        loaded = task_meta.load_task_meta(tid)
        self.assertEqual(loaded["title"], "t")
        self.assertEqual(loaded["form_data"], {"style": "minimal"})
        self.assertEqual(loaded["platform"], "bilibili")

    def test_merge_overwrites_same_key(self):
        """重试时 form_data 应整体替换为最新参数。"""
        tid = str(uuid.uuid4())
        task_meta.save_task_meta(tid, {"form_data": {"style": "a"}})
        task_meta.save_task_meta(tid, {"form_data": {"style": "b"}}, merge=True)
        self.assertEqual(task_meta.load_task_meta(tid)["form_data"], {"style": "b"})

    def test_no_merge_replaces_whole_file(self):
        tid = str(uuid.uuid4())
        task_meta.save_task_meta(tid, {"a": 1})
        task_meta.save_task_meta(tid, {"b": 2}, merge=False)
        self.assertEqual(task_meta.load_task_meta(tid), {"b": 2})

    def test_empty_task_id_noop(self):
        task_meta.save_task_meta("", {"a": 1})
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
