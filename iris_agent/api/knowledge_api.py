"""Public knowledge base endpoints."""

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse

from iris_agent.api.schemas import KnowledgeBadCaseRequest, KnowledgeChunkUpdateRequest, KnowledgeCollectionCreateRequest, KnowledgeCollectionRenameRequest, KnowledgeCollectionRetrievalConfigUpdateRequest, KnowledgeCreateRequest, KnowledgeDocumentMoveRequest, KnowledgeEvaluationGateUpdateRequest, KnowledgeEvaluationGenerateRequest, KnowledgeEvaluationRequest, KnowledgeEvaluationSeedRequest, KnowledgeGraphEntityEditRequest, KnowledgeGraphRelationEditRequest, KnowledgeGraphSummaryRequest, KnowledgeImportRequest, KnowledgeRuntimeTestRequest, KnowledgeRuntimeUpdateRequest, KnowledgeUpdateRequest, KnowledgeUploadRequest
from iris_agent.knowledge.repository import KnowledgeRepositoryError


def register_knowledge_routes(app, knowledge) -> None:
    router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

    def _document_data(document) -> dict: return document.to_dict()

    @router.get("")
    def list_knowledge(collection_id: str | None = Query(default=None, max_length=50)):
        if not hasattr(knowledge, "list_documents"):
            entries = sorted(knowledge.list(), key=lambda item: -item.updated_at)
            return {"entries": [{"id": item.id, "title": item.title, "category": item.category, "source_url": item.source_url, "source_type": item.source_type, "created_at": item.created_at, "updated_at": item.updated_at} for item in entries]}
        return {"documents": sorted((_document_data(item) for item in knowledge.list_documents(collection_id)), key=lambda item: -item["updated_at"])}

    @router.get("/collections")
    def list_collections():
        return {"collections": [item.to_dict() for item in knowledge.list_collections()] if hasattr(knowledge, "list_collections") else []}

    @router.post("/collections", status_code=status.HTTP_201_CREATED)
    def create_collection(request: KnowledgeCollectionCreateRequest):
        try:
            return knowledge.create_collection(request.name, request.description).to_dict()
        except ValueError as exc:
            raise HTTPException(422, detail={"code": "invalid_collection", "message": str(exc)}) from None

    @router.delete("/collections/{collection_id}")
    def delete_collection(collection_id: str):
        try:
            if not knowledge.delete_collection(collection_id):
                raise HTTPException(404, detail={"code": "collection_not_found", "message": "知识库不存在"})
        except ValueError as exc:
            raise HTTPException(422, detail={"code": "invalid_collection", "message": str(exc)}) from None
        return {"ok": True}

    @router.patch("/collections/{collection_id}")
    def rename_collection(collection_id: str, request: KnowledgeCollectionRenameRequest):
        try:
            return knowledge.rename_collection(collection_id, request.name).to_dict()
        except ValueError as exc:
            raise HTTPException(422, detail={"code": "invalid_collection", "message": str(exc)}) from None

    @router.get("/collections/{collection_id}/retrieval-config")
    def get_collection_retrieval_config(collection_id: str):
        try:
            return {"config": knowledge.collection_retrieval_config(collection_id)}
        except ValueError as exc:
            raise HTTPException(422, detail={"code": "invalid_collection", "message": str(exc)}) from None

    @router.patch("/collections/{collection_id}/retrieval-config")
    def update_collection_retrieval_config(collection_id: str, request: KnowledgeCollectionRetrievalConfigUpdateRequest):
        try:
            return {"config": knowledge.update_collection_retrieval_config(collection_id, request.model_dump(exclude_none=True))}
        except ValueError as exc:
            raise HTTPException(422, detail={"code": "invalid_collection", "message": str(exc)}) from None

    @router.post("", status_code=status.HTTP_201_CREATED)
    def add_knowledge(request: KnowledgeCreateRequest):
        try:
            if not hasattr(knowledge, "add_text"):
                entry = knowledge.add(request.title, request.content, category=request.category, source_url=request.source_url)
                return {"id": entry.id, "title": entry.title, "category": entry.category, "source_url": entry.source_url, "source_type": entry.source_type, "created_at": entry.created_at, "updated_at": entry.updated_at}
            entry = knowledge.enqueue_text(request.title, request.content, source_type="scrape" if request.source_url else "manual", collection_id=request.collection_id)
        except ValueError as exc:
            raise HTTPException(422, detail={"code": "invalid_knowledge", "message": str(exc)}) from None
        return _document_data(entry)

    @router.post("/upload", status_code=status.HTTP_201_CREATED)
    def upload_knowledge(request: KnowledgeUploadRequest):
        try:
            import base64
            content = base64.b64decode(request.content_base64, validate=True)
            document = knowledge.enqueue_upload(request.title, request.original_name, content, request.media_type, collection_id=request.collection_id)
        except (ValueError, base64.binascii.Error) as exc:
            raise HTTPException(422, detail={"code": "invalid_knowledge", "message": str(exc)}) from None
        return _document_data(document)

    @router.get("/search")
    def search_knowledge(
        query: str = Query(..., min_length=1),
        limit: int = Query(5, ge=1, le=20),
        collection_id: str | None = Query(default=None, max_length=50),
    ):
        hits = (knowledge.search(query, limit=limit, collection_id=collection_id)
                if hasattr(knowledge, "list_documents")
                else knowledge.search(query, limit=limit))
        return {"hits": [hit.to_dict() for hit in hits]}

    @router.get("/search/debug")
    def debug_knowledge_search(
        query: str = Query(..., min_length=1, max_length=2000),
        limit: int = Query(10, ge=1, le=20),
        collection_id: str | None = Query(default=None, max_length=50),
    ):
        if not hasattr(knowledge, "debug_search"):
            raise HTTPException(501, detail={"code": "debug_search_not_supported", "message": "当前知识库不支持检索调试"})
        try:
            return knowledge.debug_search(query, limit=limit, collection_id=collection_id)
        except ValueError as exc:
            raise HTTPException(422, detail={"code": "invalid_debug_search", "message": str(exc)}) from None

    @router.get("/topics")
    def list_topics(collection_id: str | None = Query(default=None, max_length=50)):
        return {"topics": knowledge.topics(collection_id) if hasattr(knowledge, "topics") else []}

    @router.get("/export")
    def export_knowledge(collection_id: str | None = Query(default=None, max_length=50)):
        return knowledge.export_collection(collection_id) if hasattr(knowledge, "export_collection") else {"format": "iris-knowledge-export", "version": 1, "documents": [], "graph": {"nodes": [], "edges": []}}

    @router.get("/stats")
    def knowledge_stats(collection_id: str | None = Query(default=None, max_length=50)):
        return knowledge.collection_stats(collection_id) if hasattr(knowledge, "collection_stats") else {"documents": 0, "ready": 0, "indexing": 0, "failed": 0, "chunks": 0, "nodes": 0, "edges": 0}

    @router.get("/runtime")
    def get_knowledge_runtime():
        return knowledge.model_runtime() if hasattr(knowledge, "model_runtime") else {"config": {}, "components": []}

    @router.patch("/runtime")
    def update_knowledge_runtime(request: KnowledgeRuntimeUpdateRequest):
        if not hasattr(knowledge, "update_model_runtime"):
            raise HTTPException(501, detail={"code": "runtime_not_supported", "message": "当前知识库不支持运行配置"})
        try:
            return knowledge.update_model_runtime(request.model_dump(exclude_none=True))
        except ValueError as exc:
            raise HTTPException(422, detail={"code": "invalid_runtime", "message": str(exc)}) from None

    @router.post("/runtime/test")
    def test_knowledge_runtime(request: KnowledgeRuntimeTestRequest):
        if not hasattr(knowledge, "test_model_runtime"):
            raise HTTPException(501, detail={"code": "runtime_not_supported", "message": "当前知识库不支持连接测试"})
        return knowledge.test_model_runtime(request.component)

    @router.get("/index-progress")
    def get_knowledge_index_progress():
        return knowledge.index_progress() if hasattr(knowledge, "index_progress") else {"items": []}

    @router.post("/import")
    def import_knowledge(request: KnowledgeImportRequest):
        try:
            return {"imported": knowledge.import_backup(request.backup, request.collection_id)}
        except ValueError as exc:
            raise HTTPException(422, detail={"code": "invalid_backup", "message": str(exc)}) from None

    @router.post("/evaluate")
    def evaluate_knowledge(request: KnowledgeEvaluationRequest):
        return knowledge.evaluate_queries(request.questions, request.collection_id, request.cases, request.k_values) if hasattr(knowledge, "evaluate_queries") else {"total": 0, "hit_count": 0, "results": []}

    @router.post("/evaluate/validate")
    def validate_knowledge_evaluation(request: KnowledgeEvaluationSeedRequest):
        return knowledge.validate_evaluation_cases(request.cases, request.collection_id) if hasattr(knowledge, "validate_evaluation_cases") else {"summary": {"total": len(request.cases)}, "rows": []}

    @router.post("/evaluate/generate")
    def generate_knowledge_evaluation(request: KnowledgeEvaluationGenerateRequest):
        return knowledge.generate_evaluation_cases(request.collection_id) if hasattr(knowledge, "generate_evaluation_cases") else {"cases": [], "generated_by": "none"}

    @router.get("/evaluate/gate")
    def get_evaluation_gate(collection_id: str = Query(..., min_length=1, max_length=50)):
        try:
            return {"thresholds": knowledge.evaluation_gate(collection_id)} if hasattr(knowledge, "evaluation_gate") else {"thresholds": {}}
        except ValueError as exc:
            raise HTTPException(422, detail={"code": "invalid_evaluation_gate", "message": str(exc)}) from None

    @router.patch("/evaluate/gate")
    def update_evaluation_gate(request: KnowledgeEvaluationGateUpdateRequest, collection_id: str = Query(..., min_length=1, max_length=50)):
        try:
            return {"thresholds": knowledge.update_evaluation_gate(collection_id, request.model_dump())}
        except ValueError as exc:
            raise HTTPException(422, detail={"code": "invalid_evaluation_gate", "message": str(exc)}) from None

    @router.get("/evaluate/history")
    def get_evaluation_history(collection_id: str = Query(..., min_length=1, max_length=50)):
        try:
            return knowledge.evaluation_history(collection_id) if hasattr(knowledge, "evaluation_history") else {"collection_id": collection_id, "items": []}
        except ValueError as exc:
            raise HTTPException(422, detail={"code": "invalid_evaluation_history", "message": str(exc)}) from None

    @router.post("/evaluate/history/{history_id}/restore")
    def restore_evaluation_history_config(history_id: str, collection_id: str = Query(..., min_length=1, max_length=50)):
        try:
            if not hasattr(knowledge, "restore_evaluation_config"):
                raise HTTPException(501, detail={"code": "evaluation_history_not_supported", "message": "当前知识库不支持评测历史"})
            return {"config": knowledge.restore_evaluation_config(collection_id, history_id)}
        except ValueError as exc:
            raise HTTPException(422, detail={"code": "invalid_evaluation_history", "message": str(exc)}) from None

    @router.get("/evaluate/seed")
    def get_evaluation_seed(collection_id: str | None = Query(default=None, max_length=50)):
        return knowledge.load_evaluation_cases(collection_id) if hasattr(knowledge, "load_evaluation_cases") else {"cases": []}

    @router.post("/evaluate/seed")
    def save_evaluation_seed(request: KnowledgeEvaluationSeedRequest):
        try:
            return knowledge.save_evaluation_cases(request.cases, request.collection_id)
        except ValueError as exc:
            raise HTTPException(422, detail={"code": "invalid_evaluation_seed", "message": str(exc)}) from None

    @router.get("/bad-cases")
    def list_bad_cases(limit: int = Query(100, ge=1, le=500)):
        return {"cases": knowledge.list_bad_cases(limit) if hasattr(knowledge, "list_bad_cases") else []}

    @router.post("/bad-cases")
    def record_bad_case(request: KnowledgeBadCaseRequest):
        try:
            return knowledge.record_bad_case(request.model_dump())
        except ValueError as exc:
            raise HTTPException(422, detail={"code": "invalid_bad_case", "message": str(exc)}) from None

    @router.post("/bad-cases/{case_id}/replay")
    def replay_bad_case(case_id: str):
        try:
            return knowledge.replay_bad_case(case_id)
        except ValueError as exc:
            raise HTTPException(404, detail={"code": "bad_case_not_found", "message": str(exc)}) from None

    @router.get("/duplicates")
    def duplicate_knowledge(collection_id: str | None = Query(default=None, max_length=50)):
        return {"suggestions": knowledge.duplicate_suggestions(collection_id) if hasattr(knowledge, "duplicate_suggestions") else []}

    @router.get("/graph")
    def knowledge_graph(topic: str | None = Query(default=None, max_length=120), collection_id: str | None = Query(default=None, max_length=50)):
        if not hasattr(knowledge, "graph"):
            return {"nodes": [], "edges": []}
        return knowledge.graph(topic, collection_id)

    @router.post("/graph/summarize")
    def summarize_knowledge_graph(request: KnowledgeGraphSummaryRequest):
        try:
            if request.kind == "entity":
                return knowledge.summarize_graph_entity(request.node_id or "", request.collection_id)
            return knowledge.summarize_graph_relation(request.source_id or "", request.target_id or "", request.relation or "", request.document_id, request.collection_id)
        except ValueError as exc:
            raise HTTPException(422, detail={"code": "invalid_graph_target", "message": str(exc)}) from None
        except Exception as exc:
            raise HTTPException(503, detail={"code": "graph_summary_unavailable", "message": f"图谱摘要暂不可用：{str(exc)[:120]}"}) from None

    @router.get("/graph/audit")
    def audit_knowledge_graph(collection_id: str | None = Query(default=None, max_length=50)):
        return knowledge.graph_audit(collection_id)

    @router.patch("/graph/relation")
    def update_knowledge_graph_relation(request: KnowledgeGraphRelationEditRequest):
        if not request.new_relation:
            raise HTTPException(422, detail={"code": "invalid_graph_relation", "message": "new_relation is required"})
        return {"updated": knowledge.update_graph_relation(request.source_id, request.target_id, request.relation, request.new_relation, request.document_id)}

    @router.delete("/graph/relation")
    def delete_knowledge_graph_relation(request: KnowledgeGraphRelationEditRequest):
        return {"deleted": knowledge.delete_graph_relation(request.source_id, request.target_id, request.relation, request.document_id)}

    @router.patch("/graph/entity")
    def rename_knowledge_graph_entity(request: KnowledgeGraphEntityEditRequest):
        if not request.label:
            raise HTTPException(422, detail={"code": "invalid_graph_entity", "message": "label is required"})
        return {"updated": knowledge.rename_graph_entity(request.node_id, request.label, request.collection_id)}

    @router.delete("/graph/entity")
    def delete_knowledge_graph_entity(request: KnowledgeGraphEntityEditRequest):
        return {"deleted": knowledge.delete_graph_entity(request.node_id, request.collection_id)}

    @router.get("/{entry_id}/mindmap")
    def get_document_mindmap(entry_id: str):
        if not hasattr(knowledge, "document_mindmap"):
            raise HTTPException(404, detail={"code": "mindmap_not_found", "message": "这份资料还没有思维导图"})
        try:
            return knowledge.document_mindmap(entry_id)
        except ValueError as exc:
            raise HTTPException(404, detail={"code": "knowledge_not_found", "message": str(exc)}) from None

    @router.get("/{entry_id}/source")
    def get_document_source(entry_id: str):
        if not hasattr(knowledge, "document_source_path"):
            raise HTTPException(404, detail={"code": "source_not_found", "message": "该资料没有本地原文件"})
        try:
            document = knowledge.get_document(entry_id)
            source_path = knowledge.document_source_path(entry_id)
        except ValueError:
            document, source_path = None, None
        if document is None or source_path is None or not source_path.is_file():
            raise HTTPException(404, detail={"code": "source_not_found", "message": "该资料没有本地原文件"})
        return FileResponse(
            source_path,
            media_type=document.media_type or "application/octet-stream",
            filename=document.original_name or source_path.name,
            content_disposition_type="inline",
        )

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
        return knowledge.document_detail(entry_id)

    @router.post("/reindex")
    def reindex_all_knowledge(collection_id: str | None = Query(default=None, max_length=50)):
        try:
            return {"queued": knowledge.reindex_all(collection_id)}
        except ValueError as exc:
            raise HTTPException(422, detail={"code": "invalid_knowledge", "message": str(exc)}) from None

    @router.post("/graph/merge")
    def merge_graph_entities(collection_id: str | None = Query(default=None, max_length=50)):
        try:
            return {"merged": knowledge.merge_graph_entities(collection_id)}
        except ValueError as exc:
            raise HTTPException(422, detail={"code": "invalid_knowledge", "message": str(exc)}) from None
        except Exception as exc:
            raise HTTPException(503, detail={"code": "graph_merge_unavailable", "message": f"图谱合并暂不可用：{str(exc)[:120]}"}) from None

    @router.post("/{entry_id}/reindex")
    def reindex_knowledge(entry_id: str, vectors_only: bool = Query(default=False)):
        try:
            return _document_data(knowledge.reindex_document(entry_id, vectors_only=vectors_only))
        except ValueError as exc:
            if "unknown" in str(exc):
                raise HTTPException(404, detail={"code": "knowledge_not_found", "message": "知识不存在"}) from None
            raise HTTPException(422, detail={"code": "invalid_knowledge", "message": str(exc)}) from None

    def _require_document_chunk(entry_id: str, chunk_id: str) -> None:
        detail = knowledge.document_detail(entry_id)
        if detail is None or not any(item.get("id") == chunk_id for item in detail.get("chunks", [])):
            raise HTTPException(404, detail={"code": "chunk_not_found", "message": "知识切片不存在"})

    @router.patch("/{entry_id}/chunks/{chunk_id}")
    def update_knowledge_chunk(entry_id: str, chunk_id: str, request: KnowledgeChunkUpdateRequest):
        _require_document_chunk(entry_id, chunk_id)
        try:
            return knowledge.update_chunk(chunk_id, request.content, request.location)
        except ValueError as exc:
            raise HTTPException(422, detail={"code": "invalid_chunk", "message": str(exc)}) from None

    @router.get("/{entry_id}/chunks/{chunk_id}/revisions")
    def get_knowledge_chunk_revisions(entry_id: str, chunk_id: str, limit: int = Query(default=20, ge=1, le=100)):
        _require_document_chunk(entry_id, chunk_id)
        return knowledge.chunk_revisions(chunk_id, limit)

    @router.post("/{entry_id}/chunks/{chunk_id}/revisions/{revision_id}/restore")
    def restore_knowledge_chunk_revision(entry_id: str, chunk_id: str, revision_id: str):
        _require_document_chunk(entry_id, chunk_id)
        try:
            return knowledge.restore_chunk_revision(chunk_id, revision_id)
        except ValueError as exc:
            message = str(exc)
            raise HTTPException(404 if "unknown" in message else 422, detail={"code": "invalid_chunk_revision", "message": message}) from None

    @router.patch("/{entry_id}/collection")
    def move_knowledge(entry_id: str, request: KnowledgeDocumentMoveRequest):
        try:
            return _document_data(knowledge.move_document(entry_id, request.collection_id))
        except ValueError as exc:
            message = str(exc)
            raise HTTPException(404 if "不存在" in message else 422, detail={"code": "invalid_knowledge", "message": message}) from None

    @router.patch("/{entry_id}")
    def update_knowledge(entry_id: str, request: KnowledgeUpdateRequest):
        try:
            return _document_data(knowledge.update_text_document(entry_id, request.title, request.content))
        except ValueError as exc:
            message = str(exc)
            raise HTTPException(404 if "不存在" in message else 422, detail={"code": "invalid_knowledge", "message": message}) from None

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
