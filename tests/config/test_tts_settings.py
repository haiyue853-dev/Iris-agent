from pathlib import Path

from iris_agent.config.settings import load_settings


def test_loads_gpt_sovits_settings(tmp_path: Path) -> None:
    config = tmp_path / "agent.yaml"
    config.write_text(
        """tts:
  enabled: true
  base_url: http://127.0.0.1:9880
  root_directory: D:/AI/GPT-SoVITS
  gpt_weights_path: D:/AI/gsd/tomori.ckpt
  sovits_weights_path: D:/AI/gsd/tomori.pth
  reference_audio_path: D:/AI/tomori/高松燈、です。よろしく…….mp3
  reference_text: 高松燈、です。よろしく……
  reference_language: ja
  target_language: zh
  cache_directory: data/tts
  startup_timeout_seconds: 90
  request_timeout_seconds: 300
  max_text_chars: 4000
  max_audio_bytes: 200000000
  warmup_on_startup: true
  emotion_enabled: true
  emotion_audio_directory: D:/AI/tomori
  emotion_index_file: data/tts/emotion_references.json
  emotion_aux_reference_count: 2
""",
        encoding="utf-8",
    )

    tts = load_settings(config).tts

    assert tts.enabled is True
    assert tts.root_directory == Path("D:/AI/GPT-SoVITS")
    assert tts.reference_text == "高松燈、です。よろしく……"
    assert tts.reference_language == "ja"
    assert tts.target_language == "zh"
    assert tts.max_text_chars == 4000
    assert tts.warmup_on_startup is True
    assert tts.emotion_enabled is True
    assert tts.emotion_audio_directory == Path("D:/AI/tomori")
    assert tts.emotion_index_file == Path("data/tts/emotion_references.json")
    assert tts.emotion_aux_reference_count == 2
