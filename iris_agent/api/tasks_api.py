"""Public, payload-free endpoints for Agent task timelines and queue control."""

from fastapi import APIRouter, HTTPException, status

from iris_agent.api.schemas import QueueTaskRequest, ToolApprovalRequest
from iris_agent.sessions.base import SessionRepository
from iris_agent.task_center.service import TaskCenterService
from iris_agent.task_queue.service import TaskQueueService


def register_task_routes(
    app,
    task_center: TaskCenterService,
    sessions: SessionRepository,
    task_queue: TaskQueueService | None = None,
) -> None:
    router = APIRouter(prefix="/api/tasks", tags=["tasks"])

    def task_data(task, *, include_events: bool) -> dict:
        data = task.to_dict()
        if not include_events:
            data.pop("events", None)
        if task_queue is not None:
            data["queue_position"] = task_queue.queue_position(task.id)
        return data

    def get_existing(task_id: str):
        task = task_center.get_task(task_id)
        if task is None:
            raise HTTPException(404, detail={"code": "task_not_found", "message": "任务不存在"})
        return task

    def require_queue() -> TaskQueueService:
        if task_queue is None:
            raise HTTPException(503, detail={"code": "task_queue_unavailable", "message": "任务队列不可用"})
        return task_queue

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
        task = require_queue().submit(request.session_id, request.message)
        return task_data(task, include_events=False)

    @router.delete("/{task_id}")
    def cancel_task(task_id: str):
        task = get_existing(task_id)
        if task.status in {"completed", "failed", "stopped"}:
            raise HTTPException(409, detail={"code": "task_not_active", "message": "任务已结束，不能取消"})
        try:
            return task_data(require_queue().cancel(task_id), include_events=True)
        except KeyError:
            raise HTTPException(404, detail={"code": "task_not_found", "message": "任务不存在"}) from None
        except ValueError as exc:
            raise HTTPException(409, detail={"code": "task_not_active", "message": str(exc)}) from exc

    @router.post("/{task_id}/tool-approvals/{call_id}")
    def resolve_task_approval(task_id: str, call_id: str, request: ToolApprovalRequest):
        task = get_existing(task_id)
        if task.status in {"completed", "failed", "stopped"}:
            raise HTTPException(409, detail={"code": "task_not_active", "message": "任务已结束，不能审批"})
        try:
            return task_data(require_queue().resolve_approval(task_id, call_id, request.approved), include_events=True)
        except KeyError:
            raise HTTPException(404, detail={"code": "task_not_found", "message": "任务不存在"}) from None
        except ValueError as exc:
            raise HTTPException(409, detail={"code": "tool_approval_not_found", "message": str(exc)}) from exc

    app.include_router(router)
