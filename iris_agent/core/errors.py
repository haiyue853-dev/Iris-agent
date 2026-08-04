class IrisError(Exception):
    code = "iris_error"

    def __init__(self, message: str):
        super().__init__(message)
        self.safe_message = message


class ConfigurationError(IrisError):
    code = "configuration_error"


class ProviderError(IrisError):
    code = "provider_error"


class SessionError(IrisError):
    code = "session_error"


class SessionNotFoundError(SessionError):
    code = "session_not_found"


class ToolRoundLimitError(IrisError):
    code = "tool_round_limit"


class ValidationError(IrisError):
    code = "validation_error"
