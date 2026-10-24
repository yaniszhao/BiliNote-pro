"""
TDD coverage for GroqTranscriber chunked transcription (413 fix).

Background: 2026-10-24 task 7abf79ed failed — a 58-minute video produced a
26.8MB mp3 that exceeds Groq's 25MB multipart limit (free tier). The old code
only "compressed" to 64k (already 64k → no-op) and still sent one oversized
request. Fix: split the audio into <=24MB chunks with ffmpeg `-c copy`,
transcribe each chunk, then merge segments with a global time offset.

Test strategy:
- split_audio / _get_audio_duration / _compute_chunk_seconds: run REAL ffmpeg
  on tiny synthetic mp3s.
- GroqTranscriber.transcript merge/offset logic: mock split_audio + API client
  (no network, no long audio needed).
"""
import math
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import ffmpeg as ffmpeg_pkg

from app.transcriber import groq as groq_module
from app.transcriber.groq import (
    GroqTranscriber,
    _compute_chunk_seconds,
    _get_audio_duration,
    split_audio,
)


def _make_mp3(path, seconds, sample_rate=8000, bitrate="16k"):
    """用 ffmpeg 生成真实 mp3（低码率低采样率，测试只关心大小/时长）。"""
    (
        ffmpeg_pkg.input("anullsrc", format="lavfi", t=seconds)
        .output(path, acodec="libmp3lame", audio_bitrate=bitrate, ar=sample_rate)
        .run(quiet=True, overwrite_output=True)
    )


class _FakeSegment:
    def __init__(self, start, end, text):
        self.start = start
        self.end = end
        self.text = text


class _FakeTranscription:
    """模拟 openai verbose_json 返回，带 .language/.segments/.to_dict()。"""

    def __init__(self, language, segments, chunk_id):
        self.language = language
        self.segments = segments
        self._chunk_id = chunk_id

    def to_dict(self):
        return {"chunk_id": self._chunk_id, "segments": list(self.segments)}


class TestGetAudioDuration(unittest.TestCase):
    def test_returns_duration_for_valid_mp3(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.mp3")
            _make_mp3(path, 5)
            duration = _get_audio_duration(path)
            self.assertIsNotNone(duration)
            self.assertAlmostEqual(duration, 5, delta=1)

    def test_returns_none_for_invalid_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "not_audio.mp3")
            with open(path, "w") as f:
                f.write("this is not audio")
            self.assertIsNone(_get_audio_duration(path))


class TestComputeChunkSeconds(unittest.TestCase):
    def test_scales_with_bitrate_for_known_duration(self):
        """26.8MB / 58 分钟 (64kbps) 场景：每片 ≈ 24MB*8/64kbps ≈ 3146s，共 2 片。"""
        file_size = 28_139_916
        duration = 3517.38
        chunk_seconds = _compute_chunk_seconds(file_size, duration)
        expected = groq_module.CHUNK_TARGET_BYTES * 8 / (file_size * 8 / duration)
        self.assertAlmostEqual(chunk_seconds, expected, delta=5)
        self.assertEqual(math.ceil(duration / chunk_seconds), 2)

    def test_fallback_when_duration_unknown(self):
        self.assertEqual(_compute_chunk_seconds(28_139_916, None),
                         groq_module.CHUNK_TARGET_SECONDS)


class TestSplitAudio(unittest.TestCase):
    def test_no_split_when_duration_below_chunk_seconds(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "src.mp3")
            out_dir = os.path.join(tmp, "chunks")
            os.mkdir(out_dir)
            _make_mp3(src, 10)
            chunks = split_audio(src, chunk_seconds=30, output_dir=out_dir)
            self.assertEqual(len(chunks), 1)
            self.assertGreater(os.path.getsize(chunks[0]), 0)

    def test_splits_known_duration_into_expected_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "src.mp3")
            out_dir = os.path.join(tmp, "chunks")
            os.mkdir(out_dir)
            _make_mp3(src, 30)
            # 30s 音频按 12s 切 → 3 片
            chunks = split_audio(src, chunk_seconds=12, output_dir=out_dir)
            self.assertEqual(len(chunks), 3)
            for c in chunks:
                self.assertGreater(os.path.getsize(c), 0)
            # 前两片时长 ≈ 12s（容器级误差容忍 1s）
            for c in chunks[:2]:
                self.assertAlmostEqual(_get_audio_duration(c), 12, delta=1)


class _ChunkFixture:
    """构造 transcript() 的测试环境：mock 时长探测/切片/API 客户端。

    file_size_bytes 决定音频文件的实际大小（触发/绕过大小判断）；
    chunk_seconds 模拟切片步长；每个 chunk 是 (切片真实覆盖时长, FakeTranscription)。
    """

    def __init__(self, tmp, chunk_seconds, chunks, file_size_bytes):
        self.chunk_seconds = chunk_seconds
        self.fake_chunks = chunks  # [(covered, transcription), ...]
        self.tmp = tmp
        self.captured_names = []
        self.audio = os.path.join(tmp, "big.mp3")
        # 文件必须真实达到 file_size_bytes，transcript() 的 getsize 判断才生效
        with open(self.audio, "wb") as f:
            f.write(b"a" * file_size_bytes)

        self._fake_paths = [
            os.path.join(tmp, f"chunk_{i:03d}.mp3") for i in range(len(chunks))
        ]
        for p in self._fake_paths:
            with open(p, "wb") as f:
                f.write(b"fake-audio-bytes")

    def _fake_split_audio(self, file_path, chunk_seconds, output_dir):
        self._split_args = (file_path, chunk_seconds, output_dir)
        return self._fake_paths

    def _make_client(self, provider):
        client = MagicMock()

        def create(**kwargs):
            idx = self.captured_names.count("")  # unused; index via name below
            return None

        responses = iter([t for _, t in self.fake_chunks])

        def create_side_effect(**kwargs):
            self.captured_names.append(kwargs["file"][0])
            return next(responses)

        client.audio.transcriptions.create.side_effect = create_side_effect
        return client

    def run(self):
        covered_list = [c for c, _ in self.fake_chunks]
        client = self._make_client(None)

        with patch.object(groq_module, "MAX_SIZE_BYTES", os.path.getsize(self.audio) - 1), \
             patch.object(groq_module, "_get_audio_duration", return_value=60.0), \
             patch.object(groq_module, "_compute_chunk_seconds",
                          return_value=self.chunk_seconds), \
             patch.object(groq_module, "split_audio", self._fake_split_audio), \
             patch.object(GroqTranscriber, "_build_client", return_value=client):
            transcriber = GroqTranscriber()
            result = transcriber.transcript(file_path=self.audio)

        # 模拟实现的 offset 推进：非末片加固定步长，末片加实际覆盖时长
        expected_offsets = []
        offset = 0.0
        for i in range(len(self.fake_chunks)):
            expected_offsets.append(offset)
            if i < len(self.fake_chunks) - 1:
                offset += self.chunk_seconds
            else:
                offset += covered_list[i]
        assert self._split_args[1] == self.chunk_seconds
        assert self.captured_names == [os.path.basename(p) for p in self._fake_paths]
        return result, expected_offsets


class TestGroqTranscriberMerge(unittest.TestCase):
    def test_single_chunk_when_under_limit(self):
        """小于上限：不切片，直接单请求，raw 不包 chunks。"""
        with tempfile.TemporaryDirectory() as tmp:
            audio = os.path.join(tmp, "small.mp3")
            with open(audio, "wb") as f:
                f.write(b"audio")
            # MAX_SIZE_BYTES 很大 → 不走切片路径；单响应
            with patch.object(groq_module, "MAX_SIZE_BYTES", 1 << 30), \
                 patch.object(groq_module, "split_audio") as m_split, \
                 patch.object(GroqTranscriber, "_build_client") as m_client:
                client = MagicMock()
                client.audio.transcriptions.create.return_value = _FakeTranscription(
                    "zh", [_FakeSegment(0, 5, "hello")], 0)
                m_client.return_value = client
                result = GroqTranscriber().transcript(file_path=audio)
            m_split.assert_not_called()
            self.assertEqual(result.language, "zh")
            self.assertEqual(result.segments[0].start, 0)
            self.assertEqual(result.segments[0].end, 5)
            self.assertEqual(result.full_text, "hello")
            self.assertIn("chunk_id", result.raw)
            self.assertNotIn("chunks", result.raw)

    def test_multi_chunk_offsets_are_cumulative(self):
        """3 片各 20s（chunk_seconds=20），时间戳应平移 0/20/40。"""
        with tempfile.TemporaryDirectory() as tmp:
            fixture = _ChunkFixture(tmp, chunk_seconds=20, file_size_bytes=100, chunks=[
                (20.0, _FakeTranscription("zh", [
                    _FakeSegment(0, 8, "one"), _FakeSegment(8, 9.5, "two")], 0)),
                (20.0, _FakeTranscription("zh", [_FakeSegment(0.5, 6, "three")], 1)),
                (18.0, _FakeTranscription("zh", [_FakeSegment(0, 7, "four")], 2)),
            ])
            result, expected_offsets = fixture.run()
            self.assertEqual(len(result.segments), 4)
            self.assertEqual([s.start for s in result.segments],
                             [0, 8, 20.5, 40])
            self.assertEqual([s.end for s in result.segments],
                             [8, 9.5, 26, 47])
            self.assertEqual(result.full_text, "one two three four")
            self.assertEqual(result.language, "zh")
            # 多片 raw 包在 chunks 列表里
            self.assertIn("chunks", result.raw)
            self.assertEqual(len(result.raw["chunks"]), 3)

    def test_empty_segment_texts_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = _ChunkFixture(tmp, chunk_seconds=10, file_size_bytes=100, chunks=[
                (10.0, _FakeTranscription("zh", [
                    _FakeSegment(0, 5, "  "), _FakeSegment(5, 9, "real")], 0)),
                (8.0, _FakeTranscription("zh", [_FakeSegment(0, 4, "next")], 1)),
            ])
            result, _ = fixture.run()
            self.assertEqual([s.text for s in result.segments], ["real", "next"])
            self.assertEqual(result.full_text, "real next")

    def test_real_split_audio_feeds_transcriber_end_to_end(self):
        """集成冒烟：真实 ffmpeg 切片（mock 掉大小判断让小文件也切片）+ mock API。"""
        with tempfile.TemporaryDirectory() as tmp:
            audio = os.path.join(tmp, "real.mp3")
            _make_mp3(audio, 30)  # 30s 真实音频
            client = MagicMock()
            responses = iter([
                _FakeTranscription("zh", [_FakeSegment(0, 9, "part-a")], 0),
                _FakeTranscription("zh", [_FakeSegment(0, 8, "part-b")], 1),
            ])

            def create_side_effect(**kwargs):
                # 每次调用返回下一个响应；文件名应带 chunk 序号
                return next(responses)

            client.audio.transcriptions.create.side_effect = create_side_effect

            with patch.object(groq_module, "MAX_SIZE_BYTES", -1), \
                 patch.object(groq_module, "_get_audio_duration", return_value=30.0), \
                 patch.object(groq_module, "_compute_chunk_seconds", return_value=15.0), \
                 patch.object(GroqTranscriber, "_build_client", return_value=client):
                result = GroqTranscriber().transcript(file_path=audio)

            self.assertEqual(client.audio.transcriptions.create.call_count, 2)
            # 时间戳：片 1 offset=0，片 2 offset=15
            self.assertEqual([s.text for s in result.segments], ["part-a", "part-b"])
            self.assertEqual([s.start for s in result.segments], [0, 15])
            # 切片临时目录应被清理
            temp_dirs = [d for d in os.listdir(tmp) if d.startswith("groq_chunks_")]
            self.assertEqual(temp_dirs, [])


if __name__ == "__main__":
    unittest.main()
