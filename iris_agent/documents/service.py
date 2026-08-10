"""文档工作台的存储与本地提取编排。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from iris_agent.documents.errors import DocumentExtractFailedError
from iris_agent.documents.extraction import LocalDocumentExtractor
from iris_agent.documents.models import DocumentRecord
from iris_agent.documents.storage import DocumentRepository


@dataclass(slots=True)
class DocumentService:
    root: Path
    max_file_bytes: int = 10_000_000
    max_total_bytes: int = 50_000_000
    max_count: int = 50
    max_text_chars: int = 50_000
    repository: DocumentRepository = field(init=False)
    extractor: LocalDocumentExtractor = field(init=False)

    def __post_init__(self) -> None:
        self.repository = DocumentRepository(
            self.root,
            max_file_bytes=self.max_file_bytes,
            max_total_bytes=self.max_total_bytes,
            max_count=self.max_count,
            max_text_chars=self.max_text_chars,
        )
        self.extractor = LocalDocumentExtractor(self.max_text_chars)

    def upload(self, original_name: str, content: bytes, media_type: str) -> DocumentRecord:
        document = self.repository.save(original_name, content, media_type)
        try:
            extraction = self.extractor.extract(self.repository.file_for(document.id))
        except DocumentExtractFailedError:
            return self.repository.update_extraction(document.id, None, message="无法提取文档文本")
        return self.repository.update_extraction(document.id, extraction)

    def list(self) -> list[DocumentRecord]:
        return self.repository.list()

    def get(self, document_id: str) -> DocumentRecord:
        return self.repository.get(document_id)

    def read_text(self, document_id: str) -> str:
        return self.repository.read_text(document_id)

    def delete(self, document_id: str) -> None:
        self.repository.delete(document_id)
