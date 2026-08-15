import pytest

from iris_agent.core.models import ProviderResponse
from iris_agent.profile.extractor import ProfileExtractor
from iris_agent.profile.models import ProfilePatch
from iris_agent.providers.base import ModelProvider


class FakeProvider:
    def __init__(self, content: str):
        self.content = content
        self.last_messages = None

    def complete(self, messages, tools):
        self.last_messages = messages
        return ProviderResponse(content=self.content, tool_calls=[])


class RaisingProvider:
    def complete(self, messages, tools):
        raise RuntimeError("provider down")


def test_extract_parses_json():
    extractor = ProfileExtractor(FakeProvider('{"name": "小明", "preferences": ["简洁回答"], "facts": ["后端工程师"]}'))

    patch = extractor.extract("用户：我叫小明，是后端工程师，喜欢简洁回答")

    assert patch.name == "小明"
    assert patch.preferences == ["简洁回答"]
    assert patch.facts == ["后端工程师"]
    assert patch.goals is None
    assert patch.style is None


def test_extract_strips_markdown_fence():
    extractor = ProfileExtractor(FakeProvider('```json\n{"goals": ["构建 agent"]}\n```'))

    patch = extractor.extract("用户：我在构建 agent")

    assert patch.goals == ["构建 agent"]


def test_extract_returns_empty_patch_for_no_fields():
    extractor = ProfileExtractor(FakeProvider("{}"))

    patch = extractor.extract("用户：你好")

    assert patch.name is None
    assert patch.preferences is None
    assert patch.goals is None
    assert patch.style is None
    assert patch.facts is None


def test_extract_returns_empty_patch_on_invalid_json():
    extractor = ProfileExtractor(FakeProvider("not json at all"))

    patch = extractor.extract("用户：随便聊聊")

    assert patch.name is None
    assert patch.preferences is None


def test_extract_returns_empty_patch_on_provider_error():
    extractor = ProfileExtractor(RaisingProvider())

    patch = extractor.extract("用户：随便聊聊")

    assert patch.name is None
    assert patch.preferences is None


def test_extract_ignores_unknown_fields():
    extractor = ProfileExtractor(FakeProvider('{"name": "小明", "hobby": "钓鱼"}'))

    patch = extractor.extract("用户：我叫小明")

    assert patch.name == "小明"
    assert patch.preferences is None
