from iris_agent.api.schemas import ChatRequest


def test_chat_request_accepts_named_toolsets():
    request = ChatRequest(session_id="session_1", message="hello", toolsets=["safe", "research"])

    assert request.toolsets == ["safe", "research"]


def test_chat_request_rejects_unknown_toolset():
    try:
        ChatRequest(session_id="session_1", message="hello", toolsets=["unknown"])
    except Exception:
        pass
    else:
        raise AssertionError("unknown toolset must be rejected")
