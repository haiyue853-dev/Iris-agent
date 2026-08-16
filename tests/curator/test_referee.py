"""LLM 冲突精判测试：三分类输出与异常降级。"""

from __future__ import annotations

from iris_agent.core.models import ProviderResponse
from iris_agent.curator.referee import ConflictReferee


class FakeProvider:
    def __init__(self, content="unrelated", error=False):
        self.content = content
        self.error = error
        self.calls = []

    def complete(self, messages, tools=None):
        self.calls.append((messages, tools))
        if self.error:
            raise RuntimeError("llm failed")
        return ProviderResponse(content=self.content)


def test_judge_duplicate():
    referee = ConflictReferee(FakeProvider(content="duplicate"))
    assert referee.judge("a", "b") == "duplicate"


def test_judge_conflict():
    referee = ConflictReferee(FakeProvider(content="conflict"))
    assert referee.judge("a", "b") == "conflict"


def test_judge_unrelated():
    referee = ConflictReferee(FakeProvider(content="unrelated"))
    assert referee.judge("a", "b") == "unrelated"


def test_judge_parses_chinese_label():
    referee = ConflictReferee(FakeProvider(content="冲突"))
    assert referee.judge("a", "b") == "conflict"


def test_judge_falls_back_to_unrelated_on_error():
    referee = ConflictReferee(FakeProvider(error=True))
    assert referee.judge("a", "b") == "unrelated"


def test_judge_sends_only_texts():
    provider = FakeProvider(content="duplicate")
    referee = ConflictReferee(provider)
    referee.judge("偏好A", "偏好B")
    messages, tools = provider.calls[0]
    assert tools == []
    combined = "".join(message.content for message in messages)
    assert "偏好A" in combined and "偏好B" in combined
