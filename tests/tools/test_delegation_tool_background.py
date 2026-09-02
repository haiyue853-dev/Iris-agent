from iris_agent.subagent.models import SubagentRequest, SubagentResult
from iris_agent.tools.builtin.subagent_tool import build_delegate_task_tool


class Service:
    def __init__(self):
        self.request = None

    def run(self, request):
        self.request = request
        return SubagentResult(True, "done", 1, "delegation-sync")

    def submit_background(self, request):
        self.request = request
        return "delegation-bg"


def test_delegate_tool_returns_persisted_id_for_sync_run():
    service = Service()

    result = build_delegate_task_tool(service).invoke({"goal": "work"})

    assert result.value["delegation_id"] == "delegation-sync"
    assert result.value["status"] == "succeeded"


def test_delegate_tool_can_submit_background_run():
    service = Service()

    result = build_delegate_task_tool(service).invoke({"goal": "work", "background": True})

    assert result.value == {"ok": True, "delegation_id": "delegation-bg", "status": "queued"}
    assert isinstance(service.request, SubagentRequest)
