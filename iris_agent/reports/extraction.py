from __future__ import annotations

from iris_agent.attachments.errors import AttachmentExtractError, AttachmentInvalidTypeError
from iris_agent.attachments.extraction import (
    AttachmentExtraction,
    AttachmentExtractionSource,
    LocalAttachmentExtractor as _AttachmentExtractor,
    LocalOcr,
)
from iris_agent.reports.errors import (
    ReportAttachmentExtractError,
    ReportAttachmentInvalidTypeError,
    ReportAttachmentOcrUnavailableError,
)


class LocalAttachmentExtractor(_AttachmentExtractor):
    """日报兼容门面：保留既有异常代码和导入路径。"""

    def extract(self, attachment) -> AttachmentExtraction:
        try:
            return super().extract(attachment)
        except AttachmentInvalidTypeError as exc:
            raise ReportAttachmentInvalidTypeError("不支持该日报附件") from exc
        except AttachmentExtractError as exc:
            if "OCR" in str(exc):
                raise ReportAttachmentOcrUnavailableError("本机 OCR 未配置") from exc
            raise ReportAttachmentExtractError("无法提取日报附件文本") from exc

