from urllib.parse import quote

from fastapi import FastAPI, File, Response, UploadFile, status

from iris_agent.attachments.models import AttachmentMetadata
from iris_agent.attachments.service import AttachmentService


_CHUNK_SIZE = 1024 * 1024


def _attachment_data(attachment: AttachmentMetadata) -> dict:
    data = {
        "id": attachment.id,
        "original_name": attachment.original_name,
        "media_type": attachment.media_type,
        "size_bytes": attachment.size_bytes,
        "created_at": attachment.created_at,
        "extraction_status": attachment.extraction_status,
        "text_truncated": attachment.text_truncated,
        "sources": list(attachment.sources),
    }
    if attachment.extraction_message is not None:
        data["extraction_message"] = attachment.extraction_message
    return data


async def _read_upload(file: UploadFile, max_bytes: int) -> bytes:
    content = bytearray()
    while chunk := await file.read(_CHUNK_SIZE):
        content.extend(chunk)
        if len(content) > max_bytes:
            from iris_agent.attachments.errors import AttachmentTooLargeError
            raise AttachmentTooLargeError("附件超过单文件大小限制")
    return bytes(content)


def register_attachment_routes(app: FastAPI, attachments: AttachmentService) -> None:
    @app.post("/api/sessions/{session_id}/attachments", status_code=status.HTTP_201_CREATED)
    async def upload_attachment(session_id: str, file: UploadFile = File(...)):
        attachments.sessions.get(session_id)
        try:
            content = await _read_upload(file, attachments.storage.max_file_bytes)
            attachment = attachments.upload(
                session_id,
                file.filename or "upload",
                content,
                file.content_type or "application/octet-stream",
            )
            return {"attachment": _attachment_data(attachment)}
        finally:
            await file.close()

    @app.get("/api/sessions/{session_id}/attachments")
    def list_attachments(session_id: str):
        return {"attachments": [_attachment_data(item) for item in attachments.list_for_session(session_id)]}

    @app.get("/api/sessions/{session_id}/attachments/{attachment_id}/download")
    def download_attachment(session_id: str, attachment_id: str):
        metadata = attachments.read(session_id, attachment_id)
        handle = attachments.download_path(session_id, attachment_id)
        try:
            content = handle.read_bytes()
        finally:
            handle.close()
        encoded_name = quote(metadata.original_name)
        return Response(
            content=content,
            media_type=metadata.media_type,
            headers={"Content-Disposition": f"attachment; filename=\"download\"; filename*=UTF-8''{encoded_name}"},
        )

    @app.delete("/api/sessions/{session_id}/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_attachment(session_id: str, attachment_id: str):
        attachments.detach_from_session(session_id, attachment_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
