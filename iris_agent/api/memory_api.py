"""Public memory management endpoints."""

from fastapi import APIRouter, HTTPException, status

from iris_agent.api.schemas import MemoryCreateRequest
from iris_agent.memory.service import MemoryNotFoundError, MemoryService


def register_memory_routes(app, memory: MemoryService) -> None:
    router = APIRouter(prefix="/api/memory", tags=["memory"])

    def _entry_data(entry) -> dict:
        return {
            "id": entry.id,
            "content": entry.content,
            "category": entry.category,
            "created_at": entry.created_at,
            "updated_at": entry.updated_at,
            "source_session_id": entry.source_session_id,
        }

    @router.get("")
    def list_memories():
        return {"entries": [_entry_data(entry) for entry in memory.list()]}

    @router.post("", status_code=status.HTTP_201_CREATED)
    def add_memory(request: MemoryCreateRequest):
        try:
            entry = memory.add(request.content, request.category)
        except ValueError as exc:
            raise HTTPException(422, detail={"code": "invalid_memory", "message": str(exc)}) from None
        return _entry_data(entry)

    @router.delete("/{entry_id}")
    def delete_memory(entry_id: str):
        try:
            memory.delete(entry_id)
        except MemoryNotFoundError:
            raise HTTPException(404, detail={"code": "memory_not_found", "message": "记忆不存在"}) from None
        return {"ok": True}

    app.include_router(router)
