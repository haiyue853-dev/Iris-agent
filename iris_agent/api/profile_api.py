"""Public user profile endpoints."""

from fastapi import APIRouter

from iris_agent.api.schemas import ProfileUpdateRequest
from iris_agent.profile.service import ProfileService


def register_profile_routes(app, profile: ProfileService) -> None:
    router = APIRouter(prefix="/api/profile", tags=["profile"])

    def _profile_data(p) -> dict:
        return {
            "name": p.name,
            "preferences": list(p.preferences),
            "goals": list(p.goals),
            "style": p.style,
            "facts": list(p.facts),
            "updated_at": p.updated_at,
        }

    @router.get("")
    def get_profile():
        return _profile_data(profile.get())

    @router.put("")
    def update_profile(request: ProfileUpdateRequest):
        updated = profile.replace(
            request.name,
            request.preferences,
            request.goals,
            request.style,
            request.facts,
        )
        return _profile_data(updated)

    app.include_router(router)
