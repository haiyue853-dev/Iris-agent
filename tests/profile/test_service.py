from iris_agent.profile.extractor import ProfileExtractor
from iris_agent.profile.models import ProfilePatch
from iris_agent.profile.repository import ProfileRepository
from iris_agent.profile.service import ProfileService


class FakeExtractor:
    def __init__(self, patch: ProfilePatch):
        self.patch = patch
        self.calls = 0

    def extract(self, dialogue: str) -> ProfilePatch:
        self.calls += 1
        return self.patch


def _service(tmp_path, patch, **kwargs) -> ProfileService:
    repo = ProfileRepository(tmp_path)
    extractor = FakeExtractor(patch)
    defaults = dict(extract_interval_rounds=10)
    defaults.update(kwargs)
    return ProfileService(repo, extractor, **defaults)


def test_apply_patch_merges_into_empty_profile(tmp_path):
    service = _service(tmp_path, ProfilePatch())

    service.apply_patch(ProfilePatch(name="小明", preferences=["简洁回答"]))

    profile = service.get()
    assert profile.name == "小明"
    assert profile.preferences == ["简洁回答"]


def test_apply_patch_deduplicates(tmp_path):
    service = _service(tmp_path, ProfilePatch())
    service.apply_patch(ProfilePatch(facts=["后端工程师"]))
    service.apply_patch(ProfilePatch(facts=["后端工程师", "喜欢 Go"]))

    assert service.get().facts == ["后端工程师", "喜欢 Go"]


def test_apply_patch_truncates_items(tmp_path):
    service = _service(tmp_path, ProfilePatch(), max_item_chars=5)

    service.apply_patch(ProfilePatch(facts=["这是一个很长的事实条目"]))

    assert service.get().facts == ["这是一个很"]


def test_apply_patch_caps_list_length(tmp_path):
    service = _service(tmp_path, ProfilePatch(), max_items_per_field=2)

    service.apply_patch(ProfilePatch(preferences=["a", "b", "c"]))

    assert service.get().preferences == ["a", "b"]


def test_render_formats_profile(tmp_path):
    service = _service(tmp_path, ProfilePatch())
    service.apply_patch(ProfilePatch(name="小明", preferences=["简洁"], style="直接"))

    text = service.render()

    assert "称呼：小明" in text
    assert "偏好：简洁" in text
    assert "风格：直接" in text


def test_render_empty_profile_returns_empty(tmp_path):
    service = _service(tmp_path, ProfilePatch())

    assert service.render() == ""


def test_maybe_update_extracts_on_empty_profile(tmp_path):
    service = _service(tmp_path, ProfilePatch(name="小明"))

    result = service.maybe_update("用户：我叫小明")

    assert result is True
    assert service.get().name == "小明"


def test_maybe_update_throttles(tmp_path):
    service = _service(tmp_path, ProfilePatch(facts=["工程师"]), extract_interval_rounds=3)

    service.maybe_update("第一轮")  # 画像空 → 提取
    service.maybe_update("第二轮")  # 1 < 3
    service.maybe_update("第三轮")  # 2 < 3
    assert service.get().facts == ["工程师"]
    # 用 calls 验证节流（FakeExtractor 记录次数）
    extractor = service.extractor
    assert extractor.calls == 1

    service.maybe_update("第四轮")  # 3 >= 3 → 提取
    assert extractor.calls == 2


def test_maybe_update_disabled_skips(tmp_path):
    service = _service(tmp_path, ProfilePatch(name="小明"), enabled=False)

    result = service.maybe_update("用户：我叫小明")

    assert result is False
    assert service.get().name == ""
    assert service.extractor.calls == 0
