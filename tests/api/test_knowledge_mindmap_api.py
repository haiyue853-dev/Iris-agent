from fastapi.testclient import TestClient

from iris_agent.api.app import create_app
from iris_agent.core.agent import AgentLoop, AgentService
from iris_agent.core.models import ProviderResponse
from iris_agent.sessions.json_store import JsonSessionRepository
from iris_agent.tools.registry import ToolRegistry


class Provider:
    def complete(self, messages, tools):
        return ProviderResponse(content="done")


class MindMapKnowledge:
    def document_mindmap(self, document_id):
        if document_id == "doc-missing":
            raise ValueError("知识资料不存在")
        return {"document_id": document_id, "nodes": [{"id": "root", "parent_id": None, "label": "资料", "summary": "总结", "kind": "root", "ordinal": 0, "evidence_chunk_ids": []}]}


def test_get_document_mindmap_api(tmp_path):
    sessions = JsonSessionRepository(tmp_path / "sessions")
    agent = AgentService(AgentLoop(Provider(), ToolRegistry()), sessions, "system")
    client = TestClient(create_app(agent, sessions, knowledge=MindMapKnowledge()))

    response = client.get("/api/knowledge/doc-1/mindmap")

    assert response.status_code == 200
    assert response.json()["nodes"][0]["kind"] == "root"
