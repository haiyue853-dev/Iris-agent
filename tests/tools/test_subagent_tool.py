from iris_agent.subagent.models import SubagentRequest, SubagentResult
from iris_agent.tools.builtin.subagent_tool import build_delegate_task_tool, build_delegate_tasks_tool, build_request_subagent_collaboration_tool
from iris_agent.tools.registry import ToolRegistry


class FakeRunner:
    def __init__(self, result: SubagentResult):
        self.result = result
        self.last_request: SubagentRequest | None = None
        self.parallel_requests: list[SubagentRequest] = []

    def run(self, request: SubagentRequest) -> SubagentResult:
        self.last_request = request
        return self.result

    def run_parallel(self, requests: list[SubagentRequest], max_workers: int | None = None) -> list[SubagentResult]:
        self.parallel_requests = list(requests)
        self.last_max_workers = max_workers
        return [SubagentResult(ok=(r.goal != "失败"), result=f"结论:{r.goal}", rounds=1) for r in requests]


def test_delegate_tool_returns_runner_result():
    runner = FakeRunner(SubagentResult(ok=True, result="结论", rounds=1))
    tool = build_delegate_task_tool(runner)

    result = tool.invoke({"goal": "分析代码"})

    assert result.ok
    assert result.value == {"ok": True, "result": "结论", "rounds": 1}
    assert runner.last_request.goal == "分析代码"
    assert runner.last_request.context is None


def test_delegate_tool_passes_optional_arguments():
    runner = FakeRunner(SubagentResult(ok=True, result="结论", rounds=2))
    tool = build_delegate_task_tool(runner)

    tool.invoke({"goal": "分析", "context": "背景", "allowed_tools": ["read_file"], "max_rounds": 3})

    assert runner.last_request.context == "背景"
    assert runner.last_request.allowed_tools == ["read_file"]
    assert runner.last_request.max_rounds == 3


def test_delegate_tool_requires_goal():
    runner = FakeRunner(SubagentResult(ok=True, result="结论", rounds=0))
    registry = ToolRegistry()
    registry.register(build_delegate_task_tool(runner))

    result = registry.invoke("delegate_task", {})

    assert not result.ok
    assert result.error_code == "invalid_tool_arguments"


def test_delegate_tool_passes_through_failure():
    runner = FakeRunner(SubagentResult(ok=False, result="", rounds=0))
    tool = build_delegate_task_tool(runner)

    result = tool.invoke({"goal": "会失败的任务"})

    assert result.ok
    assert result.value == {"ok": False, "result": "", "rounds": 0}


def test_delegate_tasks_tool_runs_batch_and_summarizes():
    runner = FakeRunner(SubagentResult(ok=True, result="结论", rounds=1))
    tool = build_delegate_tasks_tool(runner)

    result = tool.invoke({"tasks": [{"goal": "任务一"}, {"goal": "任务二"}, {"goal": "失败"}]})

    assert result.ok
    value = result.value
    assert value["total"] == 3
    assert value["succeeded"] == 2
    assert value["failed"] == 1
    assert value["results"][0] == {"ok": True, "result": "结论:任务一", "rounds": 1}
    assert value["results"][2] == {"ok": False, "result": "结论:失败", "rounds": 1}
    assert [r.goal for r in runner.parallel_requests] == ["任务一", "任务二", "失败"]


def test_delegate_tasks_tool_passes_optional_arguments_and_max_workers():
    runner = FakeRunner(SubagentResult(ok=True, result="结论", rounds=1))
    tool = build_delegate_tasks_tool(runner)

    tool.invoke({
        "tasks": [
            {"goal": "任务", "context": "背景", "allowed_tools": ["read_file"], "max_rounds": 3},
        ],
        "max_workers": 2,
    })

    request = runner.parallel_requests[0]
    assert request.context == "背景"
    assert request.allowed_tools == ["read_file"]
    assert request.max_rounds == 3
    assert runner.last_max_workers == 2


def test_delegate_tasks_tool_skips_invalid_entries():
    runner = FakeRunner(SubagentResult(ok=True, result="结论", rounds=0))
    tool = build_delegate_tasks_tool(runner)

    result = tool.invoke({"tasks": [{"goal": ""}, "not-a-dict", {"goal": "有效任务"}]})

    assert result.value["total"] == 1
    assert [r.goal for r in runner.parallel_requests] == ["有效任务"]


def test_delegate_tasks_tool_requires_tasks():
    runner = FakeRunner(SubagentResult(ok=True, result="结论", rounds=0))
    registry = ToolRegistry()
    registry.register(build_delegate_tasks_tool(runner))

    result = registry.invoke("delegate_tasks", {})

    assert not result.ok
    assert result.error_code == "invalid_tool_arguments"


def test_delegate_tool_passes_role():
    runner = FakeRunner(SubagentResult(ok=True, result="ok", rounds=1))
    tool = build_delegate_task_tool(runner)

    tool.invoke({"goal": "research", "role": "researcher"})

    assert runner.last_request.role == "researcher"


def test_delegate_tasks_tool_passes_each_role():
    runner = FakeRunner(SubagentResult(ok=True, result="ok", rounds=1))
    tool = build_delegate_tasks_tool(runner)

    tool.invoke({"tasks": [{"goal": "write", "role": "report_writer"}]})

    assert runner.parallel_requests[0].role == "report_writer"


def test_request_subagent_collaboration_requires_user_approval():
    tool = build_request_subagent_collaboration_tool()

    result = tool.invoke({"reason": "需要分别检索和整理多份资料"})

    assert result.ok
    assert result.value["requested"] is True
    assert tool.requires_approval is True
