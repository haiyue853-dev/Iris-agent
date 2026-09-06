# 自定义 Skill 编写实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 在 Skills 中心让用户安全地创建、编辑、启用、停用和删除提示词型自定义 Skill。

**架构：** 继续使用 `SkillCenterService` 作为唯一持久化边界；FastAPI 将用户 Skill 的受控读取、保存和删除能力暴露为 API。React 的 `useSkills` 负责数据加载与写操作，`SkillsPage` 将 Skill 按来源分组，并使用内嵌编辑器管理用户 Skill。

**技术栈：** Python 3.14、FastAPI、Pydantic、pytest、React 19、TypeScript、Vitest、Testing Library。

---

## 文件结构

- 修改：`iris_agent/skill_center/service.py` — 增加用户 Skill 的安全读取与按 ID 更新入口。
- 修改：`iris_agent/api/skills_schemas.py` — 定义用户 Skill 创建/编辑请求和可编辑内容响应。
- 修改：`iris_agent/api/skills_api.py` — 注册用户 Skill 的读取、保存和删除路由并返回稳定错误。
- 修改：`tests/skill_center/test_user_skills.py` — 覆盖只允许用户 Skill 编辑及正文读取。
- 修改：`tests/api/test_skills.py` — 覆盖 API 保存、读取、删除和内置保护。
- 修改：`web-react/src/types.ts` — 在前端 Skill 元数据中加入 `source`。
- 修改：`web-react/src/api/skills.ts` — 增加自定义 Skill API 客户端和请求/响应类型。
- 修改：`web-react/src/hooks/useSkills.ts` — 增加保存、加载正文和删除的状态与错误处理。
- 修改：`web-react/src/components/skills/SkillCard.tsx` — 仅为用户 Skill 显示编辑和删除操作。
- 创建：`web-react/src/components/skills/UserSkillEditor.tsx` — 内嵌 Skill 编辑器，管理名称、说明、正文与保存状态。
- 修改：`web-react/src/components/skills/SkillsPage.tsx` — 分组渲染内置/我的 Skills，编排编辑器与删除确认。
- 修改：`web-react/src/components/skills/SkillsPage.test.tsx` — 验证编辑器、用户操作入口与内置 Skill 边界。
- 修改：`web-react/src/App.css` — 为编辑器和分组增加既有 OpenCode 风格样式。

## 任务 1：定义用户 Skill 服务边界

**文件：**
- 修改：`tests/skill_center/test_user_skills.py`
- 修改：`iris_agent/skill_center/service.py`

- [ ] **步骤 1：编写失败的服务测试**

```python
def test_load_user_skill_returns_editable_body(tmp_path):
    service = _build_service(tmp_path)
    created = service.save_user_skill("我的技能", "描述", "第一版")

    loaded = service.load_user_skill(created.id)

    assert loaded.id == created.id
    assert loaded.source == "user"
    assert loaded.body == "第一版"


def test_load_user_skill_rejects_bundled_skill(tmp_path):
    service = _build_service(tmp_path)

    with pytest.raises(ValueError, match="不能编辑内置 Skill"):
        service.load_user_skill("daily-report")
```

- [ ] **步骤 2：运行测试验证失败**

运行：`$env:PYTHONPATH='D:\agent\Iris-agent'; pytest tests/skill_center/test_user_skills.py -q --basetemp .tmp\pytest-skill-service`

预期：FAIL，提示 `SkillCenterService` 没有 `load_user_skill`。

- [ ] **步骤 3：实现最少服务代码**

在 `SkillCenterService` 中增加只允许 `source == "user"` 的方法：

```python
def load_user_skill(self, skill_id: str) -> SkillDefinition:
    definition = self._lookup(skill_id)
    if definition.source != "user":
        raise ValueError("不能编辑内置 Skill")
    return definition
```

并让 `delete_user_skill` 调用该方法，避免两处权限判断漂移：

```python
definition = self.load_user_skill(skill_id)
directory = self.user_directory / definition.id
```

- [ ] **步骤 4：运行服务测试验证通过**

运行：`$env:PYTHONPATH='D:\agent\Iris-agent'; pytest tests/skill_center/test_user_skills.py -q --basetemp .tmp\pytest-skill-service`

预期：PASS。

## 任务 2：开放受控的用户 Skill API

**文件：**
- 修改：`tests/api/test_skills.py`
- 修改：`iris_agent/api/skills_schemas.py`
- 修改：`iris_agent/api/skills_api.py`

- [ ] **步骤 1：编写失败的 API 测试**

在 `_client` 中传入 `user_directory=tmp_path / "user-skills"`，并新增：

```python
def test_user_skill_can_be_created_read_and_deleted(tmp_path):
    client = _client(tmp_path)
    created = client.post("/api/skills/user", json={
        "name": "会议整理",
        "description": "整理会议记录",
        "content": "把输入按结论、行动项整理。",
    })
    assert created.status_code == 201
    skill_id = created.json()["id"]

    loaded = client.get(f"/api/skills/{skill_id}/content")
    assert loaded.status_code == 200
    assert loaded.json()["content"] == "把输入按结论、行动项整理。"

    deleted = client.delete(f"/api/skills/user/{skill_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/skills/{skill_id}").status_code == 404


def test_user_skill_api_rejects_bundled_content_and_delete(tmp_path):
    client = _client(tmp_path)
    assert client.get("/api/skills/daily-report/content").status_code == 403
    assert client.delete("/api/skills/user/daily-report").status_code == 403
```

- [ ] **步骤 2：运行 API 测试验证失败**

运行：`$env:PYTHONPATH='D:\agent\Iris-agent'; pytest tests/api/test_skills.py -q --basetemp .tmp\pytest-skills-api`

预期：FAIL，`POST /api/skills/user` 返回 404。

- [ ] **步骤 3：定义请求与内容响应模型**

在 `iris_agent/api/skills_schemas.py` 添加：

```python
class UserSkillSaveRequest(BaseModel):
    name: str
    description: str
    content: str


class UserSkillContentModel(SkillInfoModel):
    source: str
    content: str
```

同时为 `SkillInfoModel` 添加 `source: str`，让前端能区分内置与用户 Skill。

- [ ] **步骤 4：实现最少路由与受控错误转换**

在 `register_skills_routes` 中添加：

```python
@app.post("/api/skills/user", status_code=201)
def save_user_skill(request: UserSkillSaveRequest):
    try:
        definition = skills.save_user_skill(request.name, request.description, request.content)
        return _to_model(skills.get_skill(definition.id)).model_dump()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": "invalid_user_skill", "message": str(exc)}) from exc
```

并为 `GET /api/skills/{skill_id}/content` 与 `DELETE /api/skills/user/{skill_id}` 调用 `load_user_skill` / `delete_user_skill`；对内置 Skill 返回 `403`，未知 Skill 返回现有 `404`，不返回文件系统路径。

- [ ] **步骤 5：运行 API 测试验证通过**

运行：`$env:PYTHONPATH='D:\agent\Iris-agent'; pytest tests/api/test_skills.py -q --basetemp .tmp\pytest-skills-api`

预期：PASS。

## 任务 3：建立前端数据访问与 Hook 操作

**文件：**
- 修改：`web-react/src/api/skills.ts`
- 修改：`web-react/src/hooks/useSkills.ts`
- 修改：`web-react/src/types.ts`
- 创建：`web-react/src/api/skills.user.test.ts`

- [ ] **步骤 1：编写失败的 API 客户端测试**

```ts
it("posts custom Skill fields and returns its metadata", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
    id: "meeting-notes-a1b2c3", name: "会议整理", description: "整理会议记录",
    icon: "sparkles", category: "custom", entry_view: "chat", version: 1,
    enabled: true, source: "user",
  }), { status: 201 })));

  await saveUserSkill({ name: "会议整理", description: "整理会议记录", content: "整理输入" });

  expect(fetch).toHaveBeenCalledWith(
    "http://localhost:8000/api/skills/user",
    expect.objectContaining({ method: "POST" }),
  );
});
```

- [ ] **步骤 2：运行测试验证失败**

运行：`npm test -- src/api/skills.user.test.ts`

预期：FAIL，`saveUserSkill` 尚未导出。

- [ ] **步骤 3：实现 API 客户端与 Hook 方法**

在 `web-react/src/api/skills.ts` 添加：

```ts
export type UserSkillDraft = { name: string; description: string; content: string };
export type UserSkillContent = SkillInfo & { source: "user"; content: string };

export async function saveUserSkill(draft: UserSkillDraft): Promise<SkillInfo> { /* POST */ }
export async function fetchUserSkillContent(id: string): Promise<UserSkillContent> { /* GET content */ }
export async function deleteUserSkill(id: string): Promise<void> { /* DELETE */ }
```

在 `useSkills` 添加 `saveUserSkill`、`loadUserSkillContent`、`removeUserSkill`。保存使用返回的 Skill 按 ID 替换或追加，删除按 ID 过滤；失败写入既有 `error` 状态。

- [ ] **步骤 4：运行 API 客户端测试验证通过**

运行：`npm test -- src/api/skills.user.test.ts`

预期：PASS。

## 任务 4：实现内嵌 Skill 编辑器与卡片操作

**文件：**
- 创建：`web-react/src/components/skills/UserSkillEditor.tsx`
- 修改：`web-react/src/components/skills/SkillCard.tsx`
- 修改：`web-react/src/components/skills/SkillsPage.tsx`
- 修改：`web-react/src/components/skills/SkillsPage.test.tsx`
- 修改：`web-react/src/App.css`

- [ ] **步骤 1：编写失败的页面测试**

```tsx
it("saves a new custom Skill from the inline editor", async () => {
  render(<SkillsPage onNavigate={vi.fn()} />);
  await userEvent.click(await screen.findByRole("button", { name: "新建 Skill" }));
  await userEvent.type(screen.getByLabelText("Skill 名称"), "会议整理");
  await userEvent.type(screen.getByLabelText("用途说明"), "整理会议记录");
  await userEvent.type(screen.getByLabelText("Skill 正文"), "输出行动项");
  await userEvent.click(screen.getByRole("button", { name: "保存 Skill" }));
  expect(mockSaveUserSkill).toHaveBeenCalledWith({
    name: "会议整理", description: "整理会议记录", content: "输出行动项",
  });
});


it("only shows edit and delete actions for a user Skill", async () => {
  render(<SkillsPage onNavigate={vi.fn()} />);
  expect(await screen.findByRole("button", { name: "编辑 我的 Skill" })).toBeVisible();
  expect(screen.queryByRole("button", { name: "编辑 内置 Skill" })).toBeNull();
});
```

- [ ] **步骤 2：运行页面测试验证失败**

运行：`npm test -- src/components/skills/SkillsPage.test.tsx`

预期：FAIL，找不到“新建 Skill”按钮和用户操作入口。

- [ ] **步骤 3：实现编辑器与页面编排**

创建 `UserSkillEditor`，Props 使用：

```ts
type UserSkillEditorProps = {
  initialValue?: { id?: string; name: string; description: string; content: string };
  saving: boolean;
  onSave: (draft: UserSkillDraft) => Promise<void>;
  onCancel: () => void;
};
```

编辑器使用受控 `<input>`、`<textarea>`，保存前禁用空白字段；正文显示 `当前字符数 / 4000`。在 `SkillsPage`：

- 以 `skill.source === "user"` 分组；
- “我的 Skills”头部显示“新建 Skill”；
- 点击用户卡片的编辑时先加载正文再打开编辑器；
- 删除时复用 `ConfirmDialog`，确认后调用 `removeUserSkill`；
- 内置卡片不传编辑与删除回调。

在 `SkillCard` 增加可选 `onEdit`、`onDelete`，仅在这些回调存在时渲染对应按钮。

在 `App.css` 添加 `.skills-section`、`.user-skill-editor`、`.skill-card-manage` 样式：直角、1px 发丝边框、暖白底、深色保存按钮，复用既有 `--opencode-*` tokens；小屏幕下表单字段和操作按钮单列显示。

- [ ] **步骤 4：运行页面测试验证通过**

运行：`npm test -- src/components/skills/SkillsPage.test.tsx`

预期：PASS。

## 任务 5：端到端回归验证

**文件：**
- 修改：无

- [ ] **步骤 1：运行后端 Skill 相关测试**

运行：`$env:PYTHONPATH='D:\agent\Iris-agent'; pytest tests/skill_center/test_user_skills.py tests/api/test_skills.py -q --basetemp .tmp\pytest-custom-skills`

预期：PASS。

- [ ] **步骤 2：运行前端 Skills 相关测试**

运行：`npm test -- src/api/skills.user.test.ts src/components/skills/SkillsPage.test.tsx`

预期：PASS。

- [ ] **步骤 3：运行完整前端回归和生产构建**

运行：`npm test -- --run; npm run build`

预期：所有 Vitest 测试通过，Vite 生产构建成功。

## 自检

- 规格中的创建、编辑、启用/停用、删除、内置保护与安全约束均有对应任务。
- API 与前端统一使用 `source` 识别用户 Skill；正文仅通过用户专用端点读取。
- 所有生产变更之前均安排了对应的失败测试与验证命令。
- 未引入脚本执行、自定义入口或云同步等规格外能力。
