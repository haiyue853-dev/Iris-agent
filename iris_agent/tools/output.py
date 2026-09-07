"""Keep original results while bounding the copies sent to the model."""

from dataclasses import replace
from pathlib import Path
import re

from iris_agent.tools.base import Tool, ToolInvocationError


class ToolOutputBudget:
    def __init__(self, directory: Path | None = None, per_result_chars: int = 20000, total_chars: int = 60000):
        if per_result_chars < 512 or total_chars < 512:
            raise ValueError('Tool output limits must be at least 512 characters')
        self.directory = directory
        self.per_result_chars = per_result_chars
        self.total_chars = total_chars

    def _path(self, scope, result_id):
        if not re.fullmatch(r'[A-Za-z0-9_-]+', scope) or not re.fullmatch(r'[A-Za-z0-9_-]+', result_id):
            raise ToolInvocationError('invalid_result_id', '工具结果标识无效')
        base = self.directory.resolve()
        path = (base / scope / (result_id + '.txt')).resolve()
        if not path.is_relative_to(base / scope):
            raise ToolInvocationError('invalid_result_id', '工具结果路径无效')
        return path

    def prepare(self, messages, scope):
        count = sum(message.role == 'tool' for message in messages)
        limit = min(self.per_result_chars, self.total_chars // max(1, count))
        prepared = []
        for message in messages:
            if message.role != 'tool' or len(message.content) <= limit:
                prepared.append(message)
                continue
            saved = False
            if self.directory is not None:
                try:
                    path = self._path(scope, message.id)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if not path.exists():
                        path.write_text(message.content, encoding='utf-8')
                    saved = True
                except OSError:
                    # The original is still in the session/live message list.
                    pass
            header = f'[工具输出已缩短；result_id={message.id}；总字符数={len(message.content)}；使用 read_tool_result 分段读取。持久化={saved}]\n'
            available = max(0, limit - len(header) - 12)
            preview = message.content[:available // 2] + '\n[…省略…]\n' + (message.content[-(available - available // 2):] if available else '')
            prepared.append(replace(message, prompt_content=(header + preview)[:limit]))
        return prepared

    def reader(self, scope, messages):
        def read_tool_result(result_id: str, offset: int = 0, limit: int = 2000):
            if offset < 0 or limit < 1 or not re.fullmatch(r'[A-Za-z0-9_-]+', result_id):
                raise ToolInvocationError('invalid_tool_arguments', '结果标识、偏移或长度无效')
            content = next((message.content for message in messages if message.role == 'tool' and message.id == result_id), None)
            if content is None and self.directory is not None:
                try:
                    content = self._path(scope, result_id).read_text(encoding='utf-8')
                except OSError:
                    pass
            if content is None:
                raise ToolInvocationError('tool_result_not_found', '当前会话中没有该工具结果')
            size = min(limit, max(1, self.per_result_chars // 8))
            text = content[offset:offset + size]
            end = min(len(content), offset + len(text))
            return {'text': text, 'offset': offset, 'next_offset': end if end < len(content) else None, 'total_chars': len(content)}

        return Tool('read_tool_result', '按字符偏移分段读取当前会话的完整工具结果；继续读取时使用 next_offset。', {
            'type': 'object', 'properties': {'result_id': {'type': 'string'}, 'offset': {'type': 'integer'}, 'limit': {'type': 'integer'}},
            'required': ['result_id'], 'additionalProperties': False,
        }, read_tool_result)
