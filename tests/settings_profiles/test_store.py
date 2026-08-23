import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from iris_agent.settings_profiles import (
    ApiProfile,
    MigrationDefaults,
    ProfileCollection,
    ProfileStore,
    ProfileStoreError,
)


def profile(**changes):
    value = ApiProfile("one", " Main ", " https://api.example/v1 ", "sk-secret-value", " model-a ")
    return replace(value, **changes)


def collection(*profiles, active_id="one"):
    return ProfileCollection(version=1, active_id=active_id, profiles=profiles or (profile(),))


def test_load_migrates_env_once_and_marks_profile_active(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "# local only\nOPENAI_API_KEY=sk-migrated-secret\n"
        "OPENAI_BASE_URL=https://api.example/v1\nLLM_MODEL=model-a\n",
        encoding="utf-8",
    )
    store = ProfileStore(tmp_path / "profiles.json", env_path)

    first = store.load()
    second = store.load()

    assert first == second
    assert len(first.profiles) == 1
    assert first.active_id == first.profiles[0].id
    assert first.profiles[0].name == "默认配置"
    assert first.profiles[0].api_key == "sk-migrated-secret"
    assert json.loads((tmp_path / "profiles.json").read_text(encoding="utf-8"))["profiles"] == [
        {
            "id": first.active_id,
            "name": "默认配置",
            "base_url": "https://api.example/v1",
            "api_key": "sk-migrated-secret",
            "model": "model-a",
            "last_test_status": "untested",
            "last_tested_at": None,
        }
    ]


def test_load_without_env_uses_explicit_migration_defaults_once(tmp_path):
    store = ProfileStore(
        tmp_path / "profiles.json",
        tmp_path / ".env",
        MigrationDefaults("https://fallback.example/v1", "fallback-model", "fallback-key"),
    )

    first = store.load()
    second = store.load()

    assert second == first
    assert first.profiles[0].base_url == "https://fallback.example/v1"
    assert first.profiles[0].model == "fallback-model"
    assert first.profiles[0].api_key == "fallback-key"


def test_load_merges_partial_env_with_defaults_field_by_field(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "OPENAI_API_KEY=env-key\nOPENAI_BASE_URL=   \n",
        encoding="utf-8",
    )
    store = ProfileStore(
        tmp_path / "profiles.json",
        env_path,
        MigrationDefaults("https://fallback.example/v1", "fallback-model", "fallback-key"),
    )

    migrated = store.load().profiles[0]

    assert migrated.base_url == "https://fallback.example/v1"
    assert migrated.model == "fallback-model"
    assert migrated.api_key == "env-key"


@pytest.mark.parametrize(
    ("key", "masked"),
    [("", ""), ("short", "*****"), ("sk-123456789", "sk-****6789")],
)
def test_public_profile_never_exposes_api_key(key, masked):
    public = profile(api_key=key).to_public()

    assert "api_key" not in public
    assert public["api_key_set"] is bool(key)
    assert public["api_key_masked"] == masked


@pytest.mark.parametrize(
    "value",
    [
        ProfileCollection(1, "", (profile(),)),
        ProfileCollection(1, "missing", (profile(),)),
        ProfileCollection(1, "one", ()),
        ProfileCollection(1, "one", (profile(), profile(name="Other"))),
        ProfileCollection(1, "one", (profile(name="   "),)),
        ProfileCollection(1, "one", (profile(base_url="   "),)),
        ProfileCollection(1, "one", (profile(model="   "),)),
        ProfileCollection(1, "one", (profile(id="   "),)),
    ],
)
def test_save_rejects_invalid_collections(tmp_path, value):
    store = ProfileStore(tmp_path / "profiles.json", tmp_path / ".env")

    with pytest.raises(ProfileStoreError):
        store.save(value)


def test_save_trims_required_strings_but_allows_empty_key(tmp_path):
    store = ProfileStore(tmp_path / "profiles.json", tmp_path / ".env")
    saved = store.save(collection(profile(api_key="", last_test_status=" connected ")))

    assert saved.profiles[0] == ApiProfile(
        "one", "Main", "https://api.example/v1", "", "model-a", "connected", None
    )
    assert store.load() == saved


def test_corrupt_json_raises_without_overwriting_source(tmp_path):
    path = tmp_path / "profiles.json"
    original = "{broken secret-content"
    path.write_text(original, encoding="utf-8")

    with pytest.raises(ProfileStoreError, match="read"):
        ProfileStore(path, tmp_path / ".env").load()

    assert path.read_text(encoding="utf-8") == original


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload.update(active_id=123),
        lambda payload: payload["profiles"][0].update(name=123),
    ],
)
def test_invalid_json_field_types_raise_store_error_without_overwriting(tmp_path, mutation):
    path = tmp_path / "profiles.json"
    payload = {
        "version": 1,
        "active_id": "one",
        "profiles": [
            {
                "id": "one",
                "name": "Main",
                "base_url": "https://api.example/v1",
                "api_key": "secret-value",
                "model": "model-a",
            }
        ],
    }
    mutation(payload)
    original = json.dumps(payload)
    path.write_text(original, encoding="utf-8")

    with pytest.raises(ProfileStoreError):
        ProfileStore(path, tmp_path / ".env").load()

    assert path.read_text(encoding="utf-8") == original


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload.update(version=2),
        lambda payload: payload.update(version=True),
        lambda payload: payload["profiles"][0].update(api_key=123),
        lambda payload: payload["profiles"][0].update(last_tested_at=[]),
        lambda payload: payload["profiles"][0].update(last_test_status="unknown"),
    ],
)
def test_unsupported_or_invalid_json_fields_raise_store_error(tmp_path, mutation):
    path = tmp_path / "profiles.json"
    payload = {
        "version": 1,
        "active_id": "one",
        "profiles": [
            {
                "id": "one",
                "name": "Main",
                "base_url": "https://api.example/v1",
                "api_key": "",
                "model": "model-a",
                "last_test_status": "untested",
                "last_tested_at": None,
            }
        ],
    }
    mutation(payload)
    original = json.dumps(payload)
    path.write_text(original, encoding="utf-8")

    with pytest.raises(ProfileStoreError):
        ProfileStore(path, tmp_path / ".env").load()
    assert path.read_text(encoding="utf-8") == original


def test_save_non_string_field_raises_store_error(tmp_path):
    store = ProfileStore(tmp_path / "profiles.json", tmp_path / ".env")

    with pytest.raises(ProfileStoreError):
        store.save(collection(profile(name=123)))


def test_serialization_failure_preserves_target_and_cleans_temp(tmp_path, monkeypatch):
    path = tmp_path / "profiles.json"
    original = '{"old": true}'
    path.write_text(original, encoding="utf-8")
    store = ProfileStore(path, tmp_path / ".env")

    def fail_dump(*args, **kwargs):
        raise TypeError("cannot serialize secret-value")

    monkeypatch.setattr("iris_agent.settings_profiles.store.json.dump", fail_dump)
    with pytest.raises(ProfileStoreError) as error:
        store.save(collection())

    assert "secret-value" not in str(error.value)
    assert path.read_text(encoding="utf-8") == original
    assert list(tmp_path.glob(".*.tmp")) == []


def test_replace_failure_preserves_target_cleans_temp_and_hides_key(tmp_path, monkeypatch):
    path = tmp_path / "profiles.json"
    path.write_text('{"old": true}', encoding="utf-8")
    store = ProfileStore(path, tmp_path / ".env")

    def fail_replace(source, target):
        raise OSError("replace denied")

    monkeypatch.setattr("iris_agent.settings_profiles.store.os.replace", fail_replace)
    with pytest.raises(ProfileStoreError) as error:
        store.save(collection())

    assert "sk-secret-value" not in str(error.value)
    assert path.read_text(encoding="utf-8") == '{"old": true}'
    assert list(tmp_path.glob(".*.tmp")) == []
