"""Endpoints for inspecting and cancelling persistent background delegations."""

from fastapi import APIRouter, HTTPException

from iris_agent.subagent.delegation import DelegationRecord, DelegationService, TERMINAL_STATUSES


def register_delegation_routes(app, service: DelegationService) -> None:
    router = APIRouter(prefix="/api/delegations", tags=["delegations"])

    def record_data(record: DelegationRecord, *, include_result: bool = False) -> dict:
        data = {
            "id": record.id,
            "parent_task_id": record.parent_task_id,
            "session_id": record.session_id,
            "status": record.status,
            "goal": record.goal,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        }
        if include_result:
            data["result"] = record.result
            data["error"] = record.error
        return data

    def get_existing(delegation_id: str) -> DelegationRecord:
        try:
            return service.repository.get(delegation_id)
        except KeyError:
            raise HTTPException(
                404,
                detail={"code": "delegation_not_found", "message": "后台委派不存在"},
            ) from None

    @router.get("")
    def list_delegations(limit: int = 50, parent_task_id: str | None = None):
        records = service.repository.list(limit=limit, parent_task_id=parent_task_id)
        return {"delegations": [record_data(record) for record in records]}

    @router.get("/{delegation_id}")
    def get_delegation(delegation_id: str):
        return record_data(get_existing(delegation_id), include_result=True)

    @router.delete("/{delegation_id}")
    def cancel_delegation(delegation_id: str):
        record = get_existing(delegation_id)
        if record.status in TERMINAL_STATUSES or not service.cancel(delegation_id):
            raise HTTPException(
                409,
                detail={"code": "delegation_not_active", "message": "后台委派已结束，不能取消"},
            )
        return record_data(service.repository.get(delegation_id), include_result=True)

    app.include_router(router)
