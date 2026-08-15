from iris_agent.subagent.models import SubagentRequest, SubagentResult


def test_subagent_request_defaults():
    req = SubagentRequest("分析代码")
    assert req.goal == "分析代码"
    assert req.context is None
    assert req.allowed_tools is None
    assert req.max_rounds is None


def test_subagent_request_with_options():
    req = SubagentRequest("分析代码", context="背景", allowed_tools=["read_file"], max_rounds=3)
    assert req.context == "背景"
    assert req.allowed_tools == ["read_file"]
    assert req.max_rounds == 3


def test_subagent_result_fields():
    result = SubagentResult(ok=True, result="结论", rounds=2)
    assert result.ok is True
    assert result.result == "结论"
    assert result.rounds == 2


def test_subagent_result_failure():
    result = SubagentResult(ok=False, result="", rounds=0)
    assert result.ok is False
    assert result.result == ""
    assert result.rounds == 0
