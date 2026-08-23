from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from .models import ApiProfile, ProfileCollection


class ProfileStoreError(RuntimeError):
    """A profile collection could not be safely read or written."""


@dataclass(frozen=True, slots=True)
class MigrationDefaults:
    base_url: str
    model: str
    api_key: str = ""


class ProfileStore:
    def __init__(
        self,
        path: str | Path,
        env_path: str | Path,
        migration_defaults: MigrationDefaults | None = None,
    ):
        self.path = Path(path)
        self.env_path = Path(env_path)
        self.migration_defaults = migration_defaults
        self._lock = threading.RLock()

    def load(self) -> ProfileCollection:
        with self._lock:
            if not self.path.exists():
                values = self._read_env()
                defaults = self.migration_defaults or MigrationDefaults("", "")
                profile_id = uuid.uuid4().hex
                migrated = ProfileCollection(
                    version=1,
                    active_id=profile_id,
                    profiles=(
                        ApiProfile(
                            id=profile_id,
                            name="默认配置",
                            base_url=values.get("OPENAI_BASE_URL") or defaults.base_url,
                            api_key=values.get("OPENAI_API_KEY") or defaults.api_key,
                            model=values.get("LLM_MODEL") or defaults.model,
                        ),
                    ),
                )
                return self.save(migrated)
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                value = ProfileCollection(
                    version=raw["version"],
                    active_id=raw["active_id"],
                    profiles=tuple(ApiProfile(**item) for item in raw["profiles"]),
                )
                return self._validate(value)
            except ProfileStoreError:
                raise
            except (
                OSError,
                UnicodeError,
                json.JSONDecodeError,
                KeyError,
                TypeError,
                AttributeError,
                ValueError,
            ) as exc:
                raise ProfileStoreError("Unable to read profile store") from exc

    def save(self, collection: ProfileCollection) -> ProfileCollection:
        with self._lock:
            normalized = self._validate(collection)
            payload = {
                "version": normalized.version,
                "active_id": normalized.active_id,
                "profiles": [asdict(item) for item in normalized.profiles],
            }
            temporary: Path | None = None
            descriptor: int | None = None
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                descriptor, temporary_name = tempfile.mkstemp(
                    prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
                )
                temporary = Path(temporary_name)
                with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                    descriptor = None
                    json.dump(payload, handle, ensure_ascii=False, indent=2)
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, self.path)
                temporary = None
                return normalized
            except Exception as exc:
                raise ProfileStoreError("Unable to save profile store") from exc
            finally:
                if descriptor is not None:
                    try:
                        os.close(descriptor)
                    except OSError:
                        pass
                if temporary is not None:
                    try:
                        temporary.unlink(missing_ok=True)
                    except OSError:
                        pass

    def _read_env(self) -> dict[str, str]:
        if not self.env_path.exists():
            return {}
        try:
            lines = self.env_path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            raise ProfileStoreError("Unable to read environment configuration") from exc
        values: dict[str, str] = {}
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            values[key.strip()] = value.strip()
        return values

    @staticmethod
    def _validate(collection: ProfileCollection) -> ProfileCollection:
        if not isinstance(collection, ProfileCollection):
            raise ProfileStoreError("Invalid profile collection")
        if type(collection.version) is not int or collection.version != 1:
            raise ProfileStoreError("Unsupported profile store version")
        if not isinstance(collection.active_id, str):
            raise ProfileStoreError("Active profile ID must be a string")
        if not isinstance(collection.profiles, (tuple, list)):
            raise ProfileStoreError("Profiles must be a collection")
        if not collection.profiles:
            raise ProfileStoreError("At least one profile is required")
        profiles: list[ApiProfile] = []
        for item in collection.profiles:
            if not isinstance(item, ApiProfile):
                raise ProfileStoreError("Invalid profile")
            required_strings = (item.id, item.name, item.base_url, item.model, item.last_test_status)
            if not all(isinstance(value, str) for value in required_strings):
                raise ProfileStoreError("Required profile fields must be strings")
            if not isinstance(item.api_key, str):
                raise ProfileStoreError("API key must be a string")
            if item.last_tested_at is not None and not isinstance(item.last_tested_at, str):
                raise ProfileStoreError("Last tested time must be a string or null")
            normalized = ApiProfile(
                id=item.id.strip(),
                name=item.name.strip(),
                base_url=item.base_url.strip(),
                api_key=item.api_key,
                model=item.model.strip(),
                last_test_status=item.last_test_status.strip(),
                last_tested_at=item.last_tested_at,
            )
            if not all(
                (normalized.id, normalized.name, normalized.base_url, normalized.model, normalized.last_test_status)
            ):
                raise ProfileStoreError("Required profile strings must not be blank")
            if normalized.last_test_status not in {"untested", "connected", "failed"}:
                raise ProfileStoreError("Invalid profile test status")
            profiles.append(normalized)
        ids = [item.id for item in profiles]
        if len(ids) != len(set(ids)):
            raise ProfileStoreError("Profile IDs must be unique")
        active_id = collection.active_id.strip()
        if not active_id or active_id not in ids:
            raise ProfileStoreError("Active profile must identify an existing profile")
        return ProfileCollection(version=collection.version, active_id=active_id, profiles=tuple(profiles))
