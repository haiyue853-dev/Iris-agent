from types import SimpleNamespace

from fastapi.testclient import TestClient

from iris_agent.api.app import create_app


class FakeSections:
    def to_dict(self):
        return {
            "completed": [],
            "in_progress": [],
            "problems": [],
            "next_day": [],
            "assistance": [],
        }


class FakeReports:
    provider = object()
    repository = object()

    def ensure_workspace(self, report_date):
        version = SimpleNamespace(
            number=1,
            kind="manual",
            instruction=None,
            created_at=100.0,
            sections=FakeSections(),
        )
        return SimpleNamespace(
            date=report_date,
            source_notes="",
            source_session_id=None,
            current_version=1,
            revision=1,
            current=version,
            versions=[version],
            attachments=[],
            created_at=100.0,
            updated_at=100.0,
        )


def test_daily_report_workspace_route_is_available_when_report_service_is_supplied():
    client = TestClient(create_app(object(), object(), FakeReports()))

    response = client.post("/api/reports/2026-08-09/workspace")

    assert response.status_code == 200
    assert response.json()["date"] == "2026-08-09"
    assert response.json()["current"]["sections"]["completed"] == []
