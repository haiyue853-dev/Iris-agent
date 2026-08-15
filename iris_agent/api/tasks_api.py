"""Public, payload-free endpoints for Agent task timelines and queue control."""

from fastapi import APIRouter, HTTPException, status

from iris_agent.api.schemas import QueueTaskRequest, ToolApprovalRequest
from iris_agent.sessions.base import SessionRepository
from iris_agent.task_center.service import TaskCenterService
from iris_agent.task_queue.repository import QueueLedgerError
from iris_agent.task_queue.service import TaskQueueService


def register_task_routes(
    app,
    task_center: TaskCenterService,
    sessions: SessionRepository,
    task_queue: TaskQueueService | None = None,
) -> None:
    router = APIRouter(prefix="/api/tasks", tags=["tasks"])

    def task_data(task, *, include_events: bool, include_queue_position: bool = True) -> dict:
        data = task.to_dict()
        if any(event.type == "request_queued" for event in task.events):
            data["request_summary"] = "后台任务"
        if not include_events:
            data.pop("events", None)
        if task_queue is not None:
            data["queue_position"] = None
            if include_queue_position:
                try:
                    data["queue_position"] = task_queue.queue_position(task.id)
                except QueueLedgerError:
                    raise _queue_unavailable() from None
        return data

    def get_existing(task_id: str):
        task = task_center.get_task(task_id)
        if task is None:
            raise HTTPException(404, detail={"code": "task_not_found", "message": "任务不存在"})
        return task

    def require_queue() -> TaskQueueService:
        if task_queue is None:
            raise _queue_unavailable()
        return task_queue

    def _queue_unavailable() -> HTTPException:
        return HTTPException(503, detail={"code": "task_queue_unavailable", "message": "任务队列暂不可用"})

    @router.get("")
    def list_tasks(limit: int = 50, session_id: str | None = None):
        tasks = []
        for task in task_center.list_tasks(limit, session_id):
            tasks.append(task_data(task, include_events=False))
        return {"tasks": tasks}

    @router.get("/{task_id}")
    def get_task(task_id: str):
        return task_data(get_existing(task_id), include_events=True)

    @router.post("", status_code=status.HTTP_202_ACCEPTED)
    def submit_task(request: QueueTaskRequest):
        sessions.get(request.session_id)
        try:
            task = require_queue().submit(request.session_id, request.message)
            return task_data(task, include_events=False, include_queue_position=False)
        except QueueLedgerError:
            raise _queue_unavailable() from None

    @router.delete("/{task_id}")
    def cancel_task(task_id: str):
        task = get_existing(task_id)
        if task.status in {"completed", "failed", "stopped"}:
            raise HTTPException(409, detail={"code": "task_not_active", "message": "任务已结束，不能取消"})
        try:
            return task_data(require_queue().cancel(task_id), include_events=True, include_queue_position=False)
        except KeyError:
            raise HTTPException(404, detail={"code": "task_not_found", "message": "任务不存在"}) from None
        except QueueLedgerError:
            raise _queue_unavailable() from None
        except ValueError as exc:
            raise HTTPException(409, detail={"code": "task_not_active", "message": str(exc)}) from exc

    @router.post("/{task_id}/tool-approvals/{call_id}")
    def resolve_task_approval(task_id: str, call_id: str, request: ToolApprovalRequest):
        task = get_existing(task_id)
        if task.status in {"completed", "failed", "stopped"}:
            raise HTTPException(409, detail={"code": "task_not_active", "message": "任务已结束，不能审批"})
        try:
            return task_data(
                require_queue().resolve_approval(task_id, call_id, request.approved),
                include_events=True,
                include_queue_position=False,
            )
        except KeyError:
            raise HTTPException(404, detail={"code": "task_not_found", "message": "任务不存在"}) from None
        except QueueLedgerError:
            raise _queue_unavailable() from None
        except ValueError as exc:
            raise HTTPException(409, detail={"code": "tool_approval_not_found", "message": str(exc)}) from exc

    app.include_router(router)
