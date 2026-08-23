from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from iris_agent.api.settings_api import register_settings_routes
from iris_agent.settings_profiles import ApiProfile, ProfileCollection, ProfileStore
from iris_agent.settings_profiles.service import ProfileService


def make_client(tmp_path):
    store = ProfileStore(tmp_path / "profiles.json", tmp_path / ".env")
    store.save(ProfileCollection(1, "one", (
        ApiProfile("one", "Default", "https://api.example/v1", "sk-secret-value", "model-a"),
    )))
    runtime = {"provider": object()}
    service = ProfileService(
        store, lambda p: SimpleNamespace(profile_id=p.id),
        lambda p: runtime.__setitem__("provider", p), lambda: runtime["provider"],
        client_factory=lambda **kwargs: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: object()))),
    )
    app = FastAPI()
    register_settings_routes(app, service)
    return TestClient(app), store, runtime


def test_profile_crud_activation_and_responses_never_expose_key(tmp_path):
    client, store, runtime = make_client(tmp_path)
    listed = client.get("/api/settings/profiles")
    assert listed.status_code == 200
    assert listed.json()["active_id"] == "one"
    assert "sk-secret-value" not in listed.text
    created = client.post("/api/settings/profiles", json={"name": "Second", "base_url": "https://two.example/v1", "model": "model-b", "api_key": "sk-two-secret"})
    assert created.status_code == 201
    profile_id = created.json()["id"]
    assert "sk-two-secret" not in created.text
    patched = client.patch(f"/api/settings/profiles/{profile_id}", json={"api_key": "", "name": "Renamed"})
    assert patched.json()["api_key_set"] is True
    cleared = client.patch(f"/api/settings/profiles/{profile_id}", json={"clear_api_key": True})
    assert cleared.json()["api_key_set"] is False
    activated = client.post(f"/api/settings/profiles/{profile_id}/activate")
    assert activated.status_code == 200
    assert runtime["provider"].profile_id == profile_id
    assert store.load().active_id == profile_id
    conflict = client.delete(f"/api/settings/profiles/{profile_id}")
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "profile_conflict"
    assert client.delete("/api/settings/profiles/one").status_code == 204


def test_connection_test_and_stable_errors_do_not_leak_payload(tmp_path):
    client, _, _ = make_client(tmp_path)
    result = client.post("/api/settings/profiles/test", json={"base_url": "https://api.example/v1", "model": "model-a", "api_key": "sk-never-return", "profile_id": "one"})
    assert result.json() == {"ok": True, "code": "connected", "message": "连接成功"}
    assert "sk-never-return" not in result.text
    missing = client.patch("/api/settings/profiles/missing", json={"name": "x"})
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "profile_not_found"
    invalid = client.post("/api/settings/profiles", json={"name": "x", "base_url": "file:///secret", "model": "m", "api_key": "sk-never-return"})
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "profile_validation"
    assert "sk-never-return" not in invalid.text


def test_connection_api_preserves_omitted_vs_explicit_empty_key(tmp_path, caplog):
    calls = []
    store = ProfileStore(tmp_path / "profiles.json", tmp_path / ".env")
    store.save(ProfileCollection(1, "one", (ApiProfile("one", "Default", "https://api.example/v1", "sk-stored-secret", "model-a"),)))
    service = ProfileService(store, lambda p: object(), lambda p: None, lambda: object(), client_factory=lambda **kwargs: (calls.append(kwargs) or SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: object())))))
    app = FastAPI(); register_settings_routes(app, service); client = TestClient(app)
    omitted = client.post("/api/settings/profiles/test", json={"base_url":"https://api.example/v1","model":"model-a","profile_id":"one"})
    explicit = client.post("/api/settings/profiles/test", json={"base_url":"https://api.example/v1","model":"model-a","api_key":"","profile_id":"one"})
    assert calls[0]["api_key"] == "sk-stored-secret"
    assert calls[1]["api_key"] == "local-no-key"
    assert "sk-stored-secret" not in omitted.text + explicit.text + caplog.text


def test_unavailable_service_returns_stable_500(caplog):
    class Unavailable:
        def list_state(self):
            raise RuntimeError("disk contained sk-secret")
    app = FastAPI()
    register_settings_routes(app, Unavailable())
    response = TestClient(app).get("/api/settings/profiles")
    assert response.status_code == 500
    assert response.json() == {"detail": {"code": "settings_store_unavailable", "message": "配置存储不可用"}}
    assert "sk-secret" not in response.text
    assert "sk-secret" not in caplog.text
    assert "Settings profile store unavailable" in caplog.text


def test_activation_failure_logs_only_fixed_safe_message(caplog):
    from iris_agent.settings_profiles.service import ProfileActivationError

    class FailingActivation:
        def activate(self, _):
            raise ProfileActivationError("provider rejected sk-secret")

    app = FastAPI()
    register_settings_routes(app, FailingActivation())
    response = TestClient(app).post("/api/settings/profiles/one/activate")
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "profile_activation_failed"
    assert "sk-secret" not in response.text
    assert "sk-secret" not in caplog.text
    assert "Settings profile activation failed" in caplog.text
