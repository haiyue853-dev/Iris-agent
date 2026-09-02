import time

from iris_agent.core.models import Message
from iris_agent.sessions.json_store import JsonSessionRepository
from iris_agent.subagent.delegation import DelegationRepository, DelegationService
from iris_agent.subagent.models import SubagentRequest, SubagentResult


class Runner:
    def run(self, request, is_cancelled=None):
        if is_cancelled and is_cancelled():
            return SubagentResult(False, "", 0)
        return SubagentResult(True, f"完成:{request.goal}", 1)


def test_service_persists_successful_delegation(tmp_path):
    repository = DelegationRepository(tmp_path / "delegation.sqlite3")
    service = DelegationService(Runner(), repository)

    result = service.run(SubagentRequest("分析代码"), parent_task_id="task-1")

    record = repository.get(result.delegation_id)
    assert record.status == "succeeded"
    assert record.parent_task_id == "task-1"
    assert record.result == "完成:分析代码"


def test_repository_recovers_running_as_interrupted_and_keeps_queued(tmp_path):
    repository = DelegationRepository(tmp_path / "delegation.sqlite3")
    queued = repository.create(SubagentRequest("排队"))
    running = repository.create(SubagentRequest("运行"))
    repository.mark_running(running.id)

    recovered = repository.recover()

    assert repository.get(queued.id).status == "queued"
    assert repository.get(running.id).status == "interrupted"
    assert recovered == 1


def test_cancelled_delegation_reaches_terminal_state(tmp_path):
    repository = DelegationRepository(tmp_path / "delegation.sqlite3")
    service = DelegationService(Runner(), repository)
    record = repository.create(SubagentRequest("取消"))

    assert service.cancel(record.id) is True
    assert repository.get(record.id).status == "cancelled"


def test_background_delegation_appends_its_result_to_the_source_session(tmp_path):
    sessions = JsonSessionRepository(tmp_path / "sessions")
    session = sessions.create("主会话")
    sessions.append(session.id, Message(role="user", content="请子代理整理资料"))
    repository = DelegationRepository(tmp_path / "delegation.sqlite3")
    service = DelegationService(Runner(), repository, sessions=sessions)

    delegation_id = service.submit_background(SubagentRequest("整理资料"), session_id=session.id)

    deadline = time.monotonic() + 1
    while repository.get(delegation_id).status not in {"succeeded", "failed"} and time.monotonic() < deadline:
        time.sleep(0.01)

    assert repository.get(delegation_id).session_id == session.id
    assert sessions.get(session.id).messages[-1].content == "子代理任务已完成：整理资料\n\n完成:整理资料"
