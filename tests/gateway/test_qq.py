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


def _adapter(respond_groups=False, reply="回复", files=None) -> QQOneBotAdapter:
    return QQOneBotAdapter(FakeGateway(reply, files), respond_groups=respond_groups)


def test_private_message_returns_send_action():
    adapter = _adapter()
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
    adapter = _adapter(respond_groups=True)
    payload = {"post_type": "message", "message_type": "group", "group_id": 789, "user_id": 1, "raw_message": "hi"}

    actions = adapter.handle_event(payload)

    assert actions[0]["params"]["message_type"] == "group"
    assert actions[0]["params"]["group_id"] == 789


def test_non_message_event_returns_empty():
    adapter = _adapter()
    assert adapter.handle_event({"post_type": "notice", "notice_type": "friend_add"}) == []


def test_text_extracted_from_segments():
    adapter = _adapter()
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

    adapter = QQOneBotAdapter(BoomGateway())
    payload = {"post_type": "message", "message_type": "private", "user_id": 1, "raw_message": "hi"}

    actions = adapter.handle_event(payload)

    assert "出错" in actions[0]["params"]["message"]


def test_file_markers_become_file_actions_before_text():
    adapter = _adapter(files=["D:/agent/iris-agent/日报.md"])
    payload = {"post_type": "message", "message_type": "private", "user_id": 12345, "raw_message": "把日报发给我"}

    actions = adapter.handle_event(payload)

    assert len(actions) == 2
    file_action = actions[0]
    assert file_action["action"] == "send_msg"
    assert file_action["params"]["user_id"] == 12345
    assert "CQ:file" in file_action["params"]["message"]
    assert "D:/agent/iris-agent/日报.md" in file_action["params"]["message"]
    assert actions[1]["params"]["message"] == "回复:把日报发给我"


def test_group_message_does_not_send_files():
    adapter = _adapter(respond_groups=True, files=["D:/a.txt"])
    payload = {"post_type": "message", "message_type": "group", "group_id": 789, "user_id": 1, "raw_message": "hi"}

    actions = adapter.handle_event(payload)

    assert len(actions) == 1
    assert actions[0]["params"]["message"] == "回复:hi"
