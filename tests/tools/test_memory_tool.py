from iris_agent.memory.repository import MemoryRepository
from iris_agent.memory.service import MemoryService
from iris_agent.tools.builtin.memory_tool import build_remember_tool


def test_remember_tool_saves_memory(tmp_path):
    memory = MemoryService(MemoryRepository(tmp_path))
    tool = build_remember_tool(memory)

    result = tool.invoke({"content": "用户偏好中文", "category": "preference"})

    assert result.ok
    assert result.value["category"] == "preference"
    assert [entry.content for entry in memory.list()] == ["用户偏好中文"]


def test_remember_tool_defaults_category_to_fact(tmp_path):
    memory = MemoryService(MemoryRepository(tmp_path))
    tool = build_remember_tool(memory)

    result = tool.invoke({"content": "项目使用 Python 3"})

    assert result.ok
    assert memory.list()[0].category == "fact"


def test_remember_tool_rejects_invalid_category(tmp_path):
    memory = MemoryService(MemoryRepository(tmp_path))
    tool = build_remember_tool(memory)

    result = tool.invoke({"content": "内容", "category": "unknown"})

    assert not result.ok
    assert result.error_code == "invalid_memory"


def test_remember_tool_rejects_blank_content(tmp_path):
    memory = MemoryService(MemoryRepository(tmp_path))
    tool = build_remember_tool(memory)

    result = tool.invoke({"content": "", "category": "fact"})

    assert not result.ok
    assert result.error_code == "invalid_memory"
