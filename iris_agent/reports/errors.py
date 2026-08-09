from iris_agent.core.errors import IrisError


class ReportError(IrisError):
    code = "report_error"

    def __init__(self, message: str, *, code: str | None = None):
        if code is not None:
            self.code = code
        super().__init__(message)


class ReportNotFoundError(ReportError):
    code = "report_not_found"


class ReportValidationError(ReportError):
    code = "report_validation_error"


class ReportStorageError(ReportError):
    code = "report_storage_error"


class ReportGenerationError(ReportError):
    code = "report_generation_failed"


class ReportVersionConflictError(ReportError):
    code = "report_version_conflict"


class ReportSuggestionNotFoundError(ReportError):
    code = "report_suggestion_not_found"


class ReportSuggestionAlreadyAppliedError(ReportError):
    code = "report_suggestion_already_applied"


class ReportAttachmentError(ReportError):
    code = "report_attachment_error"


class ReportAttachmentInvalidTypeError(ReportAttachmentError):
    code = "report_attachment_invalid_type"


class ReportAttachmentTooLargeError(ReportAttachmentError):
    code = "report_attachment_too_large"


class ReportAttachmentTooManyError(ReportAttachmentError):
    code = "report_attachment_too_many"


class ReportAttachmentTotalTooLargeError(ReportAttachmentError):
    code = "report_attachment_total_too_large"


class ReportAttachmentNotFoundError(ReportAttachmentError):
    code = "report_attachment_not_found"


class ReportAttachmentStorageError(ReportAttachmentError):
    code = "report_attachment_storage_error"


class ReportAttachmentExtractError(ReportAttachmentError):
    code = "report_attachment_extract_failed"


class ReportAttachmentOcrUnavailableError(ReportAttachmentError):
    code = "report_attachment_ocr_unavailable"

