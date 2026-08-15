import pytest

from iris_agent.profile.models import ProfilePatch, UserProfile
from iris_agent.profile.repository import ProfileLedgerError, ProfileRepository


def test_load_returns_empty_when_missing(tmp_path):
    repo = ProfileRepository(tmp_path)

    profile = repo.load()

    assert profile.name == ""
    assert profile.preferences == []
    assert profile.goals == []
    assert profile.style == ""
    assert profile.facts == []
    assert profile.updated_at == ""


def test_save_and_load_roundtrip(tmp_path):
    repo = ProfileRepository(tmp_path)
    profile = UserProfile(
        name="小明",
        preferences=["简洁回答", "中文交流"],
        goals=["构建个人 agent"],
        style="直接务实",
        facts=["后端工程师"],
        updated_at="2026-08-15T00:00:00Z",
    )

    repo.save(profile)

    assert repo.load() == profile


def test_load_raises_on_invalid_json(tmp_path):
    repo = ProfileRepository(tmp_path)
    (tmp_path / "profile.json").write_text("not json", encoding="utf-8")

    with pytest.raises(ProfileLedgerError):
        repo.load()


def test_load_raises_on_wrong_shape(tmp_path):
    repo = ProfileRepository(tmp_path)
    (tmp_path / "profile.json").write_text('{"unexpected": true}', encoding="utf-8")

    with pytest.raises(ProfileLedgerError):
        repo.load()


def test_to_from_dict_roundtrip():
    profile = UserProfile(name="小明", preferences=["a"], goals=["b"], style="c", facts=["d"], updated_at="t")

    assert UserProfile.from_dict(profile.to_dict()) == profile


def test_patch_defaults_all_none():
    patch = ProfilePatch()

    assert patch.name is None
    assert patch.preferences is None
    assert patch.goals is None
    assert patch.style is None
    assert patch.facts is None
