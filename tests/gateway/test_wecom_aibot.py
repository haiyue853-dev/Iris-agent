import io
from pathlib import Path

from iris_agent.gateway.service import GatewayReply
from iris_agent.gateway.wecom_aibot import WeComAIBotBridge


class RecordingGateway:
    def __init__(self, reply: str = "Iris 回复"):
        self.reply = reply
        self.messages = []

    def handle(self, message):
        self.messages.append(message)
        return GatewayReply(self.reply)


def _event(user_id: str = "zhangsan", *, chat_type: str = "single") -> dict:
    return {
        "type": "message",
        "event_id": "evt-1",
        "user_id": user_id,
        "chat_id": user_id if chat_type == "single" else "group-1",
        "chat_type": chat_type,
        "message_id": "msg-1",
        "text": "帮我记下这件事",
    }


def test_first_private_user_is_bound_as_owner_and_message_reaches_gateway(tmp_path):
    gateway = RecordingGateway()
    bridge = WeComAIBotBridge(
        gateway,
        bot_id="bot-id",
        secret="bot-secret",
        script_path=tmp_path / "bridge.mjs",
        owner_file=tmp_path / "owner.json",
    )

    command = bridge.handle_message_event(_event())

    assert command == {"type": "reply", "event_id": "evt-1", "text": "Iris 回复"}
    assert gateway.messages[0].platform == "wecom"
    assert gateway.messages[0].user_id == "zhangsan"
    assert gateway.messages[0].raw["message_id"] == "msg-1"
    assert bridge.owner_user_id == "zhangsan"


def test_second_user_is_rejected_after_private_owner_is_bound(tmp_path):
    gateway = RecordingGateway()
    owner_file = tmp_path / "owner.json"
    bridge = WeComAIBotBridge(
        gateway,
        bot_id="bot-id",
        secret="bot-secret",
        script_path=tmp_path / "bridge.mjs",
        owner_file=owner_file,
    )
    bridge.handle_message_event(_event("owner"))

    command = bridge.handle_message_event(_event("stranger"))

    assert "未授权" in command["text"]
    assert [message.user_id for message in gateway.messages] == ["owner"]


def test_group_messages_are_not_forwarded_by_default(tmp_path):
    gateway = RecordingGateway()
    bridge = WeComAIBotBridge(
        gateway,
        bot_id="bot-id",
        secret="bot-secret",
        script_path=tmp_path / "bridge.mjs",
        owner_file=tmp_path / "owner.json",
    )

    command = bridge.handle_message_event(_event(chat_type="group"))

    assert "仅开放私聊" in command["text"]
    assert gateway.messages == []


class FakeProcess:
    def __init__(self):
        self.stdin = io.StringIO()
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()
        self.returncode = None

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.returncode = 0
        return 0

    def terminate(self):
        self.returncode = 0


def test_start_passes_credentials_only_through_child_environment(tmp_path):
    script = tmp_path / "bridge.mjs"
    script.write_text("// test", encoding="utf-8")
    captured = {}

    def process_factory(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return FakeProcess()

    bridge = WeComAIBotBridge(
        RecordingGateway(),
        bot_id="bot-id",
        secret="super-secret",
        script_path=script,
        owner_file=tmp_path / "owner.json",
        node_executable="node",
        process_factory=process_factory,
    )

    assert bridge.start() is True
    assert captured["args"] == ["node", str(script)]
    assert "super-secret" not in " ".join(captured["args"])
    assert captured["kwargs"]["env"]["IRIS_WECOM_BOT_ID"] == "bot-id"
    assert captured["kwargs"]["env"]["IRIS_WECOM_BOT_SECRET"] == "super-secret"


def test_start_resolves_relative_script_before_using_its_directory_as_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    script = Path("integrations/wecom-aibot/bridge.mjs")
    script.parent.mkdir(parents=True)
    script.write_text("// test", encoding="utf-8")
    captured = {}

    def process_factory(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return FakeProcess()

    bridge = WeComAIBotBridge(
        RecordingGateway(),
        bot_id="bot-id",
        secret="bot-secret",
        script_path=script,
        owner_file=tmp_path / "owner.json",
        process_factory=process_factory,
    )

    assert bridge.start() is True
    assert captured["args"][1] == str(script.resolve())
    assert captured["kwargs"]["cwd"] == str(script.resolve().parent)


def test_secret_is_hidden_from_repr(tmp_path):
    bridge = WeComAIBotBridge(
        RecordingGateway(),
        bot_id="bot-id",
        secret="super-secret",
        script_path=Path("bridge.mjs"),
        owner_file=tmp_path / "owner.json",
    )

    assert "super-secret" not in repr(bridge)
