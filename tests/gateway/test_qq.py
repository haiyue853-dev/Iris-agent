import asyncio
import threading
import time

from iris_agent.gateway.qq import QQOneBotAdapter
from iris_agent.gateway.service import GatewayReply


class FakeGateway:
    def __init__(self, reply: str = "回复", files=None):
        self.reply = reply
        self.files = files or []
        self.messages = []

    def handle(self, message):
        self.messages.append(message)
        return GatewayReply(text=f"{self.reply}:{message.text}", files=list(self.files))


def _adapter(respond_groups=False, reply="回复", files=None, allowed_users=None, allow_all=False) -> QQOneBotAdapter:
    return QQOneBotAdapter(FakeGateway(reply, files), respond_groups=respond_groups, allowed_users=allowed_users, allow_all=allow_all)


def test_private_message_returns_send_action():
    adapter = _adapter(allow_all=True)
    payload = {"post_type": "message", "message_type": "private", "user_id": 12345, "raw_message": "你好"}

    actions = adapter.handle_event(payload)

    assert len(actions) == 1
    assert actions[0]["action"] == "send_msg"
    assert actions[0]["params"] == {"message_type": "private", "message": "回复:你好", "user_id": 12345}
    assert adapter.gateway.messages[0].user_id == "12345"


def test_group_message_ignored_by_default():
    adapter = _adapter(respond_groups=False)
    payload = {"post_type": "message", "message_type": "group", "group_id": 789, "user_id": 1, "raw_message": "hi"}

    assert adapter.handle_event(payload) == []


def test_group_message_answered_when_enabled():
    adapter = _adapter(respond_groups=True, allow_all=True)
    payload = {"post_type": "message", "message_type": "group", "group_id": 789, "user_id": 1, "raw_message": "hi"}

    actions = adapter.handle_event(payload)

    assert actions[0]["params"]["message_type"] == "group"
    assert actions[0]["params"]["group_id"] == 789


def test_non_message_event_returns_empty():
    adapter = _adapter()
    assert adapter.handle_event({"post_type": "notice", "notice_type": "friend_add"}) == []


def test_text_extracted_from_segments():
    adapter = _adapter(allow_all=True)
    payload = {
        "post_type": "message",
        "message_type": "private",
        "user_id": 1,
        "message": [
            {"type": "text", "data": {"text": "第一段"}},
            {"type": "face", "data": {"id": "1"}},
            {"type": "text", "data": {"text": "第二段"}},
        ],
        "raw_message": "第一段[CQ:face,id=1]第二段",
    }

    actions = adapter.handle_event(payload)

    assert actions[0]["params"]["message"] == "回复:第一段第二段"


def test_empty_message_returns_empty():
    adapter = _adapter()
    payload = {"post_type": "message", "message_type": "private", "user_id": 1, "message": []}

    assert adapter.handle_event(payload) == []


def test_exception_returns_friendly_reply():
    class BoomGateway:
        def handle(self, message):
            raise RuntimeError("boom")

    adapter = QQOneBotAdapter(BoomGateway(), allow_all=True)
    payload = {"post_type": "message", "message_type": "private", "user_id": 1, "raw_message": "hi"}

    actions = adapter.handle_event(payload)

    assert "出错" in actions[0]["params"]["message"]


def test_file_markers_become_file_actions_before_text(tmp_path):
    real_file = tmp_path / "日报.md"
    real_file.write_text("内容", encoding="utf-8")
    adapter = _adapter(files=[str(real_file)], allow_all=True)
    payload = {"post_type": "message", "message_type": "private", "user_id": 12345, "raw_message": "把日报发给我"}

    actions = adapter.handle_event(payload)

    assert len(actions) == 2
    file_action = actions[0]
    assert file_action["action"] == "send_msg"
    assert file_action["params"]["user_id"] == 12345
    assert "CQ:file" in file_action["params"]["message"]
    assert str(real_file).replace("\\", "/") in file_action["params"]["message"]
    assert actions[1]["params"]["message"] == "回复:把日报发给我"


def test_missing_file_adds_notice(tmp_path):
    missing = str(tmp_path / "不存在的文件.md")
    adapter = _adapter(files=[missing], allow_all=True)
    payload = {"post_type": "message", "message_type": "private", "user_id": 12345, "raw_message": "发文件"}

    actions = adapter.handle_event(payload)

    assert len(actions) == 1
    assert "文件不存在" in actions[0]["params"]["message"]
    assert "不存在的文件.md" in actions[0]["params"]["message"]


def test_group_message_does_not_send_files():
    adapter = _adapter(respond_groups=True, files=["D:/a.txt"], allow_all=True)
    payload = {"post_type": "message", "message_type": "group", "group_id": 789, "user_id": 1, "raw_message": "hi"}

    actions = adapter.handle_event(payload)

    assert len(actions) == 1
    assert actions[0]["params"]["message"] == "回复:hi"


def test_push_text_returns_false_without_connection():
    adapter = _adapter()

    assert adapter.push_text("123", "hello") is False


def test_push_text_schedules_send_when_attached():
    adapter = _adapter()
    sent = []

    class FakeWS:
        async def send_json(self, action):
            sent.append(action)

    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    adapter.attach(FakeWS(), loop)
    try:
        assert adapter.push_text("12345", "热点提醒") is True
        deadline = time.time() + 1
        while not sent and time.time() < deadline:
            time.sleep(0.01)
        assert len(sent) == 1
        assert sent[0]["action"] == "send_msg"
        assert sent[0]["params"] == {"message_type": "private", "message": "热点提醒", "user_id": 12345}
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=1)
        loop.close()


def test_detach_clears_connection():
    adapter = _adapter()
    loop = asyncio.new_event_loop()
    ws = object()
    adapter.attach(ws, loop)

    adapter.detach(ws)

    assert adapter.push_text("123", "hello") is False


def test_allowed_users_filters_unknown_users():
    adapter = _adapter(allowed_users=["12345"])
    payload = {"post_type": "message", "message_type": "private", "user_id": 99999, "raw_message": "hi"}

    assert adapter.handle_event(payload) == []


def test_allowed_user_is_answered():
    adapter = _adapter(allowed_users=["12345"])
    payload = {"post_type": "message", "message_type": "private", "user_id": 12345, "raw_message": "hi"}

    actions = adapter.handle_event(payload)

    assert len(actions) == 1
    assert actions[0]["params"]["message"] == "回复:hi"


def test_empty_allowed_users_denies_all():
    adapter = _adapter()
    payload = {"post_type": "message", "message_type": "private", "user_id": 99999, "raw_message": "hi"}

    assert adapter.handle_event(payload) == []


def test_allow_all_flag_allows_everyone():
    adapter = _adapter(allow_all=True)
    payload = {"post_type": "message", "message_type": "private", "user_id": 99999, "raw_message": "hi"}

    assert len(adapter.handle_event(payload)) == 1


def test_allow_all_overrides_allowlist():
    adapter = _adapter(allowed_users=["12345"], allow_all=True)
    payload = {"post_type": "message", "message_type": "private", "user_id": 99999, "raw_message": "hi"}

    assert len(adapter.handle_event(payload)) == 1
