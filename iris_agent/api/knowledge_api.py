"""Public knowledge base endpoints."""

from fastapi import APIRouter, HTTPException, Query, status

from iris_agent.api.schemas import KnowledgeCreateRequest, KnowledgeUploadRequest
from iris_agent.knowledge.repository import KnowledgeRepositoryError


def register_knowledge_routes(app, knowledge) -> None:
    router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

    def _document_data(document) -> dict: return document.to_dict()

    @router.get("")
    def list_knowledge():
        if not hasattr(knowledge, "list_documents"):
            entries = sorted(knowledge.list(), key=lambda item: -item.updated_at)
            return {"entries": [{"id": item.id, "title": item.title, "category": item.category, "source_url": item.source_url, "source_type": item.source_type, "created_at": item.created_at, "updated_at": item.updated_at} for item in entries]}
        return {"documents": sorted((_document_data(item) for item in knowledge.list_documents()), key=lambda item: -item["updated_at"])}

    @router.post("", status_code=status.HTTP_201_CREATED)
    def add_knowledge(request: KnowledgeCreateRequest):
        try:
            if not hasattr(knowledge, "add_text"):
                entry = knowledge.add(request.title, request.content, category=request.category, source_url=request.source_url)
                return {"id": entry.id, "title": entry.title, "category": entry.category, "source_url": entry.source_url, "source_type": entry.source_type, "created_at": entry.created_at, "updated_at": entry.updated_at}
            entry = knowledge.add_text(request.title, request.content, source_type="scrape" if request.source_url else "manual")
        except ValueError as exc:
            raise HTTPException(422, detail={"code": "invalid_knowledge", "message": str(exc)}) from None
        return _document_data(entry)

    @router.post("/upload", status_code=status.HTTP_201_CREATED)
    def upload_knowledge(request: KnowledgeUploadRequest):
        try:
            import base64
            content = base64.b64decode(request.content_base64, validate=True)
            document = knowledge.add_upload(request.title, request.original_name, content, request.media_type)
        except (ValueError, base64.binascii.Error) as exc:
            raise HTTPException(422, detail={"code": "invalid_knowledge", "message": str(exc)}) from None
        return _document_data(document)

    @router.get("/search")
    def search_knowledge(
        query: str = Query(..., min_length=1),
        limit: int = Query(5, ge=1, le=20),
    ):
        hits = knowledge.search(query, limit=limit)
        return {"hits": [hit.to_dict() for hit in hits]}

    @router.get("/topics")
    def list_topics():
        return {"topics": knowledge.topics() if hasattr(knowledge, "topics") else []}

    @router.get("/graph")
    def knowledge_graph(topic: str | None = Query(default=None, max_length=120)):
        if not hasattr(knowledge, "graph"):
            return {"nodes": [], "edges": []}
        return knowledge.graph(topic)

    @router.get("/{entry_id}")
    def get_knowledge(entry_id: str):
        if not hasattr(knowledge, "get_document"):
            try: entry = knowledge.get(entry_id)
            except KnowledgeRepositoryError: entry = None
            if entry is None: raise HTTPException(404, detail={"code": "knowledge_not_found", "message": "知识不存在"})
            return entry.to_dict()
        entry = knowledge.get_document(entry_id)
        if entry is None:
            raise HTTPException(404, detail={"code": "knowledge_not_found", "message": "知识不存在"}) from None
        return {**_document_data(entry), "chunks": [item.to_dict() for item in knowledge.repository.chunks_for_document(entry_id)]}

    @router.delete("/{entry_id}")
    def delete_knowledge(entry_id: str):
        if not hasattr(knowledge, "delete_document"):
            try: deleted = knowledge.delete(entry_id)
            except KnowledgeRepositoryError: deleted = False
            if not deleted: raise HTTPException(404, detail={"code": "knowledge_not_found", "message": "知识不存在"})
            return {"ok": True}
        deleted = knowledge.delete_document(entry_id)
        if not deleted:
            raise HTTPException(404, detail={"code": "knowledge_not_found", "message": "知识不存在"}) from None
        return {"ok": True}

    app.include_router(router)
