"""Public session search endpoint."""

from fastapi import APIRouter, Query

from iris_agent.session_search.service import SessionSearchService


def register_search_routes(app, search: SessionSearchService) -> None:
    router = APIRouter(prefix="/api/search", tags=["search"])

    @router.get("")
    def search_sessions(
        query: str = Query(..., min_length=1),
        limit: int = Query(5, ge=1, le=20),
    ):
        hits = search.search(query, limit=limit)
        return {"hits": [hit.to_dict() for hit in hits]}

    app.include_router(router)
