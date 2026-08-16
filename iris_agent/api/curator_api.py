"""Public curator review endpoints."""

from fastapi import APIRouter, HTTPException, status

from iris_agent.api.schemas import CuratorApplyRequest
from iris_agent.curator.service import CuratorReportNotFoundError, CuratorService


def register_curator_routes(app, curator: CuratorService) -> None:
    router = APIRouter(prefix="/api/curator", tags=["curator"])

    def _suggestion_data(suggestion) -> dict:
        return {
            "id": suggestion.id,
            "kind": suggestion.kind,
            "scope": suggestion.scope,
            "field": suggestion.field,
            "targets": list(suggestion.targets),
            "keep": suggestion.keep,
            "drop": suggestion.drop,
            "summary": suggestion.summary,
            "reason": suggestion.reason,
            "applied": suggestion.applied,
            "dismissed": suggestion.dismissed,
        }

    def _report_data(report) -> dict:
        return {
            "id": report.id,
            "status": report.status,
            "created_at": report.created_at,
            "summary": report.summary,
            "suggestions": [_suggestion_data(item) for item in report.suggestions],
        }

    def _report_summary(report) -> dict:
        return {
            "id": report.id,
            "status": report.status,
            "created_at": report.created_at,
            "summary": report.summary,
            "suggestion_count": len(report.suggestions),
        }

    def _suggestion_ids(request: CuratorApplyRequest):
        return None if request.all else request.suggestion_ids

    @router.post("/run", status_code=status.HTTP_201_CREATED)
    def run_curator():
        return _report_data(curator.run())

    @router.get("/reports")
    def list_reports(limit: int = 20):
        limit = max(1, min(limit, 50))
        reports = curator.list_reports()[:limit]
        return {"reports": [_report_summary(item) for item in reports]}

    @router.get("/reports/{report_id}")
    def get_report(report_id: str):
        try:
            return _report_data(curator.get_report(report_id))
        except CuratorReportNotFoundError:
            raise HTTPException(
                404, detail={"code": "curator_report_not_found", "message": "审查报告不存在"}
            ) from None

    @router.post("/reports/{report_id}/apply")
    def apply_report(report_id: str, request: CuratorApplyRequest):
        try:
            count = curator.apply(report_id, _suggestion_ids(request))
        except CuratorReportNotFoundError:
            raise HTTPException(
                404, detail={"code": "curator_report_not_found", "message": "审查报告不存在"}
            ) from None
        return {"applied": count}

    @router.post("/reports/{report_id}/dismiss")
    def dismiss_report(report_id: str, request: CuratorApplyRequest):
        try:
            count = curator.dismiss(report_id, _suggestion_ids(request))
        except CuratorReportNotFoundError:
            raise HTTPException(
                404, detail={"code": "curator_report_not_found", "message": "审查报告不存在"}
            ) from None
        return {"dismissed": count}

    app.include_router(router)
