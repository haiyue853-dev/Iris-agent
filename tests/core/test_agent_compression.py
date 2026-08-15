from iris_agent.context_compression.compressor import ContextCompressor
from iris_agent.core.agent import AgentLoop, AgentService
from iris_agent.core.models import Message, ProviderResponse
from iris_agent.sessions.json_store import JsonSessionRepository
from iris_agent.tools.registry import ToolRegistry


class CapturingProvider:
    def __init__(self):
        self.calls = []

    def complete(self, messages, tools):
        self.calls.append(list(messages))
        return ProviderResponse(content="done")


class SummaryProvider:
    def __init__(self, content: str):
        self.content = content

    def complete(self, messages, tools):
        return ProviderResponse(content=self.content)


def test_run_compresses_long_session(tmp_path):
    repo = JsonSessionRepository(tmp_path / "sessions")
    session = repo.create("test")
    repo.append(session.id, Message(role="user", content="u" * 30))
    repo.append(session.id, Message(role="assistant", content="a" * 30))
    repo.append(session.id, Message(role="user", content="b" * 30))

    compressor = ContextCompressor(SummaryProvider("摘要内容"), trigger_chars=50, keep_recent=2)
    service = AgentService(AgentLoop(CapturingProvider(), ToolRegistry()), repo, "system", compressor=compressor)

    list(service.run(session.id, "新问题"))

    saved = repo.get(session.id)
    summaries = [m for m in saved.messages if m.content.startswith("[对话摘要]")]
    assert len(summaries) == 1
    assert summaries[0].content == "[对话摘要] 摘要内容"


def test_run_does_not_compress_short_session(tmp_path):
    repo = JsonSessionRepository(tmp_path / "sessions")
    session = repo.create("test")
    repo.append(session.id, Message(role="user", content="hi"))

    compressor = ContextCompressor(SummaryProvider("摘要"), trigger_chars=1000, keep_recent=2)
    service = AgentService(AgentLoop(CapturingProvider(), ToolRegistry()), repo, "system", compressor=compressor)

    list(service.run(session.id, "新问题"))

    saved = repo.get(session.id)
    assert not any(m.content.startswith("[对话摘要]") for m in saved.messages)


def test_run_without_compressor_unchanged(tmp_path):
    repo = JsonSessionRepository(tmp_path / "sessions")
    session = repo.create("test")
    repo.append(session.id, Message(role="user", content="u" * 30))

    service = AgentService(AgentLoop(CapturingProvider(), ToolRegistry()), repo, "system")

    list(service.run(session.id, "新问题"))

    saved = repo.get(session.id)
    assert not any(m.content.startswith("[对话摘要]") for m in saved.messages)


def test_compressed_messages_are_sent_to_model(tmp_path):
    repo = JsonSessionRepository(tmp_path / "sessions")
    session = repo.create("test")
    repo.append(session.id, Message(role="user", content="u" * 30))
    repo.append(session.id, Message(role="assistant", content="a" * 30))
    repo.append(session.id, Message(role="user", content="b" * 30))

    compressor = ContextCompressor(SummaryProvider("摘要内容"), trigger_chars=50, keep_recent=2)
    agent_provider = CapturingProvider()
    service = AgentService(AgentLoop(agent_provider, ToolRegistry()), repo, "system", compressor=compressor)

    list(service.run(session.id, "新问题"))

    sent = agent_provider.calls[0]
    system_contents = [m.content for m in sent if m.role == "system"]
    assert any(c.startswith("[对话摘要]") for c in system_contents)
