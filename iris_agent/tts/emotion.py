from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
from typing import Callable, Literal


Emotion = Literal["neutral", "happy", "sad", "tense"]


@dataclass(frozen=True, slots=True)
class VoiceReference:
    audio_path: Path
    prompt_text: str
    emotion: Emotion = "neutral"
    manual: bool = False


class FfprobeDurationProbe:
    def __init__(self, executable: Path, *, run: Callable = subprocess.run) -> None:
        self.executable = executable
        self._run = run

    def __call__(self, audio_path: Path) -> float | None:
        try:
            result = self._run(
                [
                    str(self.executable), "-v", "error", "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1", "-i", str(audio_path),
                ],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode != 0:
                return None
            return float(result.stdout.strip())
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return None


class EmotionClassifier:
    _happy = (
        "太好了", "恭喜", "成功", "开心", "高兴", "喜欢", "谢谢", "感谢",
        "嬉しい", "楽しい", "ありがとう", "やった", "よかった", "好き",
    )
    _sad = (
        "抱歉", "对不起", "遗憾", "难过", "伤心", "失去", "可惜", "悲伤",
        "ごめん", "悲しい", "つらい", "寂しい", "泣", "失く", "できない",
    )
    _tense = (
        "怎么办", "担心", "害怕", "紧张", "没关系吗", "诶", "欸",
        "えっと", "あの", "どうしよう", "怖い", "大丈夫", "まって",
    )

    def classify(self, text: str) -> Emotion:
        scores: dict[Emotion, int] = {
            "neutral": 0,
            "happy": self._score(text, self._happy),
            "sad": self._score(text, self._sad),
            "tense": self._score(text, self._tense),
        }
        scores["happy"] += min(text.count("！") + text.count("!"), 2)
        scores["tense"] += min(text.count("？") + text.count("?"), 2)
        if "！？" in text or "?!" in text or "!?" in text:
            scores["tense"] += 2
        winner = max(("happy", "sad", "tense"), key=lambda item: scores[item])
        return winner if scores[winner] > 0 else "neutral"

    @staticmethod
    def _score(text: str, words: tuple[str, ...]) -> int:
        return sum(2 for word in words if word in text)


class EmotionReferenceLibrary:
    _INDEX_VERSION = 2
    _REFERENCE_SUFFIXES = {".mp3", ".wav"}
    _MIN_REFERENCE_BYTES = 26_000
    _MAX_REFERENCE_BYTES = 90_000

    def __init__(
        self,
        audio_directory: Path,
        index_file: Path,
        fallback: VoiceReference,
        classifier: EmotionClassifier | None = None,
        *,
        duration_probe: Callable[[Path], float | None] | None = None,
    ) -> None:
        self.audio_directory = audio_directory
        self.index_file = index_file
        self.fallback = fallback
        self.classifier = classifier or EmotionClassifier()
        self.duration_probe = duration_probe
        self._lock = threading.RLock()
        self._references: list[VoiceReference] = []
        self._loaded_fingerprint = ""
        self._load()

    def needs_rebuild(self) -> bool:
        return self._loaded_fingerprint != self._source_fingerprint()

    def rebuild(self) -> int:
        with self._lock:
            manual = {
                str(item.audio_path.resolve()): item
                for item in self._references
                if item.manual
            }
            references: list[VoiceReference] = []
            if self.audio_directory.is_dir():
                for audio_path in self._audio_paths():
                    prompt_text = audio_path.stem.strip()
                    if not prompt_text or not self._has_reference_length(audio_path):
                        continue
                    existing = manual.get(str(audio_path.resolve()))
                    references.append(existing or VoiceReference(
                        audio_path=audio_path,
                        prompt_text=prompt_text,
                        emotion=self.classifier.classify(prompt_text),
                    ))
            self._references = references
            self._loaded_fingerprint = self._source_fingerprint()
            self._save()
            return len(references)

    def _has_reference_length(self, audio_path: Path) -> bool:
        if self.duration_probe is not None:
            duration = self.duration_probe(audio_path)
            return duration is not None and 3.0 <= duration <= 10.0
        try:
            size = audio_path.stat().st_size
        except OSError:
            return False
        return self._MIN_REFERENCE_BYTES <= size <= self._MAX_REFERENCE_BYTES

    def select(self, emotion: Emotion, text: str) -> VoiceReference:
        if emotion == "neutral":
            return self.fallback
        with self._lock:
            candidates = [item for item in self._references if item.emotion == emotion]
            if not candidates:
                return self.fallback
            candidates.sort(key=lambda item: (not item.manual, str(item.audio_path)))
            digest = hashlib.sha256(f"{emotion}\0{text}".encode("utf-8")).digest()
            return candidates[int.from_bytes(digest[:8], "big") % len(candidates)]

    def auxiliary(self, primary: VoiceReference, count: int) -> tuple[Path, ...]:
        if count <= 0:
            return ()
        with self._lock:
            candidates = [
                item.audio_path
                for item in self._references
                if item.emotion == primary.emotion and item.audio_path != primary.audio_path
            ]
        return tuple(candidates[:count])

    def _load(self) -> None:
        try:
            payload = json.loads(self.index_file.read_text(encoding="utf-8"))
            if payload.get("version") == self._INDEX_VERSION:
                self._loaded_fingerprint = str(payload.get("source_fingerprint", ""))
            values = payload.get("references", [])
            self._references = [
                VoiceReference(
                    audio_path=Path(item["audio_path"]),
                    prompt_text=str(item["prompt_text"]),
                    emotion=item["emotion"],
                    manual=bool(item.get("manual", False)),
                )
                for item in values
                if item.get("emotion") in {"neutral", "happy", "sad", "tense"}
            ]
        except (OSError, ValueError, TypeError, KeyError):
            self._references = []

    def _save(self) -> None:
        self.index_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": self._INDEX_VERSION,
            "source_fingerprint": self._loaded_fingerprint,
            "references": [
                {**asdict(item), "audio_path": str(item.audio_path)}
                for item in self._references
            ]
        }
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self.index_file.parent,
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            temp_path = Path(handle.name)
        os.replace(temp_path, self.index_file)

    def _source_fingerprint(self) -> str:
        entries = []
        if self.audio_directory.is_dir():
            for path in self._audio_paths():
                try:
                    stat = path.stat()
                except OSError:
                    continue
                entries.append((path.name, stat.st_size, stat.st_mtime_ns))
        return hashlib.sha256(
            json.dumps(entries, ensure_ascii=False).encode("utf-8")
        ).hexdigest()

    def _audio_paths(self) -> list[Path]:
        return sorted(
            path
            for path in self.audio_directory.iterdir()
            if path.is_file() and path.suffix.lower() in self._REFERENCE_SUFFIXES
        )
