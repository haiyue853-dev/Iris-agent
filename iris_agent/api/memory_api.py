from dataclasses import asdict

from fastapi import HTTPException, status
from pydantic import BaseModel, Field

from iris_agent.memory.service import MemoryService


class CreateMemoryRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4_000)
    session_id: str | None = Field(default=None, max_length=128)
    tags: list[str] = Field(default_factory=list, max_length=12)


def register_memory_routes(app, memory: MemoryService):
    @app.get("/api/memories")
    def list_memories(session_id: str | None = None):
        return {"items": [asdict(item) for item in memory.list(session_id)]}

    @app.get("/api/memories/search")
    def search_memories(query: str, session_id: str | None = None):
        return {"items": [asdict(item) for item in memory.search(query, session_id)]}

    @app.post("/api/memories", status_code=status.HTTP_201_CREATED)
    def create_memory(request: CreateMemoryRequest):
        try:
            return asdict(memory.remember(request.content, request.session_id, tuple(request.tags)))
        except ValueError as exc:
            raise HTTPException(422, detail={"code": "memory_invalid", "message": str(exc)}) from exc

    @app.delete("/api/memories/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_memory(memory_id: str):
        try:
            memory.delete(memory_id)
        except KeyError as exc:
            raise HTTPException(404, detail={"code": "memory_not_found", "message": "Memory was not found"}) from exc
