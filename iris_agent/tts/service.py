from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
from collections.abc import Iterator
from typing import Protocol

from iris_agent.config.settings import TtsSettings
from iris_agent.sessions.base import SessionRepository

from .errors import (
    TtsDisabledError,
    TtsMessageError,
    TtsMessageNotFoundError,
    TtsTooLargeError,
    TtsUpstreamError,
)
from .emotion import EmotionClassifier, EmotionReferenceLibrary, VoiceReference
from .text import speech_text_from_markdown


class TtsRuntime(Protocol):
    def ensure_ready(self) -> None: ...

    @property
    def status(self) -> str: ...

    @property
    def status_detail(self) -> str: ...


class TtsClient(Protocol):
    def synthesize(
        self,
        text: str,
        reference: VoiceReference | None = None,
        auxiliary: tuple[Path, ...] = (),
    ) -> bytes: ...

    def stream_synthesize(
        self,
        text: str,
        reference: VoiceReference | None = None,
        auxiliary: tuple[Path, ...] = (),
    ) -> Iterator[bytes]: ...


class TtsService:
    def __init__(
        self,
        sessions: SessionRepository,
        settings: TtsSettings,
        runtime: TtsRuntime,
        client: TtsClient,
        *,
        classifier: EmotionClassifier | None = None,
        references: EmotionReferenceLibrary | None = None,
    ) -> None:
        self.sessions = sessions
        self.settings = settings
        self.runtime = runtime
        self.client = client
        self.classifier = classifier
        self.references = references
        self._inference_lock = threading.Lock()

    def status(self) -> dict[str, str]:
        return {
            "status": getattr(self.runtime, "status", "idle"),
            "detail": getattr(self.runtime, "status_detail", ""),
            "emotion": "enabled" if self.settings.emotion_enabled else "disabled",
        }

    def synthesize_message(self, session_id: str, message_id: str) -> bytes:
        text, reference, auxiliary, cache_path = self._prepare_message(session_id, message_id)
        cached = self._read_cache(cache_path)
        if cached is not None:
            return cached

        with self._inference_lock:
            cached = self._read_cache(cache_path)
            if cached is not None:
                return cached
            self.runtime.ensure_ready()
            audio = self.client.synthesize(text, reference, auxiliary)
            self._validate_audio(audio)
            self._write_cache(cache_path, audio)
            return audio

    def stream_message(self, session_id: str, message_id: str) -> Iterator[bytes]:
        text, reference, auxiliary, cache_path = self._prepare_message(session_id, message_id)
        cached = self._read_cache(cache_path)
        if cached is not None:
            return iter((cached,))

        self.runtime.ensure_ready()

        def generate() -> Iterator[bytes]:
            with self._inference_lock:
                existing = self._read_cache(cache_path)
                if existing is not None:
                    yield existing
                    return

                chunks: list[bytes] = []
                total_bytes = 0
                for chunk in self.client.stream_synthesize(text, reference, auxiliary):
                    if not chunk:
                        continue
                    total_bytes += len(chunk)
                    if total_bytes > self.settings.max_audio_bytes:
                        raise TtsTooLargeError("生成的语音文件过大")
                    chunks.append(chunk)
                    yield chunk

                audio = self._finalize_streamed_wav(b"".join(chunks))
                self._validate_audio(audio)
                self._write_cache(cache_path, audio)

        return generate()

    def _prepare_message(
        self,
        session_id: str,
        message_id: str,
    ) -> tuple[str, VoiceReference | None, tuple[Path, ...], Path]:
        if not self.settings.enabled:
            raise TtsDisabledError("语音朗读未启用")
        session = self.sessions.get(session_id)
        message = next((item for item in session.messages if item.id == message_id), None)
        if message is None:
            raise TtsMessageNotFoundError("找不到要朗读的消息")
        if message.role != "assistant":
            raise TtsMessageError("只能朗读助手回复")

        text = speech_text_from_markdown(message.content)
        if not text:
            raise TtsMessageError("这条回复没有可朗读的文本")
        if len(text) > self.settings.max_text_chars:
            raise TtsTooLargeError(f"回复超过语音朗读上限（{self.settings.max_text_chars} 字）")

        reference = self._select_reference(text)
        auxiliary = (
            self.references.auxiliary(reference, self.settings.emotion_aux_reference_count)
            if reference is not None and self.references is not None
            else ()
        )
        cache_path = self._cache_path(text, reference, auxiliary)
        return text, reference, auxiliary, cache_path

    def _select_reference(self, text: str) -> VoiceReference | None:
        if not self.settings.emotion_enabled or self.classifier is None or self.references is None:
            return None
        return self.references.select(self.classifier.classify(text), text)

    def _cache_path(
        self,
        text: str,
        reference: VoiceReference | None = None,
        auxiliary: tuple[Path, ...] = (),
    ) -> Path:
        identity = {
            "voice_profile": "stable-neutral-v2",
            "text": text,
            "gpt": self._file_identity(self.settings.gpt_weights_path),
            "sovits": self._file_identity(self.settings.sovits_weights_path),
            "reference": self._file_identity(self.settings.reference_audio_path),
            "reference_text": self.settings.reference_text,
            "reference_language": self.settings.reference_language,
            "target_language": self.settings.target_language,
        }
        if reference is not None:
            identity["emotion"] = reference.emotion
            identity["emotion_reference"] = self._file_identity(reference.audio_path)
            identity["emotion_prompt_text"] = reference.prompt_text
            identity["emotion_aux_references"] = [
                self._file_identity(path) for path in auxiliary
            ]
            identity["emotion_aux_reference_count"] = self.settings.emotion_aux_reference_count
        digest = hashlib.sha256(
            json.dumps(identity, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return self.settings.cache_directory / f"{digest}.wav"

    @staticmethod
    def _file_identity(path: Path) -> dict[str, str | int | None]:
        try:
            modified_ns: int | None = path.stat().st_mtime_ns
        except OSError:
            modified_ns = None
        return {"path": str(path.resolve()), "modified_ns": modified_ns}

    def _read_cache(self, path: Path) -> bytes | None:
        try:
            audio = path.read_bytes()
        except OSError:
            return None
        try:
            self._validate_audio(audio)
        except (TtsTooLargeError, TtsUpstreamError):
            return None
        return audio

    @staticmethod
    def _finalize_streamed_wav(audio: bytes) -> bytes:
        if len(audio) < 44 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
            return audio
        data_offset = audio.find(b"data", 12, 128)
        if data_offset < 0 or data_offset + 8 > len(audio):
            return audio
        result = bytearray(audio)
        result[4:8] = (len(result) - 8).to_bytes(4, "little")
        result[data_offset + 4:data_offset + 8] = (
            len(result) - data_offset - 8
        ).to_bytes(4, "little")
        return bytes(result)

    @staticmethod
    def _write_cache(path: Path, audio: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=path.parent, suffix=".tmp", delete=False
        ) as handle:
            handle.write(audio)
            temp_path = Path(handle.name)
        os.replace(temp_path, path)

    def _validate_audio(self, audio: bytes) -> None:
        if len(audio) > self.settings.max_audio_bytes:
            raise TtsTooLargeError("生成的语音文件过大")
        if len(audio) < 12 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
            raise TtsUpstreamError("GPT-SoVITS 返回了无效的 WAV 音频")
