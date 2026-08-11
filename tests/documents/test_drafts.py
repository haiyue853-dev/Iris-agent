from __future__ import annotations

import json

import pytest

from iris_agent.core.models import ProviderResponse
from iris_agent.documents import DocumentError, DocumentService


class RecordingProvider:
    def __init__(self, content: str):
        self.content = content
        self.calls: list[tuple[object, object]] = []

    def complete(self, messages, tools):
        self.calls.append((messages, tools))
        return ProviderResponse(content=self.content)


def response_for(document_id: str) -> str:
    return json.dumps(
        {
            "title": "需求评审纪要",
            "markdown": "## 结论\n\n- 已完成评审",
            "citations": [{"document_id": document_id, "location": "正文"}],
        },
        ensure_ascii=False,
    )


def ready_document(service: DocumentService):
    return service.upload("notes.txt", "项目资料正文".encode("utf-8"), "text/plain")


@pytest.mark.parametrize(
    "template",
    ["meeting_minutes", "prd", "technical_solution", "weekly_report"],
)
def test_generate_draft_uses_only_selected_ready_document_and_strict_template(tmp_path, template: str) -> None:
    provider = RecordingProvider("{}")
    service = DocumentService(tmp_path, provider=provider)
    document = ready_document(service)
    provider.content = response_for(document.id)

    draft = service.generate_draft(template, [document.id], "请写得简洁")

    assert draft.template == template
    assert draft.document_ids == (document.id,)
    assert draft.citations[0].document_id == document.id
    assert len(provider.calls) == 1
    messages, tools = provider.calls[0]
    assert tools == []
    payload = json.loads(messages[1].content)
    assert payload["template"] == template
    assert payload["documents"] == [
        {
            "id": document.id,
            "name": "notes.txt",
            "text": "项目资料正文",
            "truncated": False,
        }
    ]


def test_generate_draft_without_ready_source_never_calls_provider(tmp_path) -> None:
    provider = RecordingProvider("{}")
    service = DocumentService(tmp_path, provider=provider)

    with pytest.raises(DocumentError) as error:
        service.generate_draft("prd", [], "")

    assert error.value.code == "document_validation_error"
    assert provider.calls == []


@pytest.mark.parametrize(
    "content",
    [
        "```json\n{}\n```",
        "not json",
        '{"title":"x","markdown":"body","citations":[{"document_id":"external","location":"p1"}]}',
    ],
)
def test_generate_draft_rejects_invalid_model_output_and_external_citations(tmp_path, content: str) -> None:
    provider = RecordingProvider(content)
    service = DocumentService(tmp_path, provider=provider)
    document = ready_document(service)

    with pytest.raises(DocumentError) as error:
        service.generate_draft("prd", [document.id], "")

    assert error.value.code == "document_model_output_invalid"


def test_drafts_survive_restart_and_edits_require_current_revision(tmp_path) -> None:
    provider = RecordingProvider("{}")
    service = DocumentService(tmp_path, provider=provider)
    document = ready_document(service)
    provider.content = response_for(document.id)
    created = service.generate_draft("technical_solution", [document.id], "")

    restarted = DocumentService(tmp_path, provider=provider)
    loaded = restarted.get_draft(created.id)
    saved = restarted.save_draft(created.id, "已修改标题", "修改后的正文", loaded.revision)

    assert loaded == created
    assert saved.revision == created.revision + 1
    assert saved.document_ids == created.document_ids
    assert saved.citations == created.citations
    with pytest.raises(DocumentError) as error:
        restarted.save_draft(created.id, "覆盖", "不应保存", created.revision)
    assert error.value.code == "document_revision_conflict"
