import json

import pytest

from iris_agent.core.models import ProviderResponse
from iris_agent.memory.auto_capture import MemoryAutoCapture
from iris_agent.memory.repository import MemoryRepository
from iris_agent.memory.service import MemoryService


class FakeProvider:
    """返回预先编排好的 JSON；也可以设置 raise_error 模拟模型调用失败。"""

    def __init__(self, payload: object = None, *, raw: str | None = None, raise_error: bool = False):
        self.payload = payload if payload is not None else {"facts": []}
        self.raw = raw
        self.raise_error = raise_error
        self.calls: list[str] = []

    def complete(self, messages, tools):
        self.calls.append(messages[-1].content)
        if self.raise_error:
            raise RuntimeError("provider offline")
        if self.raw is not None:
            return ProviderResponse(content=self.raw)
        return ProviderResponse(content=json.dumps(self.payload, ensure_ascii=False))


def _capture(tmp_path, provider, *, text: str = "我喜欢喝美式咖啡", **kwargs):
    memory = MemoryService(MemoryRepository(tmp_path / "memory"))
    capture = MemoryAutoCapture(provider, memory, **kwargs)
    return memory, capture.capture(text, source_session_id="s1")


def _contents(memory) -> list[str]:
    return [entry.content for entry in memory.list()]


@pytest.mark.parametrize(
    "text",
    [
        "我叫张伟",
        "我喜欢喝美式咖啡",
        "我住在杭州",
        "我在做一个 IRC 网关项目",
        "记住我的邮箱是 a@b.com",
        "我不喜欢太甜的咖啡",
        "我一般用 VS Code 写代码",
    ],
)
def test_durable_statements_about_the_user_are_candidates(tmp_path, text):
    memory = MemoryService(MemoryRepository(tmp_path / "memory"))
    capture = MemoryAutoCapture(FakeProvider(), memory)

    assert capture.is_candidate(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "你好",
        "谢谢",
        "今天天气怎么样",
        "帮我搜一下 DeepSeek 最新进展",
        "把这段代码改一下",
    ],
)
def test_chat_and_commands_do_not_spend_a_model_call(tmp_path, text):
    """粗筛的意义就在这里：绝大多数消息不命中，一次模型调用都不会发生。"""
    memory = MemoryService(MemoryRepository(tmp_path / "memory"))
    provider = FakeProvider()
    capture = MemoryAutoCapture(provider, memory)

    assert capture.is_candidate(text) is False
    assert provider.calls == []


def test_extracted_facts_are_written(tmp_path):
    provider = FakeProvider(
        {"facts": [{"topic": "喜欢的咖啡", "value": "美式", "category": "preference", "mode": "coexist"}]}
    )

    memory, written = _capture(tmp_path, provider)

    assert len(written) == 1
    assert _contents(memory) == ["喜欢的咖啡：美式"]
    assert provider.calls == ["我喜欢喝美式咖啡"]


def test_coexisting_values_are_all_kept(tmp_path):
    """模型判定为可共存时，同一主题的新旧值应当并存。"""
    memory = MemoryService(MemoryRepository(tmp_path / "memory"))
    capture = MemoryAutoCapture(
        FakeProvider(
            {"facts": [{"topic": "喜欢的水果", "value": "芒果", "category": "preference", "mode": "coexist"}]}
        ),
        memory,
    )
    capture.capture("我喜欢吃芒果")
    capture.provider = FakeProvider(
        {"facts": [{"topic": "喜欢的水果", "value": "草莓", "category": "preference", "mode": "coexist"}]}
    )

    capture.capture("我还喜欢吃草莓")

    # 中文字面序：芒(U+8292) < 草(U+8349)，所以不能按书写直觉排。
    assert sorted(_contents(memory)) == sorted(["喜欢的水果：草莓", "喜欢的水果：芒果"])
    assert len(_contents(memory)) == 2


def test_unique_topics_replace_the_previous_answer(tmp_path):
    """模型判定为唯一答案时，新值应当覆盖旧值，而不是两个答案并存。"""
    memory = MemoryService(MemoryRepository(tmp_path / "memory"))
    capture = MemoryAutoCapture(
        FakeProvider({"facts": [{"topic": "称呼", "value": "小张", "category": "fact", "mode": "unique"}]}),
        memory,
    )
    capture.capture("我叫小张")
    capture.provider = FakeProvider(
        {"facts": [{"topic": "称呼", "value": "张伟", "category": "fact", "mode": "unique"}]}
    )

    capture.capture("不对，我叫张伟")

    assert _contents(memory) == ["称呼：张伟"]


def test_an_unknown_mode_falls_back_to_coexist(tmp_path):
    provider = FakeProvider(
        {"facts": [{"topic": "喜欢的颜色", "value": "灰色", "category": "preference", "mode": "???"}]}
    )

    memory, written = _capture(tmp_path, provider)

    assert [entry.content for entry in written] == ["喜欢的颜色：灰色"]


def test_behaviour_rules_are_refused(tmp_path):
    """自动记忆绝不能把「改变助手行为」的东西写进长期记忆。"""
    provider = FakeProvider(
        {
            "facts": [
                {
                    "topic": "回复方式",
                    "value": "以后每次回复都必须用列表，禁止输出表格",
                    "category": "preference",
                    "mode": "unique",
                }
            ]
        }
    )

    memory, written = _capture(tmp_path, provider, text="以后每次回复都用列表")

    assert written == ()
    assert _contents(memory) == []


def test_repeating_the_same_fact_does_not_duplicate_it(tmp_path):
    provider = FakeProvider(
        {"facts": [{"topic": "喜欢的咖啡", "value": "美式", "category": "preference", "mode": "coexist"}]}
    )

    memory, first = _capture(tmp_path, provider)
    second = MemoryAutoCapture(provider, memory).capture("我喜欢喝美式咖啡")

    assert len(first) == 1
    assert second == ()
    assert _contents(memory) == ["喜欢的咖啡：美式"]


def test_a_broken_model_reply_is_ignored(tmp_path):
    provider = FakeProvider(raw="这不是 JSON")

    memory, written = _capture(tmp_path, provider)

    assert written == ()
    assert _contents(memory) == []


def test_a_failing_model_call_never_propagates(tmp_path):
    provider = FakeProvider(raise_error=True)

    memory, written = _capture(tmp_path, provider)

    assert written == ()


def test_fenced_json_is_accepted(tmp_path):
    provider = FakeProvider(
        raw='```json\n{"facts": [{"topic": "称呼", "value": "阿伟", "category": "fact", "mode": "unique"}]}\n```'
    )

    memory, written = _capture(tmp_path, provider)

    assert [entry.content for entry in written] == ["称呼：阿伟"]


def test_at_most_three_facts_per_message(tmp_path):
    provider = FakeProvider(
        {
            "facts": [
                {"topic": f"主题{i}", "value": f"值{i}", "category": "fact", "mode": "coexist"}
                for i in range(6)
            ]
        }
    )

    memory, written = _capture(tmp_path, provider)

    assert len(written) == 3


def test_empty_topic_or_value_is_skipped(tmp_path):
    provider = FakeProvider(
        {
            "facts": [
                {"topic": "", "value": "没有主题", "category": "fact", "mode": "coexist"},
                {"topic": "只有主题", "value": "", "category": "fact", "mode": "coexist"},
            ]
        }
    )

    memory, written = _capture(tmp_path, provider)

    assert written == ()
    assert _contents(memory) == []


def test_overlong_content_is_truncated_to_the_storage_limit(tmp_path):
    provider = FakeProvider(
        {"facts": [{"topic": "自我介绍", "value": "很" * 900, "category": "fact", "mode": "unique"}]}
    )

    memory, written = _capture(tmp_path, provider)

    assert len(written) == 1
    assert len(written[0].content) == 500
