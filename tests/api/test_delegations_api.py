from fastapi.testclient import TestClient

from iris_agent.api.app import create_app
from iris_agent.subagent.delegation import DelegationRepository, DelegationService
from iris_agent.subagent.models import SubagentRequest, SubagentResult


class Runner:
    def run(self, request, is_cancelled=None):
        return SubagentResult(True, f"完成:{request.goal}", 1)


def test_delegation_routes_list_detail_and_cancel(tmp_path):
    repository = DelegationRepository(tmp_path / "delegation.sqlite3")
    service = DelegationService(Runner(), repository)
    first = repository.create(SubagentRequest("分析代码"), parent_task_id="task-1")
    repository.create(SubagentRequest("较早任务"))
    client = TestClient(create_app(object(), object(), delegation=service))

    listed = client.get("/api/delegations", params={"parent_task_id": "task-1"})
    detail = client.get(f"/api/delegations/{first.id}")
    cancelled = client.delete(f"/api/delegations/{first.id}")

    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["delegations"]] == [first.id]
    assert detail.json()["goal"] == "分析代码"
    assert detail.json()["parent_task_id"] == "task-1"
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    service.close()


def test_delegation_routes_return_safe_conflicts_and_not_found(tmp_path):
    repository = DelegationRepository(tmp_path / "delegation.sqlite3")
    service = DelegationService(Runner(), repository)
    record = repository.create(SubagentRequest("已完成"))
    repository.finish(record.id, SubagentResult(True, "done", 1))
    client = TestClient(create_app(object(), object(), delegation=service))

    assert client.get("/api/delegations/missing").status_code == 404
    response = client.delete(f"/api/delegations/{record.id}")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "delegation_not_active"
    service.close()
