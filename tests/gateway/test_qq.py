from iris_agent.gateway.qq import QQOneBotAdapter


class FakeGateway:
    def __init__(self, reply: str = "回复"):
        self.reply = reply
        self.messages = []

    def handle(self, message):
        self.messages.append(message)
        return f"{self.reply}:{message.text}"


def _adapter(respond_groups=False, reply="回复") -> QQOneBotAdapter:
    return QQOneBotAdapter(FakeGateway(reply), respond_groups=respond_groups)


def test_private_message_returns_send_action():
    adapter = _adapter()
    payload = {
        "post_type": "message",
        "message_type": "private",
        "user_id": 12345,
        "raw_message": "你好",
    }

    action = adapter.handle_event(payload)

    assert action["action"] == "send_msg"
    assert action["params"] == {"message_type": "private", "message": "回复:你好", "user_id": 12345}
    assert adapter.gateway.messages[0].user_id == "12345"


def test_group_message_ignored_by_default():
    adapter = _adapter(respond_groups=False)
    payload = {"post_type": "message", "message_type": "group", "group_id": 789, "user_id": 1, "raw_message": "hi"}

    assert adapter.handle_event(payload) is None


def test_group_message_answered_when_enabled():
    adapter = _adapter(respond_groups=True)
    payload = {"post_type": "message", "message_type": "group", "group_id": 789, "user_id": 1, "raw_message": "hi"}

    action = adapter.handle_event(payload)

    assert action["params"]["message_type"] == "group"
    assert action["params"]["group_id"] == 789


def test_non_message_event_returns_none():
    adapter = _adapter()
    assert adapter.handle_event({"post_type": "notice", "notice_type": "friend_add"}) is None


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

    action = adapter.handle_event(payload)

    assert action["params"]["message"] == "回复:第一段第二段"


def test_empty_message_returns_none():
    adapter = _adapter()
    payload = {"post_type": "message", "message_type": "private", "user_id": 1, "message": []}

    assert adapter.handle_event(payload) is None


def test_exception_returns_friendly_reply():
    class BoomGateway:
        def handle(self, message):
            raise RuntimeError("boom")

    adapter = QQOneBotAdapter(BoomGateway())
    payload = {"post_type": "message", "message_type": "private", "user_id": 1, "raw_message": "hi"}

    action = adapter.handle_event(payload)

    assert "出错" in action["params"]["message"]
