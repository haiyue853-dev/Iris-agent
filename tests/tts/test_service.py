from pathlib import Path

import pytest

from iris_agent.config.settings import TtsSettings
from iris_agent.core.models import Message
from iris_agent.sessions.base import Session
from iris_agent.tts.errors import TtsMessageError
from iris_agent.tts.emotion import EmotionClassifier, VoiceReference
from iris_agent.tts.service import TtsService


WAV = b"RIFF" + (b"\x00" * 4) + b"WAVEfmt " + (b"\x00" * 40)


class FakeSessions:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, session_id: str) -> Session:
        assert session_id == self.session.id
        return self.session


class FakeRuntime:
    def __init__(self) -> None:
        self.calls = 0

    def ensure_ready(self) -> None:
        self.calls += 1


class FakeClient:
    def __init__(self) -> None:
        self.texts: list[str] = []

    def synthesize(self, text: str) -> bytes:
        self.texts.append(text)
        return WAV


class EmotionalClient:
    def __init__(self) -> None:
        self.calls = []

    def synthesize(self, text: str, reference, auxiliary) -> bytes:
        self.calls.append((text, reference, auxiliary))
        return WAV


class FakeReferences:
    def __init__(self, reference: VoiceReference, auxiliary=None) -> None:
        self.reference = reference
        self.auxiliary_paths = auxiliary or (Path("D:/AI/tomori/happy-2.mp3"),)

    def select(self, emotion: str, text: str) -> VoiceReference:
        assert emotion == "happy"
        return self.reference

    def auxiliary(self, primary: VoiceReference, count: int):
        assert primary == self.reference
        assert count >= 0
        return self.auxiliary_paths


def settings(cache: Path) -> TtsSettings:
    return TtsSettings(
        enabled=True,
        root_directory=Path("D:/AI/GPT-SoVITS"),
        gpt_weights_path=Path("D:/AI/gsd/tomori.ckpt"),
        sovits_weights_path=Path("D:/AI/gsd/tomori.pth"),
        reference_audio_path=Path("D:/AI/tomori/ref.mp3"),
        reference_text="高松燈、です。よろしく……",
        cache_directory=cache,
    )


def test_synthesizes_assistant_message_once_and_reuses_cached_wav(tmp_path: Path) -> None:
    message = Message(role="assistant", content="**你好**，[点这里](https://example.com)。")
    session = Session("session_test", "test", 0, 0, [message])
    runtime = FakeRuntime()
    client = FakeClient()
    service = TtsService(FakeSessions(session), settings(tmp_path), runtime, client)

    first = service.synthesize_message(session.id, message.id)
    second = service.synthesize_message(session.id, message.id)

    assert first == WAV
    assert second == WAV
    assert client.texts == ["你好，点这里。"]
    assert runtime.calls == 1
    assert len(list(tmp_path.glob("*.wav"))) == 1


def test_rejects_non_assistant_messages(tmp_path: Path) -> None:
    message = Message(role="user", content="你好")
    session = Session("session_test", "test", 0, 0, [message])
    service = TtsService(FakeSessions(session), settings(tmp_path), FakeRuntime(), FakeClient())

    with pytest.raises(TtsMessageError, match="只能朗读助手回复"):
        service.synthesize_message(session.id, message.id)


def test_selects_emotional_reference_for_reply(tmp_path: Path) -> None:
    message = Message(role="assistant", content="太好了，恭喜你成功啦！")
    session = Session("session_test", "test", 0, 0, [message])
    selected = VoiceReference(Path("D:/AI/tomori/happy.mp3"), "嬉しい！", "happy")
    client = EmotionalClient()
    configured = settings(tmp_path)
    configured.emotion_enabled = True
    configured.emotion_aux_reference_count = 2
    service = TtsService(
        FakeSessions(session), configured, FakeRuntime(), client,
        classifier=EmotionClassifier(), references=FakeReferences(selected),
    )

    assert service.synthesize_message(session.id, message.id) == WAV
    assert client.calls == [(
        "太好了，恭喜你成功啦！",
        selected,
        (Path("D:/AI/tomori/happy-2.mp3"),),
    )]


def test_cache_changes_when_auxiliary_reference_changes(tmp_path: Path) -> None:
    message = Message(role="assistant", content="太好了，恭喜你成功啦！")
    session = Session("session_test", "test", 0, 0, [message])
    selected = VoiceReference(Path("D:/AI/tomori/happy.mp3"), "嬉しい！", "happy")
    configured = settings(tmp_path)
    configured.emotion_enabled = True
    configured.emotion_aux_reference_count = 1

    first_client = EmotionalClient()
    TtsService(
        FakeSessions(session), configured, FakeRuntime(), first_client,
        classifier=EmotionClassifier(),
        references=FakeReferences(selected, (Path("D:/AI/tomori/a.mp3"),)),
    ).synthesize_message(session.id, message.id)
    second_client = EmotionalClient()
    TtsService(
        FakeSessions(session), configured, FakeRuntime(), second_client,
        classifier=EmotionClassifier(),
        references=FakeReferences(selected, (Path("D:/AI/tomori/b.mp3"),)),
    ).synthesize_message(session.id, message.id)

    assert len(first_client.calls) == 1
    assert len(second_client.calls) == 1
