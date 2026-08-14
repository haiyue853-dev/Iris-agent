from iris_agent.core.agent import AgentLoop, AgentService
from iris_agent.core.models import ProviderResponse, ToolCall
from iris_agent.sessions.json_store import JsonSessionRepository
from iris_agent.task_planning.repository import JsonTaskPlanRepository
from iris_agent.task_planning.service import TaskPlanService
from iris_agent.subagents.repository import JsonSubagentRepository
from iris_agent.subagents.service import SubagentService
from iris_agent.tools.base import Tool
from iris_agent.tools.registry import ToolRegistry


def test_task_plan_runs_steps_in_order(tmp_path):
    class Provider:
        def complete(self, messages, tools):
            return ProviderResponse(content="step completed")

    sessions = JsonSessionRepository(tmp_path / "sessions")
    session = sessions.create("task")
    service = TaskPlanService(JsonTaskPlanRepository(tmp_path / "plans"), AgentService(AgentLoop(Provider(), ToolRegistry()), sessions, "system"))
    plan = service.create(session.id, "collect questions", [
        {"title": "Search", "instruction": "Find sources"},
        {"title": "Extract", "instruction": "Extract Q&A"},
    ])

    after_first, _ = service.run_next(plan.id)
    after_second, _ = service.run_next(plan.id)

    assert [step.status for step in after_first.steps] == ["completed", "pending"]
    assert any(event.type == "step_completed" for event in after_first.steps[0].events)
    assert any(event.type == "text_delta" for event in after_first.steps[0].events)
    assert after_second.status == "completed"
    assert [step.status for step in after_second.steps] == ["completed", "completed"]


def test_task_plan_generates_steps_from_model_json(tmp_path):
    class Provider:
        def complete(self, messages, tools):
            return ProviderResponse(content='{"steps":[{"title":"Search","instruction":"Find trustworthy sources"},{"title":"Save","instruction":"Save validated Q&A"}]}')

    sessions = JsonSessionRepository(tmp_path / "sessions")
    session = sessions.create("task")
    service = TaskPlanService(JsonTaskPlanRepository(tmp_path / "plans"), AgentService(AgentLoop(Provider(), ToolRegistry()), sessions, "system"))

    plan = service.create_from_goal(session.id, "collect Python interview questions")

    assert [step.title for step in plan.steps] == ["Search", "Save"]
    assert plan.status == "active"


def test_task_plan_rejects_invalid_model_plan(tmp_path):
    class Provider:
        def complete(self, messages, tools):
            return ProviderResponse(content="not json")

    sessions = JsonSessionRepository(tmp_path / "sessions")
    session = sessions.create("task")
    service = TaskPlanService(JsonTaskPlanRepository(tmp_path / "plans"), AgentService(AgentLoop(Provider(), ToolRegistry()), sessions, "system"))

    try:
        service.create_from_goal(session.id, "collect")
    except ValueError as exc:
        assert str(exc) == "planner returned invalid JSON"
    else:
        raise AssertionError("invalid model output should be rejected")


def test_task_plan_recovers_waiting_approval_after_restart(tmp_path):
    class WaitingProvider:
        def complete(self, messages, tools):
            return ProviderResponse(tool_calls=[ToolCall("save-call", "save", {})])

    class ResumedProvider:
        def complete(self, messages, tools):
            return ProviderResponse(content="saved")

    sessions = JsonSessionRepository(tmp_path / "sessions")
    session = sessions.create("task")
    tools = ToolRegistry()
    tools.register(Tool("save", "save", {"type": "object", "properties": {}}, lambda: "ok", requires_approval=True))
    repository = JsonTaskPlanRepository(tmp_path / "plans")
    first = TaskPlanService(repository, AgentService(AgentLoop(WaitingProvider(), tools), sessions, "system"))
    plan = first.create(session.id, "save result", [{"title": "Save", "instruction": "Save it"}])

    waiting, _ = first.run_next(plan.id)
    restarted = TaskPlanService(repository, AgentService(AgentLoop(ResumedProvider(), tools), sessions, "system"))
    finished, events = restarted.resolve_approval(plan.id, True)

    assert waiting.status == "waiting_approval"
    assert waiting.steps[0].approval_call_id == "save-call"
    assert any(event.type == "approval_requested" for event in waiting.steps[0].events)
    assert finished.status == "completed"
    assert any(event.type == "tool_finished" for event in events)


def test_task_plan_delegates_step_and_records_subagent_result(tmp_path):
    class Provider:
        def complete(self, messages, tools):
            return ProviderResponse(content="delegated result")

    sessions = JsonSessionRepository(tmp_path / "sessions")
    session = sessions.create("task")
    agent = AgentService(AgentLoop(Provider(), ToolRegistry()), sessions, "system")
    subagents = SubagentService(JsonSubagentRepository(tmp_path / "subagents"), agent)
    service = TaskPlanService(JsonTaskPlanRepository(tmp_path / "plans"), agent, subagents)
    plan = service.create(session.id, "collect", [{"title": "Research", "instruction": "Research sources"}])

    updated, _ = service.delegate_step(plan.id, plan.steps[0].id, [])

    assert updated.status == "completed"
    assert updated.steps[0].status == "completed"
    assert updated.steps[0].result == "delegated result"
    assert updated.steps[0].subagent_id is not None
    assert any(event.type == "subagent_completed" for event in updated.steps[0].events)
