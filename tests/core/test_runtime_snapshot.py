from iris_agent.core.models import Message
from iris_agent.core.runtime import SessionRuntimeSnapshot


def test_runtime_snapshot_hash_is_stable_after_round_trip():
    snapshot = SessionRuntimeSnapshot.create(
        epoch=1,
        model="deepseek-chat",
        system_messages=("system", "profile", "memory"),
        tool_schemas=({"type": "function", "function": {"name": "recall"}},),
    )

    restored = SessionRuntimeSnapshot.from_dict(snapshot.to_dict())

    assert restored.prefix_hash == snapshot.prefix_hash
    assert restored.tool_schema_hash == snapshot.tool_schema_hash


def test_message_uses_persisted_prompt_content_for_model_input():
    message = Message(role="user", content="显示文本", prompt_content="固定模型文本", runtime_epoch=2)

    assert message.model_content == "固定模型文本"


def test_message_falls_back_to_display_content_for_legacy_records():
    message = Message(role="user", content="旧消息")

    assert message.model_content == "旧消息"

