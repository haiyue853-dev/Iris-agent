from fastapi import HTTPException, status
from pydantic import BaseModel, Field

from iris_agent.sessions.base import SessionRepository
from iris_agent.skill_center.errors import SkillDisabledError, SkillNotFoundError
from iris_agent.skill_center.service import SkillCenterService
from iris_agent.task_planning.service import TaskPlanService


class TaskStepRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    instruction: str = Field(min_length=1, max_length=4000)


class CreateTaskPlanRequest(BaseModel):
    session_id: str
    goal: str = Field(min_length=1, max_length=1000)
    steps: list[TaskStepRequest] = Field(min_length=1, max_length=20)
    skill_id: str | None = Field(default=None, max_length=64)


class AutoTaskPlanRequest(BaseModel):
    session_id: str
    goal: str = Field(min_length=1, max_length=1000)
    skill_id: str | None = Field(default=None, max_length=64)


class TaskApprovalRequest(BaseModel):
    approved: bool


class DelegateStepRequest(BaseModel):
    allowed_tools: list[str] = Field(default_factory=list, max_length=20)
    max_tool_rounds: int | None = Field(default=None, ge=1, le=20)


def register_task_planning_routes(app, plans: TaskPlanService, sessions: SessionRepository, skills: SkillCenterService | None = None):
    def instructions(skill_id: str | None) -> str | None:
        if not skill_id:
            return None
        if skills is None:
            raise HTTPException(422, detail={"code": "skill_unavailable", "message": "Skills are unavailable"})
        try:
            return skills.instructions_for(skill_id)
        except SkillNotFoundError as exc:
            raise HTTPException(404, detail={"code": "skill_not_found", "message": "Skill was not found"}) from exc
        except SkillDisabledError as exc:
            raise HTTPException(422, detail={"code": "skill_disabled", "message": "Skill is disabled"}) from exc

    @app.get("/api/task-plans")
    def list_task_plans(session_id: str | None = None):
        return {"items": [plans.data(item) for item in plans.list(session_id)]}

    @app.post("/api/task-plans", status_code=status.HTTP_201_CREATED)
    def create_task_plan(request: CreateTaskPlanRequest):
        sessions.get(request.session_id)
        try:
            instructions(request.skill_id)
            plan = plans.create(request.session_id, request.goal, [item.model_dump() for item in request.steps], request.skill_id)
            return plans.data(plan)
        except ValueError as exc:
            raise HTTPException(422, detail={"code": "task_plan_invalid", "message": str(exc)}) from exc

    @app.post("/api/task-plans/plan", status_code=status.HTTP_201_CREATED)
    def create_automatic_task_plan(request: AutoTaskPlanRequest):
        sessions.get(request.session_id)
        try:
            plan = plans.create_from_goal(request.session_id, request.goal, request.skill_id, instructions(request.skill_id))
            return plans.data(plan)
        except ValueError as exc:
            raise HTTPException(422, detail={"code": "task_plan_generation_invalid", "message": str(exc)}) from exc

    @app.get("/api/task-plans/{plan_id}")
    def get_task_plan(plan_id: str):
        try:
            return plans.data(plans.get(plan_id))
        except KeyError as exc:
            raise HTTPException(404, detail={"code": "task_plan_not_found", "message": "Task plan was not found"}) from exc

    @app.post("/api/task-plans/{plan_id}/run-next")
    def run_task_plan_step(plan_id: str, skill_id: str | None = None):
        try:
            selected_skill_id = skill_id or plans.get(plan_id).skill_id
            plan, events = plans.run_next(plan_id, instructions(selected_skill_id))
            return {"task": plans.data(plan), "events": [event.to_dict() for event in events]}
        except KeyError as exc:
            raise HTTPException(404, detail={"code": "task_plan_not_found", "message": "Task plan was not found"}) from exc
        except ValueError as exc:
            raise HTTPException(409, detail={"code": "task_plan_not_runnable", "message": str(exc)}) from exc

    @app.post("/api/task-plans/{plan_id}/steps/{step_id}/delegate")
    def delegate_task_plan_step(plan_id: str, step_id: str, request: DelegateStepRequest):
        try:
            plan, events = plans.delegate_step(plan_id, step_id, request.allowed_tools, request.max_tool_rounds)
            return {"task": plans.data(plan), "events": [event.to_dict() for event in events]}
        except KeyError as exc:
            raise HTTPException(404, detail={"code": "task_plan_not_found", "message": "Task plan was not found"}) from exc
        except ValueError as exc:
            raise HTTPException(409, detail={"code": "task_step_not_delegable", "message": str(exc)}) from exc

    @app.post("/api/task-plans/{plan_id}/approval")
    def approve_task_plan_step(plan_id: str, request: TaskApprovalRequest):
        try:
            plan = plans.get(plan_id)
            plan, events = plans.resolve_approval(plan_id, request.approved, instructions(plan.skill_id))
            return {"task": plans.data(plan), "events": [event.to_dict() for event in events]}
        except KeyError as exc:
            raise HTTPException(404, detail={"code": "task_plan_not_found", "message": "Task plan was not found"}) from exc
        except ValueError as exc:
            raise HTTPException(409, detail={"code": "task_plan_not_waiting", "message": str(exc)}) from exc
