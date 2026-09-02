from iris_agent.core.agent import AgentLoop, AgentService
from iris_agent.sessions.json_store import JsonSessionRepository
from iris_agent.tools.registry import ToolRegistry


class FakeOrchestrator:
    def __init__(self):
        self.calls = []

    def context_for(self, query, session_id, collection_id, mode):
        self.calls.append((query, session_id, collection_id, mode))
        return "[统一知识检索结果]\n[1] 命中", [{"index": 1, "source_type": "memory"}]


def test_turn_prompt_uses_unified_knowledge_orchestrator(tmp_path):
    orchestrator = FakeOrchestrator()
    service = AgentService(
        AgentLoop(object(), ToolRegistry()),
        JsonSessionRepository(tmp_path),
        "system",
        knowledge_orchestrator=orchestrator,
    )
    citations = []

    prompt = service._turn_prompt(
        "session-1",
        "这个怎么实现？",
        [],
        "fast",
        "collection-1",
        "mix",
        True,
        citations,
    )

    assert orchestrator.calls == [("这个怎么实现？", "session-1", "collection-1", "mix")]
    assert "[统一知识检索结果]" in prompt
    assert citations == [{"index": 1, "source_type": "memory"}]
