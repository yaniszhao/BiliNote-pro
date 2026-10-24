import math
import os
import shutil
import tempfile
from abc import ABC
from typing import List, Optional

import ffmpeg

from app.decorators.timeit import timeit
from app.models.transcriber_model import TranscriptResult, TranscriptSegment
from app.services.provider import ProviderService
from app.transcriber.base import Transcriber
from app.utils.logger import get_logger
from app.utils.openai_client import build_openai_client
from dotenv import load_dotenv

load_dotenv()

logger = get_logger(__name__)

# Groq multipart 请求体上限是 25MB（free tier），留 1MB 余量容纳 multipart
# 边界、表单字段与文件名等开销。
MAX_SIZE_MB = 18
MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024
# 切片目标 12MB。不能用 24MB：按实测码率反算出的 ~3146s/片，Groq 转写约 108s，
# 贴着 Cloudflare 对 api.groq.com 的 120s Proxy Read Timeout 红线，源站稍慢就
# 触发 524（retryable 但重试也无法恢复——每次都撞同一堵墙）。
CHUNK_TARGET_BYTES = 12 * 1024 * 1024
CHUNK_TARGET_SECONDS = 300  # 兜底切片时长（秒），探测不到音频总时长时使用


def _get_audio_duration(file_path: str) -> Optional[float]:
    """用 ffmpeg-python probe 音频时长，失败返回 None（调用方走兜底切片时长）。"""
    try:
        return float(ffmpeg.probe(file_path)["format"]["duration"])
    except Exception as e:
        logger.warning(f"探测音频时长失败，将按默认 {CHUNK_TARGET_SECONDS}s 切片：{e}")
        return None


def _compute_chunk_seconds(file_size: int, duration: Optional[float]) -> float:
    """按目标字节数反算每片时长，假设码率均匀（下载器产出的 mp3 是 CBR 64k）。"""
    if duration:
        avg_bps = file_size * 8 / duration
        return max(30.0, CHUNK_TARGET_BYTES * 8 / avg_bps)
    return CHUNK_TARGET_SECONDS


def split_audio(file_path: str, chunk_seconds: float, output_dir: str) -> List[str]:
    """把音频切成若干段（-c copy 流式切割，不重编码），返回按顺序的切片路径。

    切点不做语音静音对齐：Whisper 各片独立解码，边界处可能损失/多出半句话，
    对笔记摘要场景可接受；切片仅在本文件超过 Groq 上限时才发生。
    """
    duration = _get_audio_duration(file_path)
    if duration:
        total_chunks = max(1, math.ceil(duration / chunk_seconds))
    else:
        # 时长未知：按兜底时长循环切，切到空片为止
        total_chunks = None

    base = os.path.splitext(os.path.basename(file_path))[0]
    chunk_paths: List[str] = []
    idx = 0
    while total_chunks is None or idx < total_chunks:
        start = idx * chunk_seconds
        output_fd, output_path = tempfile.mkstemp(
            prefix=f"{base}_chunk{idx:03d}_", suffix=".mp3", dir=output_dir
        )
        os.close(output_fd)
        stream = ffmpeg.input(file_path, ss=start)
        # 已知时长时，最后一片不设 t，让 ffmpeg 截到文件末尾
        if duration and idx < total_chunks - 1:
            stream = stream.output(output_path, t=chunk_seconds, codec="copy")
        else:
            stream = stream.output(output_path, codec="copy")
        try:
            stream.run(quiet=True, overwrite_output=True)
        except ffmpeg.Error as e:
            # 时长未知模式下，超出末尾的起切点会产出空/无效文件，视为切片结束
            if total_chunks is None and idx > 0:
                os.unlink(output_path)
                break
            raise
        if os.path.getsize(output_path) == 0:
            os.unlink(output_path)
            if total_chunks is None:
                break
            # 已知时长下不应出现空片，跳过即可
            idx += 1
            continue
        chunk_paths.append(output_path)
        logger.info(f"音频切片 {idx + 1}/{total_chunks or '?'}: {os.path.basename(output_path)}")
        idx += 1
    return chunk_paths


def compress_audio(input_path: str, target_bitrate: str = '64k') -> str:
    output_fd, output_path = tempfile.mkstemp(suffix=".mp3")  # 临时输出文件
    os.close(output_fd)  # 关闭文件描述符，ffmpeg 会用路径操作
    ffmpeg.input(input_path).output(output_path, audio_bitrate=target_bitrate).run(quiet=True, overwrite_output=True)
    return output_path


class GroqTranscriber(Transcriber, ABC):

    def _build_client(self, provider):
        return build_openai_client(
            api_key=provider.get('api_key'),
            base_url=provider.get('base_url'),
            key_label="Groq 转写引擎的 API Key",
        )

    @timeit
    def transcript(self, file_path: str) -> TranscriptResult:
        file_size = os.path.getsize(file_path)
        provider = ProviderService.get_provider_by_id('groq')
        if not provider:
            raise Exception("Groq 供应商未配置,请配置以后使用。")

        chunk_paths: List[str] = []
        temp_dir: Optional[str] = None
        try:
            if file_size > MAX_SIZE_BYTES:
                duration = _get_audio_duration(file_path)
                chunk_seconds = _compute_chunk_seconds(file_size, duration)
                logger.info(
                    f"音频 {round(file_size / (1024 * 1024), 2)}MB 超过 Groq 单请求上限"
                    f"({MAX_SIZE_MB}MB)，开始切片转写（每片约 {round(chunk_seconds)}s）..."
                )
                temp_dir = tempfile.mkdtemp(prefix="groq_chunks_")
                chunk_paths = split_audio(file_path, chunk_seconds, temp_dir)
            else:
                chunk_paths = [file_path]

            client = self._build_client(provider)
            model = os.getenv('GROQ_TRANSCRIBER_MODEL')

            segments: List[TranscriptSegment] = []
            full_text_parts: List[str] = []
            language: Optional[str] = None
            raw_chunks = []
            offset = 0.0  # 已处理音频的累计时长，用于时间戳平移

            for idx, chunk_path in enumerate(chunk_paths):
                logger.info(f"转写切片 {idx + 1}/{len(chunk_paths)}...")
                with open(chunk_path, "rb") as file:
                    transcription = client.audio.transcriptions.create(
                        file=(os.path.basename(chunk_path), file.read()),
                        model=model,
                        response_format="verbose_json",
                    )
                if language is None:
                    language = transcription.language

                chunk_covered = 0.0  # 本片实际覆盖的音频时长
                for seg in transcription.segments or []:
                    text = seg.text.strip()
                    if not text:
                        continue
                    chunk_covered = max(chunk_covered, seg.end)
                    segments.append(TranscriptSegment(
                        start=offset + seg.start,
                        end=offset + seg.end,
                        text=text,
                    ))
                    full_text_parts.append(text)

                # 下一片的偏移：切片时设定的时长是精确的（t=chunk_seconds），
                # 只有最后一片（无 t）和未知总时长模式才依赖转写结果估算
                if chunk_paths and idx < len(chunk_paths) - 1:
                    offset += chunk_seconds if duration else chunk_covered
                else:
                    offset += chunk_covered
                raw_chunks.append(transcription.to_dict())

            raw = raw_chunks[0] if len(raw_chunks) == 1 else {"chunks": raw_chunks}
            return TranscriptResult(
                language=language,
                full_text=" ".join(full_text_parts).strip(),
                segments=segments,
                raw=raw,
            )
        finally:
            # 清理切片临时文件；原始音频不动（下载器有自己的缓存管理）
            if temp_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)
