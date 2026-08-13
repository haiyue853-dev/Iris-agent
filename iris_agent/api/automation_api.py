from dataclasses import asdict
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, StrictBool

from iris_agent.automation.service import AutomationService

class CreateTaskRequest(BaseModel): name: str = Field(min_length=1, max_length=80); schedule: str = Field(min_length=1, max_length=80)
class EnabledRequest(BaseModel): enabled: StrictBool

def register_automation_routes(app, automation: AutomationService):
    router = APIRouter(prefix="/api/automation", tags=["automation"])
    @router.get("/tasks")
    def tasks(): return {"tasks": [asdict(item) for item in automation.list_tasks()]}
    @router.post("/tasks", status_code=status.HTTP_201_CREATED)
    def create(request: CreateTaskRequest):
        try: return asdict(automation.create_task(request.name, request.schedule))
        except ValueError as exc: raise HTTPException(422, detail={"code": "automation_validation", "message": str(exc)})
    @router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete(task_id: str):
        try: automation.delete_task(task_id)
        except KeyError: raise HTTPException(404, detail={"code": "automation_not_found", "message": "任务不存在"})
    @router.put("/tasks/{task_id}/enabled")
    def enabled(task_id: str, request: EnabledRequest):
        try: return asdict(automation.set_enabled(task_id, request.enabled))
        except KeyError: raise HTTPException(404, detail={"code": "automation_not_found", "message": "任务不存在"})
    @router.post("/tasks/{task_id}/run")
    def run(task_id: str):
        try: return asdict(automation.run_now(task_id))
        except KeyError: raise HTTPException(404, detail={"code": "automation_not_found", "message": "任务不存在"})
    @router.get("/tasks/{task_id}/executions")
    def executions(task_id: str): return {"executions": [asdict(item) for item in automation.list_executions(task_id)]}
    app.include_router(router)
