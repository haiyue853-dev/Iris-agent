from iris_agent.core.errors import IrisError


class AttachmentError(IrisError):
    code = "attachment_error"


class AttachmentAccessError(AttachmentError):
    code = "attachment_access_denied"


class AttachmentNotFoundError(AttachmentError):
    code = "attachment_not_found"


class AttachmentInvalidTypeError(AttachmentError):
    code = "attachment_invalid_type"


class AttachmentTooLargeError(AttachmentError):
    code = "attachment_too_large"


class AttachmentTooManyError(AttachmentError):
    code = "attachment_too_many"


class AttachmentStorageError(AttachmentError):
    code = "attachment_storage_error"


class AttachmentExtractError(AttachmentError):
    code = "attachment_extract_error"
