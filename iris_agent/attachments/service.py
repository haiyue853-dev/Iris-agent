from __future__ import annotations

from iris_agent.core.models import Message
from iris_agent.sessions.base import SessionRepository

from .errors import AttachmentAccessError, AttachmentExtractError, AttachmentNotFoundError
from .extraction import LocalAttachmentExtractor
from .models import AttachmentMetadata
from .storage import AttachmentFile, AttachmentStorage


class AttachmentService:
    def __init__(self, storage: AttachmentStorage, sessions: SessionRepository, extractor: LocalAttachmentExtractor):
        self.storage = storage
        self.sessions = sessions
        self.extractor = extractor

    def upload(self, session_id: str, filename: str, content: bytes, media_type: str) -> AttachmentMetadata:
        self.sessions.get(session_id)
        metadata = self.storage.save(session_id, filename, content, media_type)
        try:
            attachment = self.storage.open(session_id, metadata.id)
            try:
                extracted = self.extractor.extract(attachment)
            finally:
                attachment.close()
            sources = tuple(source.location or source.file_name for source in extracted.sources)
            return self.storage.update_extraction_result(
                session_id, metadata.id, extraction_status="ready", extracted_text=extracted.text,
                text_truncated=extracted.truncated, sources=sources,
            )
        except AttachmentExtractError as exc:
            return self.storage.update_extraction_result(
                session_id, metadata.id, extraction_status="failed", extraction_message="无法提取附件文本",
            )

    def attach_to_session(self, session_id: str, attachment_ids: list[str]) -> list[AttachmentMetadata]:
        attachments = [self._owned(session_id, attachment_id) for attachment_id in attachment_ids]
        if len({item.id for item in attachments}) != len(attachments):
            raise AttachmentAccessError("附件不能重复关联")
        self.sessions.append(session_id, Message(role="user", attachment_ids=[item.id for item in attachments]))
        return attachments

    def detach_from_session(self, session_id: str, attachment_id: str) -> None:
        self._owned(session_id, attachment_id)
        session = self.sessions.get(session_id)
        for message in session.messages:
            if attachment_id in message.attachment_ids:
                message.attachment_ids.remove(attachment_id)
        self.sessions.save(session)
        self.storage.delete(session_id, attachment_id)

    def list_for_session(self, session_id: str) -> list[AttachmentMetadata]:
        self.sessions.get(session_id)
        return self.storage.list(session_id)

    def read(self, session_id: str, attachment_id: str) -> AttachmentMetadata:
        return self._owned(session_id, attachment_id)

    def download_path(self, session_id: str, attachment_id: str) -> AttachmentFile:
        self._owned(session_id, attachment_id)
        return self.storage.open(session_id, attachment_id)

    def cleanup_expired(self) -> None:
        attached = {
            attachment_id
            for session in self.sessions.list()
            for message in session.messages
            for attachment_id in message.attachment_ids
        }
        self.storage.cleanup_expired(lambda metadata: metadata.id not in attached)

    def delete_for_session(self, session_id: str) -> None:
        self.sessions.get(session_id)
        for metadata in self.storage.list(session_id):
            self.storage.delete(session_id, metadata.id)

    def _owned(self, session_id: str, attachment_id: str) -> AttachmentMetadata:
        self.sessions.get(session_id)
        for metadata in self.storage.list(session_id):
            if metadata.id == attachment_id:
                return metadata
        if self.storage.scope_for(attachment_id) is not None:
            raise AttachmentAccessError("无权访问其他会话的附件")
        raise AttachmentNotFoundError("附件不存在")
