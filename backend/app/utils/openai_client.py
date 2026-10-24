"""统一构造 OpenAI 兼容客户端：注入全局代理 + 校验 api_key。

为什么要这一层：
  - 代理：openai SDK 默认只认进程级 HTTP_PROXY 环境变量，桌面端用户在 UI 里
    填的代理需要显式塞进 httpx.Client 才生效。
  - api_key 校验：空 key 会让 httpx 拼出非法 header `Bearer `，抛出
    `httpx.LocalProtocolError: Illegal header value b'Bearer '` 这种天书报错。
    在入口挡掉，给用户「xxx 的 API Key 未配置」这种能看懂的提示。
  - 重试：SDK 对连接中断/超时（APIConnectionError、APITimeoutError）这类
    瞬时网络故障自带重试 + 指数退避，显式设为 3 次，避免代理/节点抖动
    （如 TLS 握手被掐断）直接导致任务失败。
"""
import os
from typing import Optional

from openai import OpenAI

from app.services.proxy_config_manager import ProxyConfigManager
from app.utils.logger import get_logger

logger = get_logger(__name__)


# 连接类瞬时错误的最大重试次数，可通过环境变量覆盖
DEFAULT_MAX_RETRIES = 3


def build_openai_client(
    api_key: Optional[str],
    base_url: Optional[str],
    *,
    key_label: str = "API Key",
    timeout: Optional[float] = None,
) -> OpenAI:
    """构造 OpenAI 客户端。api_key 为空直接抛清晰错误；代理已配置则注入。

    key_label 用于错误提示，例如 "Groq 的 API Key" / "OpenAI 供应商的 API Key"。
    """
    if not api_key or not str(api_key).strip():
        raise ValueError(f"{key_label} 未配置，请先在「设置」里填写后再使用")

    max_retries = int(os.getenv("OPENAI_MAX_RETRIES", str(DEFAULT_MAX_RETRIES)))
    kwargs = {
        "api_key": str(api_key).strip(),
        "base_url": base_url,
        "max_retries": max_retries,
    }
    if timeout is not None:
        kwargs["timeout"] = timeout

    proxy_url = ProxyConfigManager().get_proxy_url()
    if proxy_url:
        # 延迟 import httpx：仅在确实要走代理时才需要
        import httpx
        kwargs["http_client"] = httpx.Client(proxy=proxy_url, timeout=timeout or 600.0)
        logger.info(f"OpenAI 客户端走代理: {proxy_url}")

    return OpenAI(**kwargs)
