from iris_agent.attachments.errors import AttachmentAccessError, AttachmentExtractError, AttachmentNotFoundError
from iris_agent.attachments.service import AttachmentService
from iris_agent.tools.base import Tool, ToolInvocationError


def build_read_attachment_tool(service: AttachmentService, session_id: str) -> Tool:
    def read_attachment(attachment_id: str, max_chars: int | None = None) -> dict[str, object]:
        if not isinstance(attachment_id, str) or not attachment_id.strip() or "/" in attachment_id or "\\" in attachment_id or attachment_id in {".", ".."}:
            raise ToolInvocationError("invalid_attachment_id", "attachment_id 必须是附件 ID")
        try:
            metadata = service.read(session_id, attachment_id)
        except AttachmentAccessError as exc:
            raise ToolInvocationError("attachment_access_denied", str(exc)) from exc
        except AttachmentNotFoundError as exc:
            raise ToolInvocationError("attachment_not_found", str(exc)) from exc
        if metadata.extraction_status != "ready":
            code = "attachment_extract_error" if metadata.extraction_status == "failed" else "attachment_not_ready"
            raise ToolInvocationError(code, metadata.extraction_message or "附件文本尚未准备好")
        text = metadata.extracted_text or ""
        truncated = metadata.text_truncated
        if max_chars is not None:
            if max_chars < 1:
                raise ToolInvocationError("invalid_max_chars", "max_chars 必须为正整数")
            if len(text) > max_chars:
                text, truncated = text[:max_chars], True
        return {"name": metadata.original_name, "text": text, "truncated": truncated, "sources": list(metadata.sources)}

    return Tool(
        "read_attachment",
        "读取当前会话附件的已提取文本。只能使用附件 ID，不能读取任意路径。",
        {"type": "object", "properties": {"attachment_id": {"type": "string"}, "max_chars": {"type": "integer"}}, "required": ["attachment_id"], "additionalProperties": False},
        read_attachment,
    )
