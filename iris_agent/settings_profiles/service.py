from __future__ import annotations

import ipaddress
import uuid
import threading
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Callable, Generic, Protocol, TypeVar
from urllib.parse import urlsplit

import openai

from .models import ApiProfile, ProfileCollection


class ProfileNotFoundError(LookupError):
    """The requested profile does not exist."""


class ProfileConflictError(RuntimeError):
    """The requested operation conflicts with profile state."""


class ProfileValidationError(ValueError):
    """Profile input is invalid, without including secret input values."""


class ProfileActivationError(ProfileConflictError):
    """Profile activation failed at a stable, non-secret error boundary."""


@dataclass(frozen=True, slots=True)
class ProfileInput:
    name: str
    base_url: str
    api_key: str
    model: str


@dataclass(frozen=True, slots=True)
class ProfilePatch:
    name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
    clear_api_key: bool = False


@dataclass(frozen=True, slots=True)
class ConnectionInput:
    base_url: str
    model: str
    api_key: str | None = None
    profile_id: str | None = None


@dataclass(frozen=True, slots=True)
class ConnectionResult:
    ok: bool
    code: str
    message: str


class ProfileStoreProtocol(Protocol):
    def load(self) -> ProfileCollection: ...
    def save(self, collection: ProfileCollection) -> ProfileCollection: ...


class CompletionsProtocol(Protocol):
    def create(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int,
    ) -> object: ...


class ChatProtocol(Protocol):
    completions: CompletionsProtocol


class OpenAIClientProtocol(Protocol):
    chat: ChatProtocol


ProviderT = TypeVar("ProviderT")


class ProfileService(Generic[ProviderT]):
    def __init__(
        self,
        store: ProfileStoreProtocol,
        provider_factory: Callable[[ApiProfile], ProviderT],
        replace_provider: Callable[[ProviderT], None],
        get_provider: Callable[[], ProviderT],
        client_factory: Callable[..., OpenAIClientProtocol] = openai.OpenAI,
        disposer: Callable[[ProviderT], None] | None = None,
    ):
        self._store = store
        self._provider_factory = provider_factory
        self._replace_provider = replace_provider
        self._get_provider = get_provider
        self._client_factory = client_factory
        self._disposer = disposer or self._dispose_provider
        self._lock = threading.RLock()

    def test_connection(self, value: ConnectionInput) -> ConnectionResult:
        base_url = self._normalize_base_url(value.base_url)
        model = self._required(value.model, "model")
        api_key = None if value.api_key is None else self._string(value.api_key, "api_key").strip()
        if value.profile_id is not None:
            with self._lock:
                profile = self._find(self._store.load(), value.profile_id)
                if api_key is None:
                    api_key = profile.api_key
        elif api_key is None:
            api_key = ""

        try:
            client = self._client_factory(
                base_url=base_url,
                api_key=api_key or "local-no-key",
                timeout=10.0,
                max_retries=0,
            )
            client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=1,
            )
        except openai.AuthenticationError:
            result = ConnectionResult(False, "authentication_failed", "认证失败")
        except openai.NotFoundError:
            result = ConnectionResult(False, "model_unavailable", "模型不可用")
        except openai.APITimeoutError:
            result = ConnectionResult(False, "connection_timeout", "连接超时")
        except openai.APIConnectionError:
            result = ConnectionResult(False, "connection_failed", "连接失败")
        except openai.APIStatusError as error:
            result = ConnectionResult(
                False,
                "model_unavailable" if error.status_code == 404 else "provider_error",
                "模型不可用" if error.status_code == 404 else "服务商错误",
            )
        except Exception:
            result = ConnectionResult(False, "provider_error", "服务商错误")
        else:
            result = ConnectionResult(True, "connected", "连接成功")

        if value.profile_id is not None:
            with self._lock:
                current = self._store.load()
                profile = next(
                    (item for item in current.profiles if item.id == value.profile_id),
                    None,
                )
                if profile is None:
                    return result
                tested = replace(
                    profile,
                    last_test_status="connected" if result.ok else "failed",
                    last_tested_at=datetime.now(timezone.utc).isoformat(),
                )
                profiles = tuple(tested if item.id == profile.id else item for item in current.profiles)
                self._store.save(replace(current, profiles=profiles))
        return result

    def list_public(self) -> list[dict[str, object]]:
        with self._lock:
            return [profile.to_public() for profile in self._store.load().profiles]

    def list_state(self) -> dict[str, object]:
        with self._lock:
            collection = self._store.load()
            return {"active_id": collection.active_id, "profiles": [profile.to_public() for profile in collection.profiles]}

    def create(self, value: ProfileInput) -> dict[str, object]:
        with self._lock:
            return self._create(value)

    def _create(self, value: ProfileInput) -> dict[str, object]:
        name = self._required(value.name, "name")
        base_url = self._normalize_base_url(value.base_url)
        model = self._required(value.model, "model")
        api_key = self._string(value.api_key, "api_key").strip()
        profile = ApiProfile(uuid.uuid4().hex, name, base_url, api_key, model)
        current = self._store.load()
        saved = self._store.save(replace(current, profiles=(*current.profiles, profile)))
        return self._find(saved, profile.id).to_public()

    def update(self, profile_id: str, patch: ProfilePatch) -> dict[str, object]:
        with self._lock:
            return self._update(profile_id, patch)

    def _update(self, profile_id: str, patch: ProfilePatch) -> dict[str, object]:
        current = self._store.load()
        original = self._find(current, profile_id)
        changes: dict[str, str] = {}
        for field in ("name", "base_url", "model"):
            value = getattr(patch, field)
            if value is not None:
                changes[field] = self._normalize_base_url(value) if field == "base_url" else self._required(value, field)
        if patch.clear_api_key:
            changes["api_key"] = ""
        elif patch.api_key is not None:
            candidate = self._string(patch.api_key, "api_key").strip()
            if candidate:
                changes["api_key"] = candidate
        updated = replace(original, **changes)
        profiles = tuple(updated if item.id == profile_id else item for item in current.profiles)
        saved = self._store.save(replace(current, profiles=profiles))
        return self._find(saved, profile_id).to_public()

    def delete(self, profile_id: str) -> None:
        with self._lock:
            self._delete(profile_id)

    def _delete(self, profile_id: str) -> None:
        current = self._store.load()
        self._find(current, profile_id)
        if current.active_id == profile_id:
            raise ProfileConflictError("The active profile cannot be deleted")
        if len(current.profiles) == 1:
            raise ProfileConflictError("The last profile cannot be deleted")
        self._store.save(replace(current, profiles=tuple(p for p in current.profiles if p.id != profile_id)))

    def activate(self, profile_id: str) -> dict[str, object]:
        with self._lock:
            return self._activate(profile_id)

    def _activate(self, profile_id: str) -> dict[str, object]:
        previous = self._store.load()
        target = self._find(previous, profile_id)
        try:
            old_provider = self._get_provider()
        except Exception:
            raise ProfileActivationError("Unable to read runtime provider") from None
        try:
            provider = self._provider_factory(target)
        except Exception:
            raise ProfileValidationError("Unable to construct provider") from None
        activated = replace(previous, active_id=target.id)
        try:
            saved = self._store.save(activated)
        except Exception:
            self._disposer(provider)
            raise
        try:
            self._replace_provider(provider)
        except Exception:
            store_restored = runtime_restored = True
            try:
                self._store.save(previous)
            except Exception:
                store_restored = False
            try:
                self._replace_provider(old_provider)
            except Exception:
                runtime_restored = False
            self._disposer(provider)
            if not store_restored or not runtime_restored:
                raise ProfileActivationError(
                    "Unable to activate profile; runtime restoration failed"
                ) from None
            raise ProfileActivationError("Unable to replace runtime provider") from None
        return self._find(saved, target.id).to_public()

    @staticmethod
    def _dispose_provider(provider: ProviderT) -> None:
        close = getattr(provider, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass

    @staticmethod
    def _find(collection: ProfileCollection, profile_id: str) -> ApiProfile:
        for profile in collection.profiles:
            if profile.id == profile_id:
                return profile
        raise ProfileNotFoundError("Profile not found")

    @staticmethod
    def _string(value: object, field: str) -> str:
        if not isinstance(value, str):
            raise ProfileValidationError(f"{field} must be a string")
        return value

    @classmethod
    def _normalize_base_url(cls, value: object) -> str:
        normalized = cls._required(value, "base_url")
        authority = normalized.partition("://")[2]
        for delimiter in "/?#":
            authority = authority.split(delimiter, 1)[0]
        if (
            "\\" in authority
            or "%" in authority
            or any(character.isspace() or ord(character) < 32 for character in authority)
        ):
            raise ProfileValidationError("base_url must be a complete HTTP or HTTPS URL")
        try:
            parsed = urlsplit(normalized)
            hostname = parsed.hostname
            parsed.port
        except ValueError:
            raise ProfileValidationError(
                "base_url must be a complete HTTP or HTTPS URL"
            ) from None
        if (
            parsed.scheme not in {"http", "https"}
            or not hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ProfileValidationError("base_url must be a complete HTTP or HTTPS URL")
        try:
            ipaddress.ip_address(hostname)
        except ValueError:
            try:
                ascii_hostname = hostname.encode("idna").decode("ascii")
            except UnicodeError:
                raise ProfileValidationError(
                    "base_url must be a complete HTTP or HTTPS URL"
                ) from None
            labels = ascii_hostname.split(".")
            if (
                len(ascii_hostname) > 253
                or any(
                    not 1 <= len(label) <= 63
                    or label.startswith("-")
                    or label.endswith("-")
                    or not all(character.isascii() and (character.isalnum() or character == "-") for character in label)
                    for label in labels
                )
            ):
                raise ProfileValidationError(
                    "base_url must be a complete HTTP or HTTPS URL"
                )
        return normalized.rstrip("/")

    @classmethod
    def _required(cls, value: object, field: str) -> str:
        normalized = cls._string(value, field).strip()
        if not normalized:
            raise ProfileValidationError(f"{field} must not be blank")
        return normalized
