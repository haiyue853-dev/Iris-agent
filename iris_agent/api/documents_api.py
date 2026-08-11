"""HTTP routes for the local-first document workbench."""

from urllib.parse import quote

from fastapi import File, Response, UploadFile, status

from iris_agent.api.documents_schemas import GenerateDocumentDraftRequest, SaveDocumentDraftRequest
from iris_agent.documents.models import DocumentDraft, DocumentRecord


def _document_data(document: DocumentRecord) -> dict:
    data = {
        "id": document.id,
        "original_name": document.original_name,
        "suffix": document.suffix,
        "media_type": document.media_type,
        "size_bytes": document.size_bytes,
        "created_at": document.created_at,
        "extraction_status": document.extraction_status,
        "text_truncated": document.text_truncated,
        "sources": [
            {"file_name": source.file_name, "location": source.location}
            for source in document.sources
        ],
    }
    if document.extraction_message is not None:
        data["extraction_message"] = document.extraction_message
    return data


def _draft_data(draft: DocumentDraft) -> dict:
    return {
        "id": draft.id,
        "title": draft.title,
        "template": draft.template,
        "document_ids": list(draft.document_ids),
        "instructions": draft.instructions,
        "markdown": draft.markdown,
        "citations": [
            {"document_id": citation.document_id, "location": citation.location}
            for citation in draft.citations
        ],
        "revision": draft.revision,
        "created_at": draft.created_at,
        "updated_at": draft.updated_at,
    }


def register_documents_routes(app, documents) -> None:
    @app.post("/api/documents", status_code=status.HTTP_201_CREATED)
    async def upload_document(file: UploadFile = File(...)):
        content = await file.read()
        return _document_data(documents.upload(file.filename or "upload", content, file.content_type or ""))

    @app.get("/api/documents")
    def list_documents():
        return {"documents": [_document_data(item) for item in documents.list()]}

    @app.post("/api/documents/drafts/generate", status_code=status.HTTP_201_CREATED)
    def generate_draft(request: GenerateDocumentDraftRequest):
        return _draft_data(documents.generate_draft(request.template, request.document_ids, request.instructions))

    @app.get("/api/documents/drafts")
    def list_drafts():
        return {"drafts": [_draft_data(item) for item in documents.list_drafts()]}

    @app.get("/api/documents/drafts/{draft_id}")
    def get_draft(draft_id: str):
        return _draft_data(documents.get_draft(draft_id))

    @app.put("/api/documents/drafts/{draft_id}")
    def save_draft(draft_id: str, request: SaveDocumentDraftRequest):
        return _draft_data(
            documents.save_draft(draft_id, request.title, request.markdown, request.expected_revision)
        )

    @app.get("/api/documents/drafts/{draft_id}/export")
    def export_draft(draft_id: str, format: str):
        exported = documents.export_draft(draft_id, format)
        filename = quote(exported.filename)
        return Response(
            content=exported.content,
            media_type=exported.media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/api/documents/{document_id}")
    def get_document(document_id: str):
        return _document_data(documents.get(document_id))

    @app.delete("/api/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_document(document_id: str):
        documents.delete(document_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
