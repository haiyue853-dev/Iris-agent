import json
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import httpx
import pytest

from iris_agent.core.agent import AgentLoop
from iris_agent.core.errors import ProviderError
from iris_agent.core.models import ProviderResponse, ToolCall
from iris_agent.mcp_center.service import McpCenterService
from iris_agent.providers.openai_compat import OpenAICompatibleProvider
from iris_agent.tools.base import Tool
from iris_agent.tools.registry import ToolRegistry


def test_stdio_timeout_does_not_wait_for_blocked_reader():
    class SlowOutput:
        def readline(self):
            time.sleep(.3)
            return ''

    started = time.monotonic()
    with pytest.raises(TimeoutError):
        McpCenterService._read_response(SimpleNamespace(stdout=SlowOutput()), 1, .04)
    assert time.monotonic() - started < .2


def test_stdio_notifications_do_not_reset_request_deadline():
    class Notifications:
        def __init__(self):
            self.count = 0

        def readline(self):
            time.sleep(.02)
            self.count += 1
            return json.dumps({'method': 'progress'} if self.count < 8 else {'id': 1, 'result': {}}) + '\n'

    with pytest.raises(TimeoutError):
        McpCenterService._read_response(SimpleNamespace(stdout=Notifications()), 1, .05)


def test_http_sse_returns_matching_response_without_waiting_for_eof(tmp_path, monkeypatch):
    closed = []

    class Events(httpx.SyncByteStream):
        def __iter__(self):
            yield b'data: {"method":"notifications/progress"}\r\n\r\n'
            yield b'data: {"id":2,"result":{"tools":[]}}\r\n\r\n'
            raise AssertionError('must not wait for SSE connection to close')

        def close(self):
            closed.append(True)

    def handler(request):
        payload = json.loads(request.content)
        if payload['method'] == 'initialize':
            return httpx.Response(200, json={'id': 1, 'result': {}})
        return httpx.Response(200, stream=Events(), headers={'content-type': 'text/event-stream'})

    factory = httpx.Client
    monkeypatch.setattr('iris_agent.mcp_center.service.httpx.Client', lambda **kw: factory(transport=httpx.MockTransport(handler), **kw))
    service = McpCenterService(tmp_path / 'mcp.json')
    server = service.create(name='test', transport='http', url='https://example.test/mcp')
    service.set_enabled(server.id, True)
    try:
        assert service.discover_tools(server.id) == ()
        assert closed
    finally:
        service.close()


@pytest.mark.parametrize('stall_at', ['connect', 'next_chunk'])
def test_model_stream_timeout_covers_connection_and_later_chunks(stall_at):
    closed = []

    def chunks():
        try:
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content='hello', tool_calls=None))])
            if stall_at == 'next_chunk':
                time.sleep(.3)
        finally:
            closed.append(True)

    def create(**kwargs):
        if stall_at == 'connect':
            time.sleep(.3)
        return chunks()

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    provider = OpenAICompatibleProvider(client, 'test', first_token_timeout_seconds=.04)
    started = time.monotonic()
    with pytest.raises(ProviderError, match='超时'):
        list(provider.stream([], []))
    assert time.monotonic() - started < .2


def test_tool_budget_is_enforced_even_when_model_ignores_empty_schemas():
    calls = []

    class Provider:
        count = 0

        def complete(self, messages, tools):
            self.count += 1
            if self.count > 5:
                return ProviderResponse(content='stop')
            return ProviderResponse(tool_calls=[ToolCall(str(self.count), 'lookup', {})])

    registry = ToolRegistry()
    registry.register(Tool('lookup', 'lookup', {'type': 'object'}, lambda: calls.append(True)))
    events = list(AgentLoop(Provider(), registry, max_tool_rounds=1).run([]))
    assert len(calls) == 1
    assert events[-1].type == 'message_completed'


def test_stdio_tool_timeout_terminates_real_child(tmp_path, monkeypatch):
    service = McpCenterService(tmp_path / 'mcp.json')
    script = (
        'import sys,json,time\n'
        'for line in sys.stdin:\n'
        ' request=json.loads(line)\n'
        ' if request["method"]=="initialize":\n'
        '  print(json.dumps({"id":request["id"],"result":{}}),flush=True)\n'
        ' elif request["method"]=="tools/call": time.sleep(5)\n'
    )
    server = service.create(name='slow', command=sys.executable, args=('-u', '-c', script), allowed_tools=('slow',))
    service.set_enabled(server.id, True)
    service.set_timeout_seconds(server.id, 1)
    children = []
    popen = subprocess.Popen

    def start(*args, **kwargs):
        child = popen(*args, **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr('iris_agent.mcp_center.service.subprocess.Popen', start)
    started = time.monotonic()
    try:
        with pytest.raises(ValueError, match='unable to call MCP tool'):
            service.call_tool(server.id, 'slow', {})
        assert time.monotonic() - started < 3
        assert children[0].poll() is not None
        assert not service.is_connected(server.id)
        assert service.events(server.id)[0]['failure_kind'] == 'timeout'
    finally:
        service.close()
        for child in children:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=2)


def test_model_total_deadline_applies_to_continuous_empty_chunks():
    closed = threading.Event()

    def chunks():
        try:
            for _ in range(100):
                time.sleep(.01)
                yield SimpleNamespace(choices=[])
        finally:
            closed.set()

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: chunks())))
    provider = OpenAICompatibleProvider(client, 'test', first_token_timeout_seconds=.1, stream_timeout_seconds=.05)
    with pytest.raises(ProviderError, match='超时'):
        list(provider.stream([], []))
    assert closed.wait(.5), 'timed-out response must be closed after pending read returns'


def test_model_stream_is_closed_when_consumer_stops_early():
    closed = threading.Event()

    def chunks():
        try:
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content='hello', tool_calls=None))])
            yield SimpleNamespace(choices=[])
        finally:
            closed.set()

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: chunks())))
    stream = OpenAICompatibleProvider(client, 'test').stream([], [])
    assert next(stream).content == 'hello'
    stream.close()
    assert closed.wait(.5)
