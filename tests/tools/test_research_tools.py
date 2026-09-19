from iris_agent.tools.builtin.files import build_read_file_tool


def test_read_file_pages_by_line_and_continues_inside_long_lines(tmp_path):
    (tmp_path / 'code.py').write_text('one\ntwo\nabcdef\n', encoding='utf-8')
    tool = build_read_file_tool(tmp_path, max_chars=100)
    result = tool.invoke({'path': 'code.py', 'offset': 2, 'limit': 1})
    assert result.ok
    assert result.value['content'] == 'two\n'
    assert result.value['total_lines'] == 3
    assert result.value['next_offset'] == 3
    small = build_read_file_tool(tmp_path, max_chars=3)
    first = small.invoke({'path': 'code.py', 'offset': 3}).value
    second = small.invoke({'path': 'code.py', 'offset': first['next_offset'], 'column': first['next_column']}).value
    assert first['content'] + second['content'] == 'abcdef'


def test_search_files_returns_lines_and_excludes_dependencies(tmp_path):
    from iris_agent.tools.builtin.files import build_search_files_tool
    (tmp_path / 'main.py').write_text('first\nneedle = 1\n', encoding='utf-8')
    (tmp_path / 'node_modules').mkdir()
    (tmp_path / 'node_modules' / 'dep.py').write_text('needle', encoding='utf-8')
    tool = build_search_files_tool(tmp_path)
    result = tool.invoke({'query': 'needle', 'file_pattern': '*.py'})
    assert result.ok
    assert result.value['matches'] == [{'path': 'main.py', 'line': 2, 'text': 'needle = 1'}]
    assert tool.invoke({'query': '*.py', 'target': 'files'}).value['matches'] == [{'path': 'main.py'}]
    assert not tool.invoke({'query': 'needle', 'path': '..'}).ok


def test_registry_validates_enums_and_nested_array_items_before_execution():
    from iris_agent.tools.base import Tool
    from iris_agent.tools.registry import ToolRegistry
    called = []
    registry = ToolRegistry()
    registry.register(Tool('extract', '', {'type': 'object', 'properties': {'urls': {'type': 'array', 'minItems': 1, 'maxItems': 5, 'items': {'type': 'string', 'minLength': 1}}, 'mode': {'type': 'string', 'enum': ['text']}}, 'required': ['urls']}, lambda **kw: called.append(kw)))
    for args in ({'urls': []}, {'urls': [42]}, {'urls': ['']}, {'urls': ['a'] * 6}, {'urls': ['a'], 'mode': 'bad'}):
        assert registry.invoke('extract', args).error_code == 'invalid_tool_arguments'
    assert called == []
