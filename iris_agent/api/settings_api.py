"""HTTP API for persistent, hot-swappable model configuration profiles."""
import logging
from fastapi import HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from iris_agent.settings_profiles.service import (ConnectionInput, ProfileActivationError, ProfileConflictError, ProfileInput, ProfileNotFoundError, ProfilePatch, ProfileValidationError)

logger = logging.getLogger(__name__)

class ProfileCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(max_length=200); base_url: str = Field(max_length=500); model: str = Field(max_length=200); api_key: str = Field(default="", max_length=500)

class ProfilePatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, max_length=200); base_url: str | None = Field(default=None, max_length=500); model: str | None = Field(default=None, max_length=200); api_key: str | None = Field(default=None, max_length=500); clear_api_key: bool = False

class ConnectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_url: str = Field(max_length=500); model: str = Field(max_length=200); api_key: str | None = Field(default=None, max_length=500); profile_id: str | None = Field(default=None, max_length=200)

def _raise_safe(error: Exception) -> None:
    if isinstance(error, ProfileNotFoundError): raise HTTPException(404, {"code": "profile_not_found", "message": "配置不存在"})
    if isinstance(error, ProfileConflictError) and not isinstance(error, ProfileActivationError): raise HTTPException(409, {"code": "profile_conflict", "message": "配置状态冲突"})
    if isinstance(error, ProfileValidationError): raise HTTPException(422, {"code": "profile_validation", "message": "配置内容无效"})
    if isinstance(error, ProfileActivationError):
        logger.error("Settings profile activation failed")
        raise HTTPException(500, {"code": "profile_activation_failed", "message": "配置激活失败"})
    logger.error("Settings profile store unavailable")
    raise HTTPException(500, {"code": "settings_store_unavailable", "message": "配置存储不可用"})

def register_settings_routes(app, service) -> None:
    @app.get("/api/settings/profiles")
    def list_profiles():
        try: return service.list_state()
        except Exception as error: _raise_safe(error)
    @app.post("/api/settings/profiles", status_code=status.HTTP_201_CREATED)
    def create_profile(payload: ProfileCreateRequest):
        try: return service.create(ProfileInput(**payload.model_dump()))
        except Exception as error: _raise_safe(error)
    @app.patch("/api/settings/profiles/{profile_id}")
    def patch_profile(profile_id: str, payload: ProfilePatchRequest):
        try: return service.update(profile_id, ProfilePatch(**payload.model_dump()))
        except Exception as error: _raise_safe(error)
    @app.delete("/api/settings/profiles/{profile_id}", status_code=204)
    def delete_profile(profile_id: str):
        try: service.delete(profile_id); return Response(status_code=204)
        except Exception as error: _raise_safe(error)
    @app.post("/api/settings/profiles/{profile_id}/activate")
    def activate_profile(profile_id: str):
        try: return service.activate(profile_id)
        except Exception as error: _raise_safe(error)
    @app.post("/api/settings/profiles/test")
    def test_profile(payload: ConnectionRequest):
        try: return service.test_connection(ConnectionInput(**payload.model_dump()))
        except Exception as error: _raise_safe(error)
