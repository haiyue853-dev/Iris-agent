import json

from iris_agent.core.models import Message


def test_budget_preserves_full_results_and_limits_model_context(tmp_path):
    from iris_agent.tools.output import ToolOutputBudget
    budget = ToolOutputBudget(tmp_path, per_result_chars=1000, total_chars=1500)
    originals = [Message(role='tool', content=json.dumps({'text': str(i) * 4000}), tool_call_id=str(i)) for i in range(3)]
    prepared = budget.prepare(originals, 'session_a')
    assert sum(len(item.model_content) for item in prepared) <= 1500
    assert all(len(item.model_content) <= 1000 for item in prepared)
    assert all(item.prompt_content is None for item in originals)
    assert prepared[0].content == originals[0].content
    reader = budget.reader('session_a', originals)
    result = reader.invoke({'result_id': originals[0].id, 'offset': 3500, 'limit': 100})
    assert result.ok
    assert result.value['text'] == originals[0].content[3500:3600]
    assert result.value['next_offset'] == 3600


def test_saved_results_are_scoped_and_readable_after_restart(tmp_path):
    from iris_agent.tools.output import ToolOutputBudget
    message = Message(role='tool', content='x' * 3000)
    budget = ToolOutputBudget(tmp_path, per_result_chars=1000)
    budget.prepare([message], 'session_a')
    restarted = ToolOutputBudget(tmp_path)
    assert restarted.reader('session_a', []).invoke({'result_id': message.id}).ok
    assert not restarted.reader('session_b', []).invoke({'result_id': message.id}).ok
    assert not restarted.reader('session_a', []).invoke({'result_id': '../private'}).ok


def test_reader_pagination_stays_below_preview_limit(tmp_path):
    from iris_agent.tools.output import ToolOutputBudget
    budget = ToolOutputBudget(tmp_path, per_result_chars=1000)
    message = Message(role='tool', content='中文' * 5000)
    budget.prepare([message], 'session_a')
    result = budget.reader('session_a', []).invoke({'result_id': message.id, 'limit': 999999})
    assert result.ok
    assert len(json.dumps(result.value, ensure_ascii=False)) <= 1000


def test_agent_can_read_truncated_result_in_next_tool_round(tmp_path):
    from iris_agent.core.agent import AgentLoop
    from iris_agent.core.models import ProviderResponse, ToolCall
    from iris_agent.tools.base import Tool
    from iris_agent.tools.output import ToolOutputBudget
    from iris_agent.tools.registry import ToolRegistry

    class Provider:
        calls = 0

        def complete(self, messages, tools):
            self.calls += 1
            if self.calls == 1:
                return ProviderResponse(tool_calls=[ToolCall('c', 'large', {})])
            if self.calls == 2:
                result = messages[-1]
                assert len(result.model_content) <= 1000
                assert result.content == json.dumps({'text': 'x' * 4000}, ensure_ascii=False)
                assert 'read_tool_result' in [tool['function']['name'] for tool in tools]
                return ProviderResponse(tool_calls=[ToolCall('r', 'read_tool_result', {'result_id': result.id, 'offset': 3000, 'limit': 100})])
            assert json.loads(messages[-1].model_content)['text'] == 'x' * 100
            return ProviderResponse(content='done')

    registry = ToolRegistry()
    registry.register(Tool('large', '', {'type': 'object'}, lambda: {'text': 'x' * 4000}))
    loop = AgentLoop(Provider(), registry, output_budget=ToolOutputBudget(tmp_path, per_result_chars=1000))
    events = list(loop.run([]))
    assert events[-1].data['content'] == 'done'
    assert len(events[1].data['result']['text']) == 4000
    assert 'read_tool_result' not in registry.names()


def test_session_retains_original_and_archive_survives_compression(tmp_path):
    from iris_agent.core.agent import AgentLoop, AgentService
    from iris_agent.core.models import AgentEvent
    from iris_agent.sessions.json_store import JsonSessionRepository
    from iris_agent.tools.output import ToolOutputBudget
    from iris_agent.tools.registry import ToolRegistry
    sessions = JsonSessionRepository(tmp_path / 'sessions')
    session = sessions.create('test')
    budget = ToolOutputBudget(tmp_path / 'results', per_result_chars=1000)
    service = AgentService(AgentLoop(None, ToolRegistry(), output_budget=budget), sessions, 'system')
    service._persist_tool_result(session.id, AgentEvent('tool_finished', {'call_id': 'c', 'name': 'large', 'ok': True, 'result': {'text': 'z' * 4000}}))
    stored = sessions.get(session.id).messages[-1]
    assert len(stored.model_content) <= 1000
    assert len(json.loads(stored.content)['text']) == 4000
    reader = ToolOutputBudget(tmp_path / 'results').reader(session.id, [])
    assert reader.invoke({'result_id': stored.id, 'offset': 3000, 'limit': 50}).value['text'] == 'z' * 50
