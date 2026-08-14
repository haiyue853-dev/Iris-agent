"""Read-only endpoints for safe Agent task timelines."""

from fastapi import APIRouter, HTTPException

from iris_agent.task_center.service import TaskCenterService


def register_task_routes(app, task_center: TaskCenterService) -> None:
    router = APIRouter(prefix="/api/tasks", tags=["tasks"])

    @router.get("")
    def list_tasks(limit: int = 50, session_id: str | None = None):
        tasks = []
        for task in task_center.list_tasks(limit, session_id):
            data = task.to_dict()
            data.pop("events", None)
            tasks.append(data)
        return {"tasks": tasks}

    @router.get("/{task_id}")
    def get_task(task_id: str):
        task = task_center.get_task(task_id)
        if task is None:
            raise HTTPException(404, detail={"code": "task_not_found", "message": "任务不存在"})
        return task.to_dict()

    app.include_router(router)
