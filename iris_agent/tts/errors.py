from iris_agent.core.errors import IrisError


class TtsError(IrisError):
    code = "tts_error"


class TtsDisabledError(TtsError):
    code = "tts_disabled"


class TtsMessageNotFoundError(TtsError):
    code = "tts_message_not_found"


class TtsMessageError(TtsError):
    code = "tts_message_invalid"


class TtsTooLargeError(TtsError):
    code = "tts_too_large"


class TtsUnavailableError(TtsError):
    code = "tts_unavailable"


class TtsTimeoutError(TtsError):
    code = "tts_timeout"


class TtsUpstreamError(TtsError):
    code = "tts_upstream_error"

