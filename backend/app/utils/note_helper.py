import re


def prepend_source_link(markdown: str | None, source_url: str) -> str | None:
    """
    在笔记开头添加来源链接；若首个非空行已包含来源链接，则更新该行并避免重复。
    """
    if markdown is None:
        return None

    source = (source_url or "").strip()
    if not source:
        return markdown

    header = f"> 来源链接：{source}"
    lines = markdown.splitlines()
    first_non_empty_idx = None
    for idx, line in enumerate(lines):
        if line.strip():
            first_non_empty_idx = idx
            break

    if first_non_empty_idx is not None:
        first_line = lines[first_non_empty_idx].strip()
        if first_line.startswith("> 来源链接：") or first_line.startswith("来源链接："):
            lines[first_non_empty_idx] = header
            return "\n".join(lines)

    if markdown.strip():
        return f"{header}\n\n{markdown}"
    return header


def replace_content_markers(markdown: str, video_id: str, platform: str = 'bilibili') -> str:
    """
    替换 *Content-04:16*、Content-04:16 或 Content-[04:16] 为超链接，跳转到对应平台视频的时间位置
    """
    # 匹配 *Content-04:16*、Content-04:16、Content-[04:16]，兼容 HH:MM:SS 与超过 99 分钟的写法
    pattern = r"\*?Content-\[?(\d{1,3}):(\d{2})(?::(\d{2}))?\]?\*?"

    # 分 P 视频的 video_id 形如 BV1xx_p2，需转换为 ?p= 查询参数
    parsed_video_id = video_id.replace("_p", "?p=")

    def replacer(match):
        if match.group(3) is not None:
            # HH:MM:SS 形式
            hh, mm, ss = match.group(1), match.group(2), match.group(3)
            label = f"{hh}:{mm}:{ss}"
            total_seconds = int(hh) * 3600 + int(mm) * 60 + int(ss)
        else:
            # MM:SS 形式（分钟允许 3 位，覆盖超过 99 分钟的视频）
            mm, ss = match.group(1), match.group(2)
            label = f"{int(mm)}:{ss}"
            total_seconds = int(mm) * 60 + int(ss)

        if platform == 'bilibili':
            # 分 P 视频已有 ?p= 查询参数，时间戳用 & 接续；普通视频用 ? 起始
            separator = "&" if "?" in parsed_video_id else "?"
            url = f"https://www.bilibili.com/video/{parsed_video_id}{separator}t={total_seconds}"
        elif platform == 'youtube':
            url = f"https://www.youtube.com/watch?v={video_id}&t={total_seconds}s"
        elif platform == 'douyin':
            url = f"https://www.douyin.com/video/{video_id}"
        else:
            return f"({label})"

        return f"[原片 @ {label}]({url})"

    return re.sub(pattern, replacer, markdown)

