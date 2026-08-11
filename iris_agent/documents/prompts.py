"""Prompt construction for source-bound document drafts."""

from __future__ import annotations

import json

from iris_agent.core.models import Message


_TEMPLATE_GUIDANCE = {
    "meeting_minutes": "Write concise meeting minutes with decisions, action items, owners when present, and risks.",
    "prd": "Write a concise product requirements document with goals, scope, requirements, and acceptance criteria.",
    "technical_solution": "Write a technical solution with context, architecture, implementation steps, risks, and validation.",
    "weekly_report": "Write a weekly report with completed work, progress, risks, and next steps.",
}


def build_draft_messages(template: str, documents: list[dict[str, object]], instructions: str) -> list[Message]:
    """Build a strict JSON-only request without exposing server file paths."""
    payload = {
        "template": template,
        "template_guidance": _TEMPLATE_GUIDANCE[template],
        "instructions": instructions,
        "documents": documents,
    }
    system = (
        "You write a document draft only from the supplied source documents. "
        "Return exactly one JSON object and no Markdown fence. Its keys must be exactly "
        "title, markdown, citations. citations is an array of objects with exactly document_id and location. "
        "Every citation document_id must be one of the supplied documents. Never invent citations, facts, file paths, or sources. "
        "Source text marked truncated is incomplete; do not imply that it is complete and cite the source location for claims."
    )
    return [
        Message(role="system", content=system),
        Message(role="user", content=json.dumps(payload, ensure_ascii=False)),
    ]
