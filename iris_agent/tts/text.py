from __future__ import annotations

import html
import re


_FENCED_CODE_RE = re.compile(r"```.*?```|~~~.*?~~~", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`]*)`")
_IMAGE_RE = re.compile(r"!\[([^]]*)\]\([^)]*\)")
_LINK_RE = re.compile(r"\[([^]]+)\]\([^)]*\)")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s*", re.MULTILINE)
_LIST_RE = re.compile(r"^\s*(?:[-+*]|\d+[.)])\s+", re.MULTILINE)
_QUOTE_RE = re.compile(r"^\s*>+\s?", re.MULTILINE)
_EMPHASIS_RE = re.compile(r"(?<!\\)[*_~]{1,3}")
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def speech_text_from_markdown(markdown: str) -> str:
    """Convert assistant Markdown into concise text suitable for speech."""
    text = _FENCED_CODE_RE.sub("\n", markdown)
    text = _IMAGE_RE.sub(lambda match: match.group(1), text)
    text = _LINK_RE.sub(lambda match: match.group(1), text)
    text = _INLINE_CODE_RE.sub(lambda match: match.group(1), text)
    text = _HEADING_RE.sub("", text)
    text = _LIST_RE.sub("", text)
    text = _QUOTE_RE.sub("", text)
    text = _EMPHASIS_RE.sub("", text)
    text = _HTML_TAG_RE.sub("", text)
    text = html.unescape(text)
    # The bundled Windows GPT-SoVITS runtime logs request text through a GBK
    # console. Characters outside that encoding (notably emoji) make its
    # request handler fail before inference starts.
    text = text.encode("gbk", errors="ignore").decode("gbk")
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)
