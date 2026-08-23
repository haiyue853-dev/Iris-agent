from dataclasses import replace
from datetime import datetime, timedelta
import threading
import httpx
import openai

import pytest

from iris_agent.settings_profiles import (
    ApiProfile,
    ConnectionInput,
    ConnectionResult,
    ProfileCollection,
    ProfileConflictError,
    ProfileActivationError,
    ProfileInput,
    ProfileNotFoundError,
    ProfilePatch,
    ProfileService,
    ProfileValidationError,
)


class MemoryStore:
    def __init__(self, value):
        self.value = value
        self.saved = []

    def load(self):
        return self.value

    def save(self, value):
        self.saved.append(value)
        self.value = value
        return value


def make_collection():
    return ProfileCollection(1, "one", (
        ApiProfile("one", "One", "https://one/v1", "secret-one", "model-one"),
        ApiProfile("two", "Two", "https://two/v1", "secret-two", "model-two"),
    ))


def service(store=None, factory=lambda profile: object(), replace_provider=lambda provider: None, get_provider=lambda: object()):
    return ProfileService(store or MemoryStore(make_collection()), factory, replace_provider, get_provider)


class FakeCompletions:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return object()


class FakeClient:
    def __init__(self, completions):
        self.chat = type("Chat", (), {"completions": completions})()


def connection_service(store=None, error=None):
    calls = []
    completions = FakeCompletions(error)

    def client_factory(**kwargs):
        calls.append(kwargs)
        return FakeClient(completions)

    subject = ProfileService(
        store or MemoryStore(make_collection()), lambda profile: object(), lambda provider: None,
        lambda: object(), client_factory=client_factory,
    )
    return subject, calls, completions


def test_connection_uses_normalized_values_ten_second_timeout_and_no_retries():
    subject, client_calls, completions = connection_service()
    result = subject.test_connection(ConnectionInput(" https://local/v1/ ", " model-x ", " sk-secret "))

    assert result == ConnectionResult(True, "connected", "连接成功")
    assert client_calls == [{"base_url": "https://local/v1", "api_key": "sk-secret", "timeout": 10.0, "max_retries": 0}]
    assert completions.calls == [{
        "model": "model-x", "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 1,
    }]


def test_connection_empty_key_uses_placeholder_without_persisting_it():
    store = MemoryStore(make_collection())
    subject, client_calls, _ = connection_service(store)
    subject.test_connection(ConnectionInput("http://localhost:1234/v1", "local", "", "one"))
    assert client_calls[0]["api_key"] == "local-no-key"
    assert store.value.profiles[0].api_key == "secret-one"


def test_connection_omitted_key_uses_saved_profile_secret_without_leaking(caplog):
    subject, client_calls, _ = connection_service()
    result = subject.test_connection(ConnectionInput("https://one/v1", "model-one", profile_id="one"))
    assert client_calls[0]["api_key"] == "secret-one"
    assert "secret-one" not in result.message
    assert "secret-one" not in caplog.text


def test_connection_explicit_empty_key_does_not_use_saved_profile_secret():
    subject, client_calls, _ = connection_service()
    subject.test_connection(ConnectionInput("https://one/v1", "model-one", "", "one"))
    assert client_calls[0]["api_key"] == "local-no-key"


@pytest.mark.parametrize(("error", "code", "message"), [
    (openai.AuthenticationError("sk-secret", response=httpx.Response(401, request=httpx.Request("GET", "https://x")), body=None), "authentication_failed", "认证失败"),
    (openai.NotFoundError("sk-secret", response=httpx.Response(404, request=httpx.Request("GET", "https://x")), body=None), "model_unavailable", "模型不可用"),
    (openai.APIStatusError("sk-secret", response=httpx.Response(404, request=httpx.Request("GET", "https://x")), body=None), "model_unavailable", "模型不可用"),
    (openai.APITimeoutError(httpx.Request("GET", "https://x")), "connection_timeout", "连接超时"),
    (openai.APIConnectionError(message="sk-secret", request=httpx.Request("GET", "https://x")), "connection_failed", "连接失败"),
    (openai.APIStatusError("sk-secret", response=httpx.Response(500, request=httpx.Request("GET", "https://x")), body="sk-secret"), "provider_error", "服务商错误"),
    (RuntimeError("sk-secret"), "provider_error", "服务商错误"),
])
def test_connection_maps_errors_to_stable_safe_results(error, code, message, caplog):
    subject, _, completions = connection_service(error=error)
    result = subject.test_connection(ConnectionInput("https://x/v1", "m", "sk-secret"))
    assert result == ConnectionResult(False, code, message)
    assert len(completions.calls) == 1
    assert "sk-secret" not in result.message
    assert "sk-secret" not in caplog.text


@pytest.mark.parametrize("value", [
    ConnectionInput(" ", "m"), ConnectionInput("ftp://x", "m"),
    ConnectionInput("x/v1", "m"), ConnectionInput("https://x", " "),
])
def test_connection_rejects_invalid_input_before_constructing_client(value):
    subject, calls, _ = connection_service()
    with pytest.raises(ProfileValidationError):
        subject.test_connection(value)
    assert calls == []


@pytest.mark.parametrize("base_url", [
    "http://[::1",
    "http://localhost:not-a-port/v1",
    "http://localhost:65536/v1",
    "https://user@example.com/v1",
    "https://user:password@example.com/v1",
    "https://example.com/v1?key=value",
    "https://example.com/v1#fragment",
    "https://exa mple.com/v1",
    "https://example.com\\evil/v1",
    "https://%zz/v1",
    "https://.example.com/v1",
    "https://example.com./v1",
    "https://example..com/v1",
    "https://exa\tmple.com/v1",
    "https://exa\nmple.com/v1",
    "https://-example.com/v1",
    "https://example-.com/v1",
    f"https://{'a' * 64}.example/v1",
    f"https://{'a' * 63}.{'b' * 63}.{'c' * 63}.{'d' * 63}/v1",
])
def test_connection_rejects_malformed_or_ambiguous_base_urls(base_url):
    subject, calls, _ = connection_service()

    with pytest.raises(ProfileValidationError):
        subject.test_connection(ConnectionInput(base_url, "model"))

    assert calls == []


@pytest.mark.parametrize("base_url", [
    "http://localhost:1234/v1",
    "https://127.0.0.1/v1",
    "https://[::1]:8443/v1",
    "https://api.example.com/nested/path",
])
def test_connection_accepts_valid_hostname_path_and_port(base_url):
    subject, calls, _ = connection_service()

    assert subject.test_connection(ConnectionInput(base_url, "model")).ok is True
    assert calls[0]["base_url"] == base_url


@pytest.mark.parametrize(("error", "status"), [(None, "connected"), (RuntimeError("no"), "failed")])
def test_connection_records_saved_profile_status_and_utc_timestamp(error, status):
    store = MemoryStore(make_collection())
    subject, _, _ = connection_service(store, error)
    original = store.value
    subject.test_connection(ConnectionInput("https://x/v1", "m", profile_id="two"))
    updated = store.value.profiles[1]
    assert updated.last_test_status == status
    tested_at = datetime.fromisoformat(updated.last_tested_at)
    assert tested_at.utcoffset() == timedelta(0)
    assert store.value.active_id == original.active_id
    assert replace(updated, last_test_status="untested", last_tested_at=None) == original.profiles[1]


def test_connection_missing_profile_does_not_send_request():
    subject, calls, completions = connection_service()
    with pytest.raises(ProfileNotFoundError):
        subject.test_connection(ConnectionInput("https://x/v1", "m", "sk-secret", "missing"))
    assert calls == []
    assert completions.calls == []


def test_connection_skips_status_save_when_profile_is_deleted_during_request():
    store = MemoryStore(make_collection())
    request_started = threading.Event()
    release_request = threading.Event()

    class BlockingCompletions:
        def create(self, **kwargs):
            request_started.set()
            assert release_request.wait(1)
            return object()

    def client_factory(**kwargs):
        return FakeClient(BlockingCompletions())

    subject = ProfileService(
        store, lambda profile: object(), lambda provider: None,
        lambda: object(), client_factory=client_factory,
    )
    results = []
    failures = []

    def test_connection():
        try:
            results.append(subject.test_connection(
                ConnectionInput("https://x/v1", "m", profile_id="two")
            ))
        except Exception as exc:
            failures.append(exc)

    worker = threading.Thread(target=test_connection)
    worker.start()
    assert request_started.wait(1)
    subject.delete("two")
    state_after_delete = store.value
    saves_after_delete = len(store.saved)
    release_request.set()
    worker.join(1)

    assert not worker.is_alive()
    assert failures == []
    assert results == [ConnectionResult(True, "connected", "连接成功")]
    assert store.value == state_after_delete
    assert len(store.saved) == saves_after_delete
    assert store.value.active_id == "one"
    assert [profile.id for profile in store.value.profiles] == ["one"]


def test_create_trims_fields_assigns_uuid_and_returns_public_profile():
    store = MemoryStore(make_collection())
    result = service(store).create(ProfileInput(" New ", " https://new/v1 ", " key ", " model "))

    assert result["name"] == "New"
    assert result["base_url"] == "https://new/v1"
    assert result["model"] == "model"
    assert result["api_key_set"] is True
    assert "api_key" not in result
    assert store.value.profiles[-1].api_key == "key"
    assert store.value.profiles[-1].id not in {"one", "two"}


@pytest.mark.parametrize("field", ["name", "base_url", "model"])
def test_create_rejects_blank_required_field_without_leaking_key(field):
    values = {"name": "Name", "base_url": "https://new/v1", "api_key": "top-secret", "model": "model"}
    values[field] = "   "
    with pytest.raises(ProfileValidationError) as error:
        service().create(ProfileInput(**values))
    assert "top-secret" not in str(error.value)


def test_update_merges_only_provided_fields_and_blank_key_keeps_secret():
    store = MemoryStore(make_collection())
    result = service(store).update("one", ProfilePatch(name=" Renamed ", api_key="   "))

    updated = store.value.profiles[0]
    assert updated == replace(make_collection().profiles[0], name="Renamed")
    assert result["api_key_set"] is True


def test_update_can_explicitly_clear_key():
    store = MemoryStore(make_collection())
    service(store).update("one", ProfilePatch(clear_api_key=True))
    assert store.value.profiles[0].api_key == ""


def test_missing_update_delete_and_activate_raise_not_found():
    subject = service()
    with pytest.raises(ProfileNotFoundError):
        subject.update("missing", ProfilePatch(name="x"))
    with pytest.raises(ProfileNotFoundError):
        subject.delete("missing")
    with pytest.raises(ProfileNotFoundError):
        subject.activate("missing")


def test_delete_rejects_active_and_last_profile():
    with pytest.raises(ProfileConflictError):
        service().delete("one")
    only = ProfileCollection(1, "one", (make_collection().profiles[0],))
    with pytest.raises(ProfileConflictError):
        service(MemoryStore(only)).delete("one")


def test_delete_non_active_profile():
    store = MemoryStore(make_collection())
    result = service(store).delete("two")
    assert result is None
    assert [p.id for p in store.value.profiles] == ["one"]


def test_list_public_never_exposes_keys():
    listed = service().list_public()
    assert [item["id"] for item in listed] == ["one", "two"]
    assert all("api_key" not in item for item in listed)


def test_activate_constructs_before_save_and_does_nothing_on_factory_failure():
    store = MemoryStore(make_collection())
    runtime_calls = []

    def fail(profile):
        raise RuntimeError(f"failed for key length {len(profile.api_key)}")

    with pytest.raises(ProfileValidationError) as error:
        service(store, fail, runtime_calls.append).activate("two")
    assert "secret-two" not in str(error.value)
    assert store.saved == []
    assert runtime_calls == []


def test_activate_rolls_back_store_when_runtime_replacement_fails():
    original = make_collection()
    store = MemoryStore(original)
    replacement = object()

    def fail(provider):
        raise RuntimeError("runtime failed")

    with pytest.raises(RuntimeError):
        service(store, lambda profile: replacement, fail).activate("two")

    assert store.value == original
    assert [value.active_id for value in store.saved] == ["two", "one"]


def test_activate_disposes_candidate_when_store_save_fails():
    class FailingStore(MemoryStore):
        def save(self, value):
            raise RuntimeError("save failed")
    candidate = object()
    disposed = []
    subject = ProfileService(FailingStore(make_collection()), lambda _: candidate, lambda _: None, lambda: object(), disposer=disposed.append)

    with pytest.raises(RuntimeError):
        subject.activate("two")

    assert disposed == [candidate]


def test_activate_disposes_uninstalled_candidate_when_replace_fails():
    candidate, old = object(), object()
    disposed = []
    subject = ProfileService(MemoryStore(make_collection()), lambda _: candidate, lambda _: (_ for _ in ()).throw(RuntimeError("replace failed")), lambda: old, disposer=disposed.append)

    with pytest.raises(ProfileActivationError):
        subject.activate("two")

    assert disposed == [candidate]


def test_activate_restores_runtime_when_replace_installs_new_provider_then_fails():
    original = make_collection()
    store = MemoryStore(original)
    old_provider = object()
    new_provider = object()
    runtime = {"provider": old_provider}
    calls = []

    def replace_runtime(provider):
        runtime["provider"] = provider
        calls.append(provider)
        if len(calls) == 1:
            raise RuntimeError("failed after installing secret-two")

    with pytest.raises(ProfileActivationError) as error:
        service(store, lambda profile: new_provider, replace_runtime, lambda: runtime["provider"]).activate("two")

    assert store.value == original
    assert runtime["provider"] is old_provider
    assert calls == [new_provider, old_provider]
    assert "secret-two" not in str(error.value)


def test_activate_reports_stable_safe_error_when_runtime_restore_also_fails():
    original = make_collection()
    store = MemoryStore(original)
    old_provider = object()
    runtime = {"provider": old_provider}

    def always_fail(provider):
        runtime["provider"] = provider
        raise RuntimeError("secret-two")

    with pytest.raises(ProfileActivationError) as error:
        service(store, lambda profile: object(), always_fail, lambda: runtime["provider"]).activate("two")

    assert store.value == original
    assert str(error.value) == "Unable to activate profile; runtime restoration failed"
    assert "secret-two" not in str(error.value)


def test_activate_saves_then_replaces_and_returns_public_profile():
    store = MemoryStore(make_collection())
    events = []
    provider = object()

    def factory(profile):
        events.append(("factory", profile.id))
        return provider

    def replace_runtime(value):
        events.append(("runtime", value))
        assert store.value.active_id == "two"

    result = service(store, factory, replace_runtime).activate("two")
    assert events == [("factory", "two"), ("runtime", provider)]
    assert result["id"] == "two"


def test_concurrent_creates_do_not_lose_either_profile():
    class CoordinatedStore(MemoryStore):
        def __init__(self, value):
            super().__init__(value)
            self.first_loaded = threading.Event()
            self.release_first = threading.Event()
            self.load_calls = 0
            self.guard = threading.Lock()

        def load(self):
            with self.guard:
                self.load_calls += 1
                call = self.load_calls
                value = self.value
            if call == 1:
                self.first_loaded.set()
                assert self.release_first.wait(1)
            return value

    store = CoordinatedStore(make_collection())
    subject = service(store)
    failures = []
    second_finished = threading.Event()

    def create_second():
        _capture(failures, subject.create, ProfileInput("B", "https://b/v1", "", "b"))
        second_finished.set()

    first = threading.Thread(target=lambda: _capture(failures, subject.create, ProfileInput("A", "https://a/v1", "", "a")))
    second = threading.Thread(target=create_second)

    first.start()
    assert store.first_loaded.wait(1)
    second.start()
    assert not second_finished.wait(0.05)
    store.release_first.set()
    first.join(1)
    second.join(1)

    assert failures == []
    assert {item.name for item in store.value.profiles} == {"One", "Two", "A", "B"}


def test_concurrent_activations_are_serial_and_leave_store_runtime_consistent():
    store = MemoryStore(make_collection())
    old_provider = object()
    runtime = {"provider": old_provider}
    first_replace_entered = threading.Event()
    release_first_replace = threading.Event()
    second_factory_entered = threading.Event()
    factory_calls = 0
    factory_guard = threading.Lock()

    def factory(profile):
        nonlocal factory_calls
        with factory_guard:
            factory_calls += 1
            call = factory_calls
        if call == 2:
            second_factory_entered.set()
        return profile.id

    def replace_runtime(provider):
        if provider == "two":
            first_replace_entered.set()
            assert release_first_replace.wait(1)
        runtime["provider"] = provider

    subject = service(store, factory, replace_runtime, lambda: runtime["provider"])
    failures = []
    first = threading.Thread(target=lambda: _capture(failures, subject.activate, "two"))
    second = threading.Thread(target=lambda: _capture(failures, subject.activate, "one"))

    first.start()
    assert first_replace_entered.wait(1)
    second.start()
    assert not second_factory_entered.wait(0.05)
    release_first_replace.set()
    first.join(1)
    second.join(1)

    assert failures == []
    assert store.value.active_id == "one"
    assert runtime["provider"] == "one"


def _capture(failures, operation, *args):
    try:
        operation(*args)
    except Exception as exc:
        failures.append(exc)
