"""Document-level mind-map model and bounded payload normalisation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class MindMapNode:
    id: str
    parent_id: str | None
    label: str
    summary: str
    kind: str
    ordinal: int
    evidence_chunk_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "parent_id": self.parent_id,
            "label": self.label,
            "summary": self.summary,
            "kind": self.kind,
            "ordinal": self.ordinal,
            "evidence_chunk_ids": list(self.evidence_chunk_ids),
        }


def _text(value: object, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _label(value: object, fallback: str) -> str:
    text = _text(value, 80).lstrip("#*-•0123456789.、 ").strip("，。；：:！？!?（）()[]【】")
    if not text:
        text = fallback
    for separator in ("。", "；", "：", ":", "，", ","):
        if separator in text:
            text = text.split(separator, 1)[0]
    return text[:20]


def _evidence_ids(values: object, chunks: Iterable[Any]) -> tuple[str, ...]:
    by_ordinal = {int(chunk.ordinal): str(chunk.id) for chunk in chunks}
    if not isinstance(values, list):
        return ()
    result = []
    for value in values:
        try:
            chunk_id = by_ordinal.get(int(value))
        except (TypeError, ValueError):
            chunk_id = None
        if chunk_id and chunk_id not in result:
            result.append(chunk_id)
    return tuple(result[:6])
def select_mindmap_chunks(chunks: Iterable[Any], limit: int = 24) -> list[Any]:
    """Select evenly distributed chunks so the outline covers beginning, middle, and end."""
    values = list(chunks)
    if limit <= 0 or not values:
        return []
    if len(values) <= limit:
        return values
    indexes = sorted({round(index * (len(values) - 1) / (limit - 1)) for index in range(limit)}) if limit > 1 else [0]
    return [values[index] for index in indexes]



def normalise_mindmap_payload(title: str, payload: dict[str, Any], chunks: Iterable[Any]) -> list[MindMapNode]:
    """Convert model JSON into one root and at most two descendant levels."""
    chunk_list = list(chunks)
    nodes = [MindMapNode("root", None, _text(title, 120) or "未命名资料", _text(payload.get("summary"), 240), "root", 0)]
    branches = payload.get("branches") if isinstance(payload, dict) else None
    for branch_index, branch in enumerate(branches[:8] if isinstance(branches, list) else []):
        if not isinstance(branch, dict) or len(nodes) >= 40:
            continue
        branch_id = f"branch-{branch_index + 1}"
        branch_node = MindMapNode(
            branch_id,
            "root",
            _label(branch.get("title"), f"主题 {branch_index + 1}"),
            _text(branch.get("summary"), 240),
            "branch",
            branch_index,
            _evidence_ids(branch.get("evidence_ordinals"), chunk_list),
        )
        nodes.append(branch_node)
        children = branch.get("children")
        for child_index, child in enumerate(children[:6] if isinstance(children, list) else []):
            if not isinstance(child, dict) or len(nodes) >= 40:
                continue
            nodes.append(
                MindMapNode(
                    f"point-{branch_index + 1}-{child_index + 1}",
                    branch_id,
                    _label(child.get("title"), f"观点 {child_index + 1}"),
                    _text(child.get("summary"), 240),
                    "point",
                    child_index,
                    _evidence_ids(child.get("evidence_ordinals"), chunk_list),
                )
            )
    return nodes


def build_fallback_mindmap(title: str, chunks: Iterable[Any]) -> list[MindMapNode]:
    """Create a small deterministic outline when the local model is unavailable."""
    chunk_list = select_mindmap_chunks(chunks, limit=8)
    payload: dict[str, Any] = {"summary": "", "branches": []}
    summaries = []
    for chunk in chunk_list[:8]:
        lines = [line.strip() for line in re.split(r"[\r\n]+", str(chunk.content)) if line.strip()]
        if not lines:
            continue
        heading = next((line for line in lines if line.lstrip().startswith("#")), lines[0])
        details = [line for line in lines if line != heading][:4]
        summary = _text(" ".join(details or lines), 240)
        summaries.append(summary)
        payload["branches"].append(
            {
                "title": _label(heading, f"主题 {len(payload['branches']) + 1}"),
                "summary": summary,
                "evidence_ordinals": [chunk.ordinal],
                "children": [
                    {"title": _label(line, f"观点 {index + 1}"), "summary": _text(line, 240), "evidence_ordinals": [chunk.ordinal]}
                    for index, line in enumerate(details)
                ],
            }
        )
        if len(payload["branches"]) == 8:
            break
    payload["summary"] = _text(" ".join(summaries), 240)
    return normalise_mindmap_payload(title, payload, chunk_list)
