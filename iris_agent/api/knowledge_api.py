"""Public knowledge base endpoints."""

from fastapi import APIRouter, HTTPException, Query, status

from iris_agent.api.schemas import KnowledgeCreateRequest
from iris_agent.knowledge.repository import KnowledgeRepositoryError
from iris_agent.knowledge.service import KnowledgeService


def register_knowledge_routes(app, knowledge: KnowledgeService) -> None:
    router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

    def _entry_data(entry) -> dict:
        return {
            "id": entry.id,
            "title": entry.title,
            "category": entry.category,
            "source_url": entry.source_url,
            "source_type": entry.source_type,
            "created_at": entry.created_at,
            "updated_at": entry.updated_at,
        }

    @router.get("")
    def list_knowledge():
        entries = sorted(knowledge.list(), key=lambda e: -e.updated_at)
        return {"entries": [_entry_data(e) for e in entries]}

    @router.post("", status_code=status.HTTP_201_CREATED)
    def add_knowledge(request: KnowledgeCreateRequest):
        try:
            entry = knowledge.add(
                request.title,
                request.content,
                category=request.category,
                source_url=request.source_url,
            )
        except ValueError as exc:
            raise HTTPException(422, detail={"code": "invalid_knowledge", "message": str(exc)}) from None
        return _entry_data(entry)

    @router.get("/search")
    def search_knowledge(
        query: str = Query(..., min_length=1),
        limit: int = Query(5, ge=1, le=20),
    ):
        hits = knowledge.search(query, limit=limit)
        return {"hits": [hit.to_dict() for hit in hits]}

    @router.get("/{entry_id}")
    def get_knowledge(entry_id: str):
        try:
            entry = knowledge.get(entry_id)
        except KnowledgeRepositoryError:
            entry = None
        if entry is None:
            raise HTTPException(404, detail={"code": "knowledge_not_found", "message": "知识不存在"}) from None
        return {**_entry_data(entry), "content": entry.content}

    @router.delete("/{entry_id}")
    def delete_knowledge(entry_id: str):
        try:
            deleted = knowledge.delete(entry_id)
        except KnowledgeRepositoryError:
            deleted = False
        if not deleted:
            raise HTTPException(404, detail={"code": "knowledge_not_found", "message": "知识不存在"}) from None
        return {"ok": True}

    app.include_router(router)
