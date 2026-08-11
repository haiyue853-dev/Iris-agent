"""可安全暴露给文档工作台 API 的领域错误。"""

from iris_agent.core.errors import IrisError


class DocumentError(IrisError):
    code = "document_error"

    def __init__(self, message: str, *, code: str | None = None):
        if code is not None:
            self.code = code
        super().__init__(message)


class DocumentValidationError(DocumentError):
    code = "document_validation_error"


class DocumentInvalidTypeError(DocumentError):
    code = "document_invalid_type"


class DocumentTooLargeError(DocumentError):
    code = "document_too_large"


class DocumentTooManyError(DocumentError):
    code = "document_too_many"


class DocumentTotalTooLargeError(DocumentError):
    code = "document_total_too_large"


class DocumentNotFoundError(DocumentError):
    code = "document_not_found"


class DocumentStorageError(DocumentError):
    code = "document_storage_error"


class DocumentExtractFailedError(DocumentError):
    code = "document_extract_failed"


class DocumentDraftNotFoundError(DocumentError):
    code = "document_draft_not_found"


class DocumentGenerationError(DocumentError):
    code = "document_generation_failed"


class DocumentRevisionConflictError(DocumentError):
    code = "document_revision_conflict"
