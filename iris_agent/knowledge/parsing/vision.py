"""Local vision-model adapter for image and scanned-page knowledge ingestion."""

from __future__ import annotations

import base64

import httpx

from iris_agent.knowledge.parsing.base import ParsingError


class OllamaImageDescriber:
    def __init__(self, *, model: str, base_url: str, timeout: float = 120) -> None:
        if not model.strip():
            raise ValueError("image parsing model must be non-blank")
        self.model = model.strip()
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(timeout=timeout)

    def describe(self, content: bytes, name: str) -> str:
        response = self.client.post(f"{self.base_url}/api/generate", json={
            "model": self.model,
            "prompt": (
                f"请提取并描述图片《{name}》中可用于知识检索的信息。"
                "准确抄录可辨认文字、表格、公式和图中关系；不要编造；直接输出结构化纯文本。"
            ),
            "images": [base64.b64encode(content).decode("ascii")],
            "stream": False,
            "options": {"temperature": 0},
        })
        try:
            response.raise_for_status()
            text = str(response.json().get("response") or "").strip()
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise ParsingError(f"视觉解析失败：{exc}") from exc
        if not text:
            raise ParsingError("视觉解析模型未返回可索引内容")
        return text

    def close(self) -> None:
        self.client.close()
