from iris_agent.core.context import ContextEngine, JsonContextSnapshotRepository
from iris_agent.core.models import Message


def test_context_engine_keeps_short_history_unchanged(tmp_path):
    engine = ContextEngine(JsonContextSnapshotRepository(tmp_path), max_chars=1_000)
    history = [Message(role="user", content="hello")]

    messages = engine.build("session_1", "system", history)

    assert [message.content for message in messages] == ["system", "hello"]


def test_context_engine_persists_snapshot_and_keeps_recent_messages(tmp_path):
    snapshots = JsonContextSnapshotRepository(tmp_path)
    engine = ContextEngine(snapshots, max_chars=1_000)
    history = [
        Message(role="user", content="first " * 110),
        Message(role="assistant", content="second " * 110),
        Message(role="user", content="latest " * 110),
    ]

    messages = engine.build("session_1", "system", history)

    assert messages[0].role == "system"
    assert "Conversation summary" in messages[0].content
    assert messages[-1].content == history[-1].content
    assert snapshots.get("session_1", history[-2].id) is not None
