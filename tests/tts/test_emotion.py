import json
from pathlib import Path

from iris_agent.tts.emotion import (
    EmotionClassifier,
    EmotionReferenceLibrary,
    FfprobeDurationProbe,
    VoiceReference,
)


def test_classifier_recognizes_four_reply_emotions() -> None:
    classifier = EmotionClassifier()

    assert classifier.classify("下面是问题的处理步骤。") == "neutral"
    assert classifier.classify("太好了，恭喜你成功啦！") == "happy"
    assert classifier.classify("真的很抱歉，听到这件事很难过。") == "sad"
    assert classifier.classify("诶？怎么办，我有点担心……") == "tense"


def test_library_builds_from_filename_transcripts_and_selects_stably(tmp_path: Path) -> None:
    audio_dir = tmp_path / "tomori"
    audio_dir.mkdir()
    for name in (
        "高松燈、です。よろしく…….mp3",
        "やった！嬉しい！.mp3",
        "ごめんね……悲しい。.mp3",
        "えっと、どうしよう！？.mp3",
    ):
        (audio_dir / name).write_bytes(b"a" * 30_000)
    index_file = tmp_path / "emotion_references.json"
    fallback = VoiceReference(
        audio_dir / "高松燈、です。よろしく…….mp3",
        "高松燈、です。よろしく……",
        "neutral",
    )
    library = EmotionReferenceLibrary(audio_dir, index_file, fallback)

    library.rebuild()

    payload = json.loads(index_file.read_text(encoding="utf-8"))
    assert {item["emotion"] for item in payload["references"]} == {
        "neutral", "happy", "sad", "tense"
    }
    first = library.select("happy", "祝贺消息")
    second = library.select("happy", "祝贺消息")
    assert first == second
    assert first.emotion == "happy"
    assert first.prompt_text == "やった！嬉しい！"


def test_library_preserves_manual_classification_when_rebuilding(tmp_path: Path) -> None:
    audio_dir = tmp_path / "tomori"
    audio_dir.mkdir()
    audio = audio_dir / "ありがとう！.mp3"
    audio.write_bytes(b"a" * 30_000)
    index_file = tmp_path / "emotion_references.json"
    index_file.write_text(
        json.dumps({
            "references": [{
                "audio_path": str(audio),
                "prompt_text": "ありがとう！",
                "emotion": "sad",
                "manual": True,
            }]
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    fallback = VoiceReference(audio, "ありがとう！", "neutral")
    library = EmotionReferenceLibrary(audio_dir, index_file, fallback)

    library.rebuild()

    assert library.select("sad", "难过").audio_path == audio
    saved = json.loads(index_file.read_text(encoding="utf-8"))["references"][0]
    assert saved["emotion"] == "sad"
    assert saved["manual"] is True


def test_library_falls_back_to_fixed_reference_for_missing_emotion(tmp_path: Path) -> None:
    audio_dir = tmp_path / "tomori"
    audio_dir.mkdir()
    fallback = VoiceReference(tmp_path / "fallback.mp3", "默认台词", "neutral")
    library = EmotionReferenceLibrary(audio_dir, tmp_path / "index.json", fallback)

    assert library.select("happy", "开心") == fallback


def test_library_always_uses_fixed_reference_for_neutral_replies(tmp_path: Path) -> None:
    audio_dir = tmp_path / "tomori"
    audio_dir.mkdir()
    fallback_audio = audio_dir / "固定参考.wav"
    fallback_audio.write_bytes(b"RIFF" + b"a" * 40_000)
    for index in range(6):
        (audio_dir / f"普通台词{index}.wav").write_bytes(b"RIFF" + b"a" * 40_000)
    fallback = VoiceReference(fallback_audio, "固定参考", "neutral")
    library = EmotionReferenceLibrary(
        audio_dir,
        tmp_path / "index.json",
        fallback,
        duration_probe=lambda path: 5.0,
    )
    library.rebuild()

    for text in ("你好", "下面是处理结果", "我已经检查完成", "请继续"):
        assert library.select("neutral", text).audio_path == fallback_audio


def test_library_excludes_clips_outside_reference_length_range(tmp_path: Path) -> None:
    audio_dir = tmp_path / "tomori"
    audio_dir.mkdir()
    (audio_dir / "短い！.mp3").write_bytes(b"a" * 10_000)
    (audio_dir / "ちょうどいい、嬉しい！.mp3").write_bytes(b"a" * 40_000)
    (audio_dir / "長すぎる。.mp3").write_bytes(b"a" * 120_000)
    fallback = VoiceReference(tmp_path / "fallback.mp3", "默认台词", "neutral")
    library = EmotionReferenceLibrary(audio_dir, tmp_path / "index.json", fallback)

    assert library.rebuild() == 1


def test_library_uses_probed_duration_instead_of_file_size(tmp_path: Path) -> None:
    audio_dir = tmp_path / "tomori"
    audio_dir.mkdir()
    durations = {"short.mp3": 1.0, "valid.mp3": 5.0, "long.mp3": 12.0}
    for name in durations:
        (audio_dir / name).write_bytes(b"a" * 40_000)
    fallback = VoiceReference(tmp_path / "fallback.mp3", "默认台词", "neutral")
    library = EmotionReferenceLibrary(
        audio_dir,
        tmp_path / "index.json",
        fallback,
        duration_probe=lambda path: durations[path.name],
    )

    assert library.rebuild() == 1


def test_library_indexes_lossless_wav_references(tmp_path: Path) -> None:
    audio_dir = tmp_path / "tomori"
    audio_dir.mkdir()
    wav = audio_dir / "やった！嬉しい！.wav"
    wav.write_bytes(b"RIFF" + b"a" * 40_000)
    fallback = VoiceReference(tmp_path / "fallback.wav", "默认台词", "neutral")
    library = EmotionReferenceLibrary(
        audio_dir,
        tmp_path / "index.json",
        fallback,
        duration_probe=lambda path: 5.0,
    )

    assert library.rebuild() == 1
    assert library.select("happy", "开心").audio_path == wav


def test_ffprobe_duration_probe_rejects_decode_failures(tmp_path: Path) -> None:
    calls = []

    class Result:
        returncode = 0
        stdout = "5.328000\n"

    probe = FfprobeDurationProbe(
        tmp_path / "ffprobe.exe",
        run=lambda command, **options: calls.append((command, options)) or Result(),
    )

    assert probe(tmp_path / "voice.mp3") == 5.328
    assert "-show_entries" in calls[0][0]

    class Failed:
        returncode = 1
        stdout = ""

    failed = FfprobeDurationProbe(tmp_path / "ffprobe.exe", run=lambda *args, **kwargs: Failed())
    assert failed(tmp_path / "broken.mp3") is None


def test_library_rebuilds_only_when_index_or_audio_changes(tmp_path: Path) -> None:
    audio_dir = tmp_path / "tomori"
    audio_dir.mkdir()
    audio = audio_dir / "voice.mp3"
    audio.write_bytes(b"a" * 30_000)
    index_file = tmp_path / "index.json"
    library = EmotionReferenceLibrary(
        audio_dir, index_file,
        VoiceReference(tmp_path / "fallback.mp3", "默认", "neutral"),
    )

    assert library.needs_rebuild() is True
    library.rebuild()
    assert library.needs_rebuild() is False

    audio.write_bytes(b"b" * 31_000)
    assert library.needs_rebuild() is True
