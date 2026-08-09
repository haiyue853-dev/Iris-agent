from __future__ import annotations

import sys
from types import SimpleNamespace

from iris_agent.reports.extraction import LocalAttachmentExtractor


class XlsFile:
    name = "progress.xls"
    suffix = ".xls"

    def read_bytes(self) -> bytes:
        return b"legacy-xls"


def test_extracts_xls_with_xlrd_and_limits_rows_and_columns(monkeypatch) -> None:
    class Sheet:
        name = "进度"
        nrows = 101
        ncols = 21

        @staticmethod
        def cell_value(row: int, column: int) -> str:
            return f"{row}:{column}"

    workbook = SimpleNamespace(sheets=lambda: [Sheet()])
    monkeypatch.setitem(sys.modules, "xlrd", SimpleNamespace(open_workbook=lambda **_kwargs: workbook))

    result = LocalAttachmentExtractor(max_chars=20_000).extract(XlsFile())

    assert "工作表：进度" in result.text
    assert "0:0" in result.text
    assert "99:19" in result.text
    assert "100:0" not in result.text
    assert "0:20" not in result.text

