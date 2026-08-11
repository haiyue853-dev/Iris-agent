from __future__ import annotations

import json

from fastapi.testclient import TestClient

from iris_agent.api.app import create_app
from iris_agent.core.agent import AgentLoop, AgentService
from iris_agent.core.models import ProviderResponse
from iris_agent.documents import DocumentService
from iris_agent.sessions.json_store import JsonSessionRepository
from iris_agent.tools.registry import ToolRegistry


class DraftProvider:
    def __init__(self):
        self.content = "{}"
        self.calls = 0

    def complete(self, _messages, _tools):
        self.calls += 1
        return ProviderResponse(content=self.content)


def make_client(tmp_path) -> tuple[TestClient, DraftProvider]:
    provider = DraftProvider()
    sessions = JsonSessionRepository(tmp_path / "sessions")
    agent = AgentService(AgentLoop(provider, ToolRegistry()), sessions, "system")
    documents = DocumentService(tmp_path / "documents", provider=provider)
    return TestClient(create_app(agent, sessions, documents=documents)), provider


def test_documents_api_upload_generates_edits_exports_and_deletes_without_leaking_source(tmp_path) -> None:
    client, provider = make_client(tmp_path)

    uploaded = client.post(
        "/api/documents",
        files={"file": ("notes.txt", "private source body".encode("utf-8"), "text/plain")},
    )

    assert uploaded.status_code == 201
    document = uploaded.json()
    assert document["original_name"] == "notes.txt"
    assert document["extraction_status"] == "ready"
    assert "path" not in document
    assert "private source body" not in json.dumps(document)
    listed = client.get("/api/documents")
    assert listed.status_code == 200
    assert "private source body" not in listed.text

    provider.content = json.dumps(
        {
            "title": "项目 PRD",
            "markdown": "## 目标\n\n- 完成草稿",
            "citations": [{"document_id": document["id"], "location": "正文"}],
        },
        ensure_ascii=False,
    )
    generated = client.post(
        "/api/documents/drafts/generate",
        json={"template": "prd", "document_ids": [document["id"]], "instructions": "简洁"},
    )

    assert generated.status_code == 201
    draft = generated.json()
    assert draft["document_ids"] == [document["id"]]
    assert draft["markdown"] == "## 目标\n\n- 完成草稿"
    assert "private source body" not in generated.text
    assert "path" not in generated.text
    assert provider.calls == 1

    listed_drafts = client.get("/api/documents/drafts")
    assert listed_drafts.status_code == 200
    assert listed_drafts.json()["drafts"][0]["id"] == draft["id"]
    fetched = client.get(f"/api/documents/drafts/{draft['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["revision"] == 1

    saved = client.put(
        f"/api/documents/drafts/{draft['id']}",
        json={"title": "已编辑 PRD", "markdown": "编辑后的正文", "expected_revision": 1},
    )
    assert saved.status_code == 200
    assert saved.json()["revision"] == 2
    assert saved.json()["citations"] == draft["citations"]
    conflict = client.put(
        f"/api/documents/drafts/{draft['id']}",
        json={"title": "覆盖", "markdown": "不应保存", "expected_revision": 1},
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "document_revision_conflict"

    markdown = client.get(f"/api/documents/drafts/{draft['id']}/export?format=markdown")
    assert markdown.status_code == 200
    assert markdown.headers["content-type"].startswith("text/markdown")
    assert markdown.text.startswith("# 已编辑 PRD")
    assert "private source body" not in markdown.text
    assert "filename=\"iris-document-" in markdown.headers["content-disposition"]
    docx = client.get(f"/api/documents/drafts/{draft['id']}/export?format=docx")
    assert docx.status_code == 200
    assert docx.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert docx.content.startswith(b"PK")
    invalid_export = client.get(f"/api/documents/drafts/{draft['id']}/export?format=pdf")
    assert invalid_export.status_code == 422
    assert invalid_export.json()["detail"]["code"] == "document_validation_error"

    deleted = client.delete(f"/api/documents/{document['id']}")
    assert deleted.status_code == 204
    assert client.get(f"/api/documents/{document['id']}").status_code == 404
    assert client.get("/api/documents").json()["documents"] == []


def test_documents_api_rejects_generate_without_sources_without_calling_provider(tmp_path) -> None:
    client, provider = make_client(tmp_path)

    response = client.post(
        "/api/documents/drafts/generate",
        json={"template": "prd", "document_ids": [], "instructions": ""},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "document_validation_error"
    assert provider.calls == 0


def test_documents_api_rejects_unsupported_upload_as_validation_error(tmp_path) -> None:
    client, _ = make_client(tmp_path)

    response = client.post(
        "/api/documents",
        files={"file": ("unsafe.exe", b"not a document", "application/octet-stream")},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "document_invalid_type"
