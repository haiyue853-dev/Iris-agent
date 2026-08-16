"""Curator API 测试：run/列表/详情/apply/dismiss。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from iris_agent.api.app import create_app
from iris_agent.core.agent import AgentLoop, AgentService
from iris_agent.core.models import ProviderResponse
from iris_agent.curator.repository import CuratorRepository
from iris_agent.curator.service import CuratorService
from iris_agent.curator.similarity import SimilarityEngine
from iris_agent.memory.repository import MemoryRepository
from iris_agent.memory.service import MemoryService
from iris_agent.profile.repository import ProfileRepository
from iris_agent.profile.service import ProfileService
from iris_agent.sessions.json_store import JsonSessionRepository
from iris_agent.tools.registry import ToolRegistry


class Provider:
    def complete(self, messages, tools):
        return ProviderResponse(content="done")


class FakeExtractor:
    def extract(self, dialogue):
        return None


class FakeEmbedder:
    def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]


def _client(tmp_path):
    sessions = JsonSessionRepository(tmp_path / "sessions")
    agent = AgentService(AgentLoop(Provider(), ToolRegistry()), sessions, "system")
    memory = MemoryService(MemoryRepository(tmp_path / "memory"))
    profile = ProfileService(ProfileRepository(tmp_path / "profile"), FakeExtractor(), enabled=False)
    engine = SimilarityEngine(embedder=FakeEmbedder())
    curator = CuratorService(
        CuratorRepository(tmp_path / "curator"), memory, profile, engine, enable_llm=False
    )
    app = create_app(agent, sessions, memory=memory, profile=profile, curator=curator)
    return TestClient(app), memory, curator


def test_run_curator(tmp_path):
    client, memory, _ = _client(tmp_path)
    memory.add("用户偏好 React", "preference")
    memory.add("用户偏好 React 框架", "preference")

    response = client.post("/api/curator/run")

    assert response.status_code == 201
    data = response.json()
    assert data["id"].startswith("cur-")
    assert len(data["suggestions"]) == 1
    assert data["suggestions"][0]["kind"] == "merge"


def test_list_reports(tmp_path):
    client, memory, _ = _client(tmp_path)
    memory.add("用户偏好 React", "preference")
    memory.add("用户偏好 React 框架", "preference")
    client.post("/api/curator/run")

    response = client.get("/api/curator/reports")

    assert response.status_code == 200
    assert len(response.json()["reports"]) == 1


def test_get_report(tmp_path):
    client, memory, _ = _client(tmp_path)
    memory.add("用户偏好 React", "preference")
    memory.add("用户偏好 React 框架", "preference")
    report = client.post("/api/curator/run").json()

    response = client.get(f"/api/curator/reports/{report['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == report["id"]


def test_get_report_missing_404(tmp_path):
    client, _, _ = _client(tmp_path)
    response = client.get("/api/curator/reports/cur-ffffffffffff")
    assert response.status_code == 404


def test_apply_suggestions(tmp_path):
    client, memory, _ = _client(tmp_path)
    memory.add("用户偏好 React", "preference")
    memory.add("用户偏好 React 框架", "preference")
    report = client.post("/api/curator/run").json()

    response = client.post(f"/api/curator/reports/{report['id']}/apply", json={"all": True})

    assert response.status_code == 200
    assert response.json()["applied"] == 1
    assert len(memory.list()) == 1


def test_dismiss_suggestions(tmp_path):
    client, memory, _ = _client(tmp_path)
    memory.add("用户偏好 React", "preference")
    memory.add("用户偏好 React 框架", "preference")
    report = client.post("/api/curator/run").json()

    response = client.post(f"/api/curator/reports/{report['id']}/dismiss", json={"all": True})

    assert response.status_code == 200
    assert response.json()["dismissed"] == 1
    assert len(memory.list()) == 2  # dismiss 不改数据


def test_apply_missing_report_404(tmp_path):
    client, _, _ = _client(tmp_path)
    response = client.post("/api/curator/reports/cur-ffffffffffff/apply", json={"all": True})
    assert response.status_code == 404
