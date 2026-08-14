from fastapi import HTTPException, status
from pydantic import BaseModel, Field

from iris_agent.sessions.base import SessionRepository
from iris_agent.subagents.service import SubagentService


class CreateSubagentRequest(BaseModel):
    parent_session_id: str
    title: str = Field(min_length=1, max_length=120)
    instruction: str = Field(min_length=1, max_length=4_000)
    allowed_tools: list[str] = Field(default_factory=list, max_length=20)
    max_tool_rounds: int | None = Field(default=None, ge=1, le=20)


class SubagentApprovalRequest(BaseModel):
    approved: bool


def register_subagent_routes(app, subagents: SubagentService, sessions: SessionRepository):
    @app.get("/api/subagents")
    def list_subagents(parent_session_id: str | None = None):
        return {"items": [subagents.data(item) for item in subagents.list(parent_session_id)]}

    @app.post("/api/subagents", status_code=status.HTTP_201_CREATED)
    def create_subagent(request: CreateSubagentRequest):
        sessions.get(request.parent_session_id)
        try:
            return subagents.data(subagents.create(request.parent_session_id, request.title, request.instruction, request.allowed_tools, request.max_tool_rounds))
        except ValueError as exc:
            raise HTTPException(422, detail={"code": "subagent_invalid", "message": str(exc)}) from exc

    @app.get("/api/subagents/{task_id}")
    def get_subagent(task_id: str):
        try:
            return subagents.data(subagents.get(task_id))
        except KeyError as exc:
            raise HTTPException(404, detail={"code": "subagent_not_found", "message": "Subagent was not found"}) from exc

    @app.post("/api/subagents/{task_id}/run")
    def run_subagent(task_id: str):
        try:
            task, events = subagents.run(task_id)
            return {"subagent": subagents.data(task), "events": [event.to_dict() for event in events]}
        except KeyError as exc:
            raise HTTPException(404, detail={"code": "subagent_not_found", "message": "Subagent was not found"}) from exc
        except ValueError as exc:
            raise HTTPException(409, detail={"code": "subagent_not_runnable", "message": str(exc)}) from exc

    @app.post("/api/subagents/{task_id}/approval")
    def resolve_subagent_approval(task_id: str, request: SubagentApprovalRequest):
        try:
            task, events = subagents.resolve_approval(task_id, request.approved)
            return {"subagent": subagents.data(task), "events": [event.to_dict() for event in events]}
        except KeyError as exc:
            raise HTTPException(404, detail={"code": "subagent_not_found", "message": "Subagent was not found"}) from exc
        except ValueError as exc:
            raise HTTPException(409, detail={"code": "subagent_not_waiting", "message": str(exc)}) from exc
