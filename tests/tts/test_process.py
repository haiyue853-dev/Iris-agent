from pathlib import Path
import threading

from iris_agent.config.settings import TtsSettings
from iris_agent.tts.process import GptSovitsProcessManager


class FakeClient:
    def __init__(self) -> None:
        self.health_checks = 0
        self.weight_calls = 0

    def is_healthy(self) -> bool:
        self.health_checks += 1
        return self.health_checks >= 2

    def set_weights(self) -> None:
        self.weight_calls += 1


class FakeProcess:
    def poll(self):
        return None

    def terminate(self) -> None:
        pass

    def wait(self, timeout: float) -> None:
        pass


def test_first_use_starts_bundled_api_and_loads_weights(tmp_path: Path) -> None:
    root = tmp_path / "GPT-SoVITS"
    (root / "runtime").mkdir(parents=True)
    (root / "GPT_SoVITS" / "configs").mkdir(parents=True)
    for path in (
        root / "runtime" / "python.exe",
        root / "api_v2.py",
        root / "GPT_SoVITS" / "configs" / "tts_infer.yaml",
    ):
        path.write_bytes(b"")
    gpt = tmp_path / "tomori.ckpt"
    sovits = tmp_path / "tomori.pth"
    reference = tmp_path / "ref.mp3"
    for path in (gpt, sovits, reference):
        path.write_bytes(b"model")
    settings = TtsSettings(
        enabled=True,
        root_directory=root,
        gpt_weights_path=gpt,
        sovits_weights_path=sovits,
        reference_audio_path=reference,
        reference_text="高松燈、です。よろしく……",
        startup_timeout_seconds=5,
    )
    client = FakeClient()
    starts: list[tuple[list[str], dict]] = []

    def start(command, **kwargs):
        starts.append((command, kwargs))
        return FakeProcess()

    manager = GptSovitsProcessManager(
        settings, client, start_process=start, sleep=lambda _: None
    )

    manager.ensure_ready()
    manager.ensure_ready()

    command, options = starts[0]
    assert len(starts) == 1
    assert command[:3] == [str(root / "runtime" / "python.exe"), "-I", "api_v2.py"]
    assert command[command.index("-p") + 1] == "9880"
    assert options["cwd"] == str(root)
    assert client.weight_calls == 1


def test_background_warmup_reports_starting_then_ready(tmp_path: Path) -> None:
    settings = TtsSettings(enabled=True, root_directory=tmp_path)
    client = FakeClient()
    entered = threading.Event()
    release = threading.Event()
    manager = GptSovitsProcessManager(settings, client)

    def delayed_ready() -> None:
        entered.set()
        release.wait(timeout=2)

    manager.ensure_ready = delayed_ready  # type: ignore[method-assign]

    thread = manager.start_warmup()
    assert entered.wait(timeout=1)
    assert manager.status == "starting"
    release.set()
    thread.join(timeout=1)
    assert manager.status == "ready"


def test_background_warmup_reports_failure_without_raising(tmp_path: Path) -> None:
    manager = GptSovitsProcessManager(TtsSettings(enabled=True, root_directory=tmp_path), FakeClient())

    def fail() -> None:
        raise RuntimeError("boom")

    manager.ensure_ready = fail  # type: ignore[method-assign]

    manager.start_warmup().join(timeout=1)

    assert manager.status == "failed"
    assert manager.status_detail == "boom"


def test_ready_manager_restarts_when_service_dies(tmp_path: Path) -> None:
    root = tmp_path / "GPT-SoVITS"
    (root / "runtime").mkdir(parents=True)
    (root / "GPT_SoVITS" / "configs").mkdir(parents=True)
    for path in (
        root / "runtime" / "python.exe",
        root / "api_v2.py",
        root / "GPT_SoVITS" / "configs" / "tts_infer.yaml",
    ):
        path.write_bytes(b"")
    gpt, sovits, reference = tmp_path / "voice.ckpt", tmp_path / "voice.pth", tmp_path / "ref.mp3"
    for path in (gpt, sovits, reference):
        path.write_bytes(b"model")
    settings = TtsSettings(
        enabled=True, root_directory=root, gpt_weights_path=gpt,
        sovits_weights_path=sovits, reference_audio_path=reference,
    )

    class RecoveringClient:
        def __init__(self) -> None:
            self.health = iter((True, False, False, True))
            self.weight_calls = 0

        def is_healthy(self) -> bool:
            return next(self.health)

        def set_weights(self) -> None:
            self.weight_calls += 1

    starts = []
    client = RecoveringClient()
    manager = GptSovitsProcessManager(
        settings, client, start_process=lambda *args, **kwargs: starts.append(args) or FakeProcess(),
        sleep=lambda _: None,
    )

    manager.ensure_ready()
    manager.ensure_ready()

    assert len(starts) == 1
    assert client.weight_calls == 2
