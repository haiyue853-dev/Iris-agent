import sys
from types import SimpleNamespace

import pytest

from iris_agent.knowledge.parsing import ParsingError, parse_document, supported_suffixes


def test_image_parser_uses_configured_describer():
    calls = []

    parsed = parse_document(
        ".png",
        b"image-bytes",
        name="diagram.png",
        image_describer=lambda content, name: calls.append((content, name)) or "架构图包含检索器和重排器",
    )

    assert ".png" in supported_suffixes()
    assert calls == [(b"image-bytes", "diagram.png")]
    assert parsed.sections[0].kind == "image"
    assert parsed.text == "架构图包含检索器和重排器"


def test_image_parser_reports_missing_vlm_configuration():
    with pytest.raises(ParsingError, match="视觉解析"):
        parse_document(".jpg", b"image-bytes", name="photo.jpg")


def test_scanned_pdf_pages_fall_back_to_image_describer(monkeypatch):
    calls = []

    class Pixmap:
        def tobytes(self, kind):
            assert kind == "png"
            return b"page-image"

    class Page:
        def get_text(self, kind):
            return ""

        def find_tables(self):
            return SimpleNamespace(tables=[])

        def get_pixmap(self, matrix, alpha):
            assert alpha is False
            return Pixmap()

    class Document:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def __iter__(self):
            return iter([Page()])

    fake_fitz = SimpleNamespace(open=lambda **_: Document(), Matrix=lambda x, y: (x, y))
    monkeypatch.setitem(sys.modules, "pymupdf", fake_fitz)

    parsed = parse_document(
        ".pdf",
        b"pdf",
        name="scan.pdf",
        image_describer=lambda content, name: calls.append((content, name)) or "扫描页文字",
    )

    assert calls == [(b"page-image", "scan.pdf · 第 1 页")]
    assert parsed.sections[0].kind == "image"
    assert parsed.sections[0].location == "第 1 页"
    assert parsed.text == "扫描页文字"
