from __future__ import annotations

import json
from pathlib import Path
import socket
from collections.abc import Iterator
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from iris_agent.config.settings import TtsSettings

from .emotion import VoiceReference
from .errors import TtsTimeoutError, TtsUnavailableError, TtsUpstreamError


class GptSovitsClient:
    def __init__(
        self,
        settings: TtsSettings,
        *,
        open_url: Callable = urlopen,
    ) -> None:
        self.settings = settings
        self._open_url = open_url

    def is_healthy(self) -> bool:
        request = Request(f"{self.settings.base_url}/openapi.json", method="GET")
        try:
            with self._open_url(request, timeout=2) as response:
                return bool(response.read(1))
        except (OSError, HTTPError, URLError, TimeoutError):
            return False

    def set_weights(self) -> None:
        self._get(
            "/set_gpt_weights",
            {"weights_path": str(self.settings.gpt_weights_path)},
        )
        self._get(
            "/set_sovits_weights",
            {"weights_path": str(self.settings.sovits_weights_path)},
        )

    def synthesize(
        self,
        text: str,
        reference: VoiceReference | None = None,
        auxiliary: tuple[Path, ...] = (),
    ) -> bytes:
        payload = self._payload(text, reference, auxiliary, streaming=False)
        request = self._tts_request(payload)
        return self._send(request, self.settings.max_audio_bytes + 1)

    def stream_synthesize(
        self,
        text: str,
        reference: VoiceReference | None = None,
        auxiliary: tuple[Path, ...] = (),
    ) -> Iterator[bytes]:
        payload = self._payload(text, reference, auxiliary, streaming=True)
        request = self._tts_request(payload)
        try:
            with self._open_url(
                request, timeout=self.settings.request_timeout_seconds
            ) as response:
                read_chunk = getattr(response, "read1", response.read)
                while chunk := read_chunk(16 * 1024):
                    yield chunk
        except (socket.timeout, TimeoutError) as exc:
            raise TtsTimeoutError("GPT-SoVITS 请求超时") from exc
        except HTTPError as exc:
            detail = self._http_error_detail(exc)
            raise TtsUpstreamError(f"GPT-SoVITS 返回错误：{detail}") from exc
        except (URLError, OSError) as exc:
            raise TtsUnavailableError("无法连接 GPT-SoVITS 服务") from exc

    def warmup(self) -> None:
        for _ in self.stream_synthesize("你好，我是高松灯。"):
            pass

    def _payload(
        self,
        text: str,
        reference: VoiceReference | None,
        auxiliary: tuple[Path, ...],
        *,
        streaming: bool,
    ) -> dict[str, object]:
        reference_path = reference.audio_path if reference else self.settings.reference_audio_path
        prompt_text = reference.prompt_text if reference else self.settings.reference_text
        payload: dict[str, object] = {
            "text": text,
            "text_lang": self.settings.target_language,
            "ref_audio_path": str(reference_path),
            "prompt_text": prompt_text,
            "prompt_lang": self.settings.reference_language,
            "text_split_method": "cut5",
            "media_type": "wav",
            "streaming_mode": 2 if streaming else 0,
            "speed_factor": 1.0,
            "top_k": 10,
            "top_p": 0.85,
            "temperature": 0.7,
            "seed": 1234,
            "parallel_infer": True,
            "fragment_interval": 0.05,
            "repetition_penalty": 1.35,
            "overlap_length": 2,
            "min_chunk_length": 12,
        }
        if auxiliary:
            payload["aux_ref_audio_paths"] = [str(path) for path in auxiliary]
        return payload

    def _tts_request(self, payload: dict[str, object]) -> Request:
        return Request(
            f"{self.settings.base_url}/tts",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "audio/wav"},
            method="POST",
        )

    def _get(self, path: str, query: dict[str, str]) -> bytes:
        request = Request(
            f"{self.settings.base_url}{path}?{urlencode(query)}",
            method="GET",
        )
        return self._send(request, 1024 * 1024)

    def _send(self, request: Request, read_limit: int) -> bytes:
        try:
            with self._open_url(
                request, timeout=self.settings.request_timeout_seconds
            ) as response:
                return response.read(read_limit)
        except (socket.timeout, TimeoutError) as exc:
            raise TtsTimeoutError("GPT-SoVITS 请求超时") from exc
        except HTTPError as exc:
            detail = self._http_error_detail(exc)
            raise TtsUpstreamError(f"GPT-SoVITS 返回错误：{detail}") from exc
        except (URLError, OSError) as exc:
            raise TtsUnavailableError("无法连接 GPT-SoVITS 服务") from exc

    @staticmethod
    def _http_error_detail(exc: HTTPError) -> str:
        try:
            payload = json.loads(exc.read(4096).decode("utf-8", errors="replace"))
            return str(payload.get("message") or payload.get("detail") or exc.reason)
        except (OSError, ValueError, AttributeError):
            return str(exc.reason)
