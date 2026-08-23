from dataclasses import dataclass


def _mask_api_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:3]}****{key[-4:]}"


@dataclass(frozen=True, slots=True)
class ApiProfile:
    id: str
    name: str
    base_url: str
    api_key: str
    model: str
    last_test_status: str = "untested"
    last_tested_at: str | None = None

    def to_public(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "base_url": self.base_url,
            "model": self.model,
            "last_test_status": self.last_test_status,
            "last_tested_at": self.last_tested_at,
            "api_key_set": bool(self.api_key),
            "api_key_masked": _mask_api_key(self.api_key),
        }


@dataclass(frozen=True, slots=True)
class ProfileCollection:
    version: int
    active_id: str
    profiles: tuple[ApiProfile, ...]
