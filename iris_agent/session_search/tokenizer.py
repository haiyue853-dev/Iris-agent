"""Tokenization for session search: CJK bigrams plus lowercase English words."""

from __future__ import annotations

import re

_CJK_SEGMENT = re.compile(r"[\u4e00-\u9fff]+")
_WORD = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> set[str]:
    """Split text into a deduplicated set of search tokens.

    Chinese runs produce consecutive bigrams (a single character is kept as
    its own token); English and digits produce lowercase word tokens.
    """
    tokens: set[str] = set()
    lowered = text.lower()
    for match in _WORD.findall(lowered):
        tokens.add(match)
    for segment in _CJK_SEGMENT.findall(text):
        if len(segment) == 1:
            tokens.add(segment)
        else:
            for index in range(len(segment) - 1):
                tokens.add(segment[index : index + 2])
    return tokens
