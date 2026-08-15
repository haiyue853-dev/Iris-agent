from iris_agent.subagent.models import SubagentRequest, SubagentResult
from iris_agent.tools.builtin.subagent_tool import build_delegate_task_tool
from iris_agent.tools.registry import ToolRegistry


class FakeRunner:
    def __init__(self, result: SubagentResult):
        self.result = result
        self.last_request: SubagentRequest | None = None

    def run(self, request: SubagentRequest) -> SubagentResult:
        self.last_request = request
        return self.result


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
