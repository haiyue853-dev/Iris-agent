from __future__ import annotations

from pathlib import Path

import pytest

from iris_agent.attachments.errors import AttachmentExtractError
from iris_agent.attachments.extraction import LocalAttachmentExtractor
from iris_agent.attachments.storage import AttachmentStorage


def test_extracts_text_with_source_and_truncation(tmp_path: Path) -> None:
    storage = AttachmentStorage(tmp_path, max_file_bytes=100, max_total_bytes=100, max_count=1)
    saved = storage.save("session-1", "notes.txt", b"abcdef", "text/plain")

    result = LocalAttachmentExtractor(max_chars=4).extract(storage.open("session-1", saved.id))

    assert result.text == "abcd"
    assert result.sources[0].file_name == "notes.txt"
    assert result.truncated is True


def test_images_report_ocr_unavailable_without_configuration(tmp_path: Path) -> None:
    storage = AttachmentStorage(tmp_path, max_file_bytes=100, max_total_bytes=100, max_count=1)
    saved = storage.save("session-1", "picture.png", b"not-an-image", "image/png")

    with pytest.raises(AttachmentExtractError, match="OCR"):
        LocalAttachmentExtractor(max_chars=100).extract(storage.open("session-1", saved.id))
