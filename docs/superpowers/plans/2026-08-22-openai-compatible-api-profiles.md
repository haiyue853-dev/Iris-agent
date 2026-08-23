# OpenAI 兼容 API 多配置档案实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将单一 LLM 设置改造成可保存、测试和即时切换多套 OpenAI 兼容 API 的配置档案。

**架构：** 新增独立的档案模型、原子 JSON 存储和业务服务，由设置 API 调用；运行时切换通过重新创建 Provider 并交给统一切换器完成。React 设置弹窗改成左侧档案列表、右侧编辑表单，保持现有黑白灰主题。

**技术栈：** Python 3、FastAPI、Pydantic、OpenAI Python SDK、pytest、React 19、TypeScript、Vitest、Testing Library、CSS。

**仓库说明：** 当前目录不是 Git 仓库，因此不能创建 worktree 或执行 commit。每个任务以测试通过作为可恢复检查点。

---

## 文件结构

- 创建 `iris_agent/settings_profiles/models.py`：档案与连接状态的数据模型。
- 创建 `iris_agent/settings_profiles/store.py`：迁移、校验、加锁和原子 JSON 存储。
- 创建 `iris_agent/settings_profiles/service.py`：CRUD、当前项约束、连接测试和运行时切换。
- 创建 `iris_agent/settings_profiles/__init__.py`：导出公开类型。
- 修改 `iris_agent/bootstrap.py`：创建档案服务和受控 Provider 切换器。
- 重写 `iris_agent/api/settings_api.py`：暴露多档案 HTTP API，不直接写 `.env`。
- 创建 `tests/settings_profiles/test_store.py`：存储、迁移、损坏恢复测试。
- 创建 `tests/settings_profiles/test_service.py`：业务约束、测试连接、切换测试。
- 修改 `tests/api/test_settings_api.py`：多档案 API、掩码和错误码测试。
- 修改 `web-react/src/types.ts`：前端档案与响应类型。
- 重写 `web-react/src/api/settings.ts`：多档案 API 客户端。
- 重写 `web-react/src/components/settings/SettingsModal.tsx`：档案列表和编辑表单。
- 修改 `web-react/src/App.css`：黑白灰双栏布局与响应式样式。
- 修改 `web-react/tests/SettingsModal.test.tsx`：交互、校验和状态测试。
- 修改 `.gitignore`：明确忽略本地档案文件。
- 创建 `data/settings_profiles.example.json`：不含密钥的示例结构。

### 任务 1：定义档案模型和原子存储

**文件：**
- 创建：`iris_agent/settings_profiles/models.py`
- 创建：`iris_agent/settings_profiles/store.py`
- 创建：`iris_agent/settings_profiles/__init__.py`
- 创建：`tests/settings_profiles/test_store.py`

- [ ] **步骤 1：编写失败的迁移与掩码测试**

```python
def test_load_migrates_env_once(tmp_path):
    env = tmp_path / ".env"
    env.write_text("OPENAI_API_KEY=sk-secret\nOPENAI_BASE_URL=https://api.example/v1\nLLM_MODEL=m1\n", encoding="utf-8")
    store = ProfileStore(tmp_path / "profiles.json", env)
    first = store.load()
    second = store.load()
    assert len(first.profiles) == len(second.profiles) == 1
    assert first.profiles[0].api_key == "sk-secret"
    assert first.active_id == first.profiles[0].id

def test_public_profile_never_exposes_key():
    profile = ApiProfile(id="p1", name="远程", base_url="https://api.example/v1", api_key="sk-secret", model="m1")
    assert profile.to_public()["api_key_set"] is True
    assert profile.to_public()["api_key_masked"].endswith("cret")
    assert "api_key" not in profile.to_public()
```

- [ ] **步骤 2：运行测试并确认因模块不存在而失败**

运行：`pytest tests/settings_profiles/test_store.py -v`

预期：FAIL，包含 `ModuleNotFoundError: iris_agent.settings_profiles`。

- [ ] **步骤 3：实现档案模型与存储格式**

```python
@dataclass(frozen=True, slots=True)
class ApiProfile:
    id: str
    name: str
    base_url: str
    api_key: str
    model: str
    last_test_status: str = "untested"
    last_tested_at: str | None = None

@dataclass(frozen=True, slots=True)
class ProfileCollection:
    version: int
    active_id: str
    profiles: Sequence[ApiProfile]
```

`ProfileStore.load()` 在目标文件不存在时从 `.env` 创建唯一默认档案；`save()` 在同目录写入 `profiles.json.tmp`、flush、`os.fsync()` 后调用 `os.replace()`。实例内使用 `threading.RLock` 串行化读取和写入。损坏 JSON 抛出 `ProfileStoreError`，不重写原文件。

- [ ] **步骤 4：补充原子写入失败和损坏文件测试**

```python
def test_failed_replace_keeps_original(tmp_path, monkeypatch):
    store = seeded_store(tmp_path)
    before = store.path.read_text(encoding="utf-8")
    monkeypatch.setattr(os, "replace", Mock(side_effect=OSError("disk full")))
    with pytest.raises(ProfileStoreError):
        store.save(changed_collection())
    assert store.path.read_text(encoding="utf-8") == before

def test_corrupt_json_is_not_overwritten(tmp_path):
    path = tmp_path / "profiles.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(ProfileStoreError):
        ProfileStore(path, tmp_path / ".env").load()
    assert path.read_text(encoding="utf-8") == "{broken"
```

- [ ] **步骤 5：运行存储测试**

运行：`pytest tests/settings_profiles/test_store.py -v`

预期：全部 PASS。

### 任务 2：实现档案业务服务与安全的运行时切换

**文件：**
- 创建：`iris_agent/settings_profiles/service.py`
- 修改：`iris_agent/core/agent_loop.py`
- 创建：`tests/settings_profiles/test_service.py`
- 修改：`tests/core/test_agent_loop.py`

- [ ] **步骤 1：编写 CRUD 约束测试**

```python
def test_cannot_delete_active_profile(service):
    active_id = service.list_public()["active_id"]
    with pytest.raises(ProfileConflictError, match="当前配置"):
        service.delete(active_id)

def test_switch_rebuilds_provider_before_persisting(service, provider_factory):
    target = service.create(ProfileInput(name="本地", base_url="http://localhost:11434/v1", api_key="", model="qwen3:8b"))
    service.activate(target.id)
    assert service.active_id == target.id
    assert provider_factory.calls[-1].model == "qwen3:8b"
```

- [ ] **步骤 2：运行并确认业务服务测试失败**

运行：`pytest tests/settings_profiles/test_service.py -v`

预期：FAIL，包含 `ImportError` 或缺少 `ProfileService`。

- [ ] **步骤 3：实现业务接口和 Provider 工厂**

```python
class ProfileService:
    def list_public(self) -> dict:
        collection = self.store.load()
        return {"active_id": collection.active_id, "profiles": [item.to_public() for item in collection.profiles]}

    def activate(self, profile_id: str) -> ApiProfile:
        before = self.store.load()
        profile = self._require_profile(before, profile_id)
        replacement = self.provider_factory(profile)
        changed = replace(before, active_id=profile.id)
        self.store.save(changed)
        try:
            self.replace_provider(replacement)
        except Exception:
            self.store.save(before)
            raise
        return profile
```

`create()` 生成 UUID 并追加档案，`update()` 合并允许修改的字段，`delete()` 拒绝当前档案或最后一套档案，`test_connection()` 返回稳定结果对象。Provider 工厂固定使用 `OpenAI(api_key=profile.api_key or "local-no-key", base_url=profile.base_url, timeout=timeout)`，随后创建 `OpenAICompatibleProvider`。`activate()` 必须先成功创建 Provider，再保存 `active_id`，最后调用运行时切换器；任何一步失败均恢复旧集合和旧 Provider。

- [ ] **步骤 4：让 AgentLoop 按请求快照 Provider**

在 `run()` 与 `stream()` 的请求入口先读取 `provider = self.provider`，本次请求后续所有模型轮次使用该局部引用；新增线程安全的 `replace_provider(provider)`。测试用阻塞 FakeProvider 证明切换后旧请求继续使用旧实例，新请求使用新实例。

- [ ] **步骤 5：运行相关测试**

运行：`pytest tests/settings_profiles/test_service.py tests/core/test_agent_loop.py -v`

预期：全部 PASS。

### 任务 3：实现短连接测试与稳定错误分类

**文件：**
- 修改：`iris_agent/settings_profiles/service.py`
- 修改：`tests/settings_profiles/test_service.py`

- [ ] **步骤 1：编写空 Key、超时及上游错误映射测试**

```python
@pytest.mark.parametrize((error, code), [
    (AuthenticationError("bad", response=response_401(), body=None), "authentication_failed"),
    (NotFoundError("missing", response=response_404(), body=None), "model_unavailable"),
    (APITimeoutError(request=request()), "connection_timeout"),
    (APIConnectionError(request=request()), "connection_failed"),
])
def test_connection_error_mapping(service, fake_openai, error, code):
    fake_openai.error = error
    result = service.test_connection(local_or_remote_input())
    assert result.code == code
    assert "sk-secret" not in result.message
```

- [ ] **步骤 2：运行并确认未实现分类时失败**

运行：`pytest tests/settings_profiles/test_service.py -k connection -v`

预期：FAIL，实际错误码与期望不一致。

- [ ] **步骤 3：实现连接测试**

连接测试使用 10 秒超时，调用 `chat.completions.create(model=value.model, messages=[{"role": "user", "content": "Hi"}], max_tokens=1)`；若兼容服务拒绝 `max_tokens`，不进行第二次昂贵请求，直接归类为 `provider_error`。测试完成后只持久化 `connected`、`failed` 或 `untested` 以及 UTC ISO 时间，不保存上游正文。

- [ ] **步骤 4：运行连接测试**

运行：`pytest tests/settings_profiles/test_service.py -k connection -v`

预期：全部 PASS，且日志捕获中不含测试 Key。

### 任务 4：接入启动流程并重写设置 API

**文件：**
- 修改：`iris_agent/bootstrap.py`
- 重写：`iris_agent/api/settings_api.py`
- 修改：`tests/api/test_settings_api.py`
- 修改：`tests/test_bootstrap.py`

- [ ] **步骤 1：编写多档案 API 失败测试**

```python
def test_profile_crud_and_activation(client):
    created = client.post("/api/settings/profiles", json={
        "name": "Ollama", "base_url": "http://localhost:11434/v1", "api_key": "", "model": "qwen3:8b"
    })
    assert created.status_code == 201
    profile_id = created.json()["id"]
    activated = client.post(f"/api/settings/profiles/{profile_id}/activate")
    assert activated.status_code == 200
    assert client.get("/api/settings/profiles").json()["active_id"] == profile_id
    assert "api_key" not in created.json()
```

- [ ] **步骤 2：运行并确认路由不存在**

运行：`pytest tests/api/test_settings_api.py -v`

预期：FAIL，新增端点返回 404。

- [ ] **步骤 3：定义 HTTP 请求模型与路由**

实现：

```text
GET    /api/settings/profiles
POST   /api/settings/profiles
PATCH  /api/settings/profiles/{profile_id}
DELETE /api/settings/profiles/{profile_id}
POST   /api/settings/profiles/{profile_id}/activate
POST   /api/settings/profiles/test
```

名称与模型 trim 后必须非空；Base URL 只允许完整 `http`/`https` 地址；PATCH 中空 `api_key` 表示保留旧值，显式 `clear_api_key: true` 才清除已有 Key。冲突返回 409，不存在返回 404，格式错误返回 422，存储失败返回 500，所有响应使用稳定 `detail.code`。

- [ ] **步骤 4：在 bootstrap 创建服务**

使用 `data/settings_profiles.json` 和项目 `.env` 创建 `ProfileStore`。若档案存储有效，则用当前档案构造初始 Provider；若读取失败，记录不含敏感值的错误并使用现有 `settings.llm` 回退。将 `ProfileService` 放入 `ApplicationServices` 并传给 `register_settings_routes`。

- [ ] **步骤 5：运行 API 与启动测试**

运行：`pytest tests/api/test_settings_api.py tests/test_bootstrap.py tests/test_bootstrap_services.py -v`

预期：全部 PASS。

### 任务 5：更新前端类型与 API 客户端

**文件：**
- 修改：`web-react/src/types.ts`
- 重写：`web-react/src/api/settings.ts`
- 创建：`web-react/src/api/settings.test.ts`

- [ ] **步骤 1：编写请求路径和错误解析测试**

```typescript
it('activates one profile', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(okJson(profileState)));
  await activateSettingsProfile('p2');
  expect(fetch).toHaveBeenCalledWith(
    'http://localhost:8000/api/settings/profiles/p2/activate',
    expect.objectContaining({ method: 'POST' }),
  );
});
```

- [ ] **步骤 2：运行并确认缺少新函数**

运行：`cd web-react; npm test -- src/api/settings.test.ts`

预期：FAIL，TypeScript 报 `activateSettingsProfile` 未导出。

- [ ] **步骤 3：定义严格类型和 API 函数**

```typescript
export type ApiProfile = {
  id: string; name: string; base_url: string; model: string;
  api_key_set: boolean; api_key_masked: string;
  last_test_status: 'untested' | 'connected' | 'failed';
  last_tested_at: string | null;
};
export type SettingsProfilesState = { active_id: string; profiles: ApiProfile[] };
```

API 模块导出 `fetchSettingsProfiles`、`createSettingsProfile`、`updateSettingsProfile`、`deleteSettingsProfile`、`activateSettingsProfile` 和 `testSettingsProfileConnection`，统一通过 `checked()` 提取 `detail.message`。

- [ ] **步骤 4：运行 API 客户端测试**

运行：`cd web-react; npm test -- src/api/settings.test.ts`

预期：全部 PASS。

### 任务 6：重构设置弹窗为多档案界面

**文件：**
- 重写：`web-react/src/components/settings/SettingsModal.tsx`
- 修改：`web-react/tests/SettingsModal.test.tsx`

- [ ] **步骤 1：编写列表、切换、空 Key 与删除限制测试**

```typescript
it('switches profile and refreshes the active marker', async () => {
  render(<SettingsModal onClose={() => undefined} />);
  await userEvent.click(await screen.findByRole('button', { name: /Ollama/ }));
  await userEvent.click(screen.getByRole('button', { name: '保存并设为当前' }));
  expect(api.activateSettingsProfile).toHaveBeenCalledWith('p2');
  expect(await screen.findByText('当前配置')).toBeInTheDocument();
});

it('keeps an existing key when the password input is blank', async () => {
  render(<SettingsModal onClose={() => undefined} />);
  await userEvent.click(await screen.findByRole('button', { name: '保存' }));
  expect(api.updateSettingsProfile).toHaveBeenCalledWith('p1', expect.not.objectContaining({ api_key: '' }));
});
```

- [ ] **步骤 2：运行并确认旧单表单界面失败**

运行：`cd web-react; npm test -- tests/SettingsModal.test.tsx`

预期：FAIL，找不到档案列表和“保存并设为当前”。

- [ ] **步骤 3：实现状态与交互**

组件维护 `state`、`selectedId`、`draft`、`isCreating`、`saving`、`testing` 和消息状态。选择列表项载入对应草稿；有未保存修改时切换列表项不静默覆盖，而是在当前表单上显示“请先保存或取消修改”。新建默认草稿为名称空、Base URL 空、Key 空、模型空。

- [ ] **步骤 4：实现保存、测试、激活和删除语义**

保存成功后用服务端响应替换本地档案；“保存并设为当前”先保存再激活。测试使用当前草稿值。删除按钮仅在非当前档案且档案数量大于一时启用。API Key 留空不进入更新 payload；单独的“清除已保存 Key”操作发送 `clear_api_key: true`。

- [ ] **步骤 5：运行组件测试**

运行：`cd web-react; npm test -- tests/SettingsModal.test.tsx`

预期：全部 PASS。

### 任务 7：实现黑白灰样式和响应式布局

**文件：**
- 修改：`web-react/src/App.css`
- 创建：`web-react/tests/SettingsProfiles.theme.test.ts`

- [ ] **步骤 1：编写主题约束测试**

```typescript
it('uses grayscale status styles and responsive layout', () => {
  const css = readFileSync(resolve('src/App.css'), 'utf8');
  const block = css.slice(css.indexOf('/* ========== 设置弹窗 ========== */'));
  expect(block).toContain('.settings-profiles-layout');
  expect(block).toContain('@media (max-width: 700px)');
  expect(block).not.toMatch(/#(?:1a7f37|b3551a|e6f6ea|fdf0e3)/i);
});
```

- [ ] **步骤 2：运行并确认现有彩色状态导致失败**

运行：`cd web-react; npm test -- tests/SettingsProfiles.theme.test.ts`

预期：FAIL，检测到绿色和橙色状态色。

- [ ] **步骤 3：实现双栏灰阶样式**

弹窗桌面宽度约 760px，列表栏约 220px；边框使用现有 `#e8e8ea`，当前项使用 `#1d1c23` 文本和浅灰背景，成功/失败依赖图标与“连接成功/连接失败”文字。小于 700px 时切为单栏，列表横向滚动，按钮允许换行，输入框保持全宽。

- [ ] **步骤 4：运行主题与组件测试**

运行：`cd web-react; npm test -- tests/SettingsProfiles.theme.test.ts tests/SettingsModal.test.tsx`

预期：全部 PASS。

### 任务 8：敏感文件规则、全量回归和浏览器验收

**文件：**
- 修改：`.gitignore`
- 创建：`data/settings_profiles.example.json`

- [ ] **步骤 1：添加明确忽略规则和无密钥示例**

`.gitignore` 加入 `data/settings_profiles.json`；示例文件只包含 `api_key: ""`，并包含一个远程和一个本地档案示例，但只有一个 `active_id`。

- [ ] **步骤 2：运行后端全量测试**

运行：`pytest -q`

预期：所有测试通过，仅允许项目已有且与本功能无关的 skip。

- [ ] **步骤 3：运行前端全量测试、构建和 lint**

运行：`cd web-react; npm test`

预期：全部 PASS。

运行：`cd web-react; npm run build`

预期：退出码 0。

运行：`cd web-react; npm run lint`

预期：退出码 0；若存在修改前已有警告，记录其数量并确认未增加。

- [ ] **步骤 4：本地浏览器验收**

启动后端和 Vite 页面，完成以下流程：从旧 `.env` 看到“默认配置”；新增一个 API Key 为空的 Ollama 档案；新增一个远程档案但不显示 Key 明文；分别测试连接；在两套档案间切换；发送新聊天确认使用当前模型；切换期间已有流式回答不中断；窄屏下表单仍可输入且无横向溢出。

- [ ] **步骤 5：记录验证证据**

在任务交付说明中记录后端测试通过数、前端测试通过数、build/lint 退出码，以及浏览器验收的配置切换结果；不得粘贴 `.env`、档案 JSON 或任何 Key。
