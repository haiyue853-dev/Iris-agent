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
