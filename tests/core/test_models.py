import pytest

from iris_agent.core.models import AgentEvent, Message


def test_event_serializes_to_wire_shape():
    event = AgentEvent(type="text_delta", data={"content": "你"})
    assert event.to_dict() == {"type": "text_delta", "data": {"content": "你"}}


def test_message_rejects_unknown_role():
    with pytest.raises(ValueError):
        Message(role="unknown", content="x")
