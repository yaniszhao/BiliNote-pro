"""截图按任务分目录的回归测试。

mock generate_screenshot（避免 ffmpeg 依赖），断言：
1. 传 task_id 时输出目录与 URL 均带 {task_id}/ 子目录；
2. task_id 缺省时退回平铺目录（兼容旧调用路径）。
"""
import unittest
from unittest.mock import MagicMock, patch

import app.services.note as sn


class TestScreenshotSubdir(unittest.TestCase):
    def _run(self, task_id):
        gen = MagicMock(return_value="/tmp/fake/screenshot_000_x.jpg")
        with patch.object(sn, "generate_screenshot", gen):
            # 实例方法内部不依赖 self 状态，直接用 None 调用避免构造完整 NoteGenerator
            markdown = sn.NoteGenerator._insert_screenshots(
                None, "*Screenshot-00:10\n正文", "video.mp4", task_id,
            )
        return markdown, gen

    def test_url_contains_task_id_subdir(self):
        markdown, gen = self._run("abc-task")

        self.assertIn(f"/static/screenshots/abc-task/screenshot_000_x.jpg", markdown)
        output_dir = gen.call_args[0][1]
        self.assertTrue(output_dir.endswith("abc-task"))

    def test_flat_fallback_without_task_id(self):
        """不传 task_id（旧调用）退回平铺目录，URL 不含子目录层级。"""
        markdown, gen = self._run(None)

        self.assertIn("/static/screenshots/screenshot_000_x.jpg", markdown)
        output_dir = gen.call_args[0][1]
        self.assertFalse(output_dir.endswith("abc-task"))


if __name__ == "__main__":
    unittest.main()
