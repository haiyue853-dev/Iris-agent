# 动态 Skill 一期实现计划（P3）

> **面向 AI 代理的工作者：** 必需子技能：使用 `superpowers:executing-plans`（或 `subagent-driven-development`）逐任务实现。步骤使用复选框（`- [ ]`）跟踪进度。

**目标：** 让 Iris 的 Skill 可执行、可沉淀——`use_skill` 加载正文，`save_skill` 沉淀经验。

**架构：** 扩展 `SkillDefinition`（加 `body`/`source`）；`SkillCatalog` 解析正文；`SkillCenterService` 支持 user 目录读写与合并；新增 `use_skill`/`save_skill` 工具。

**技术栈：** Python 3、FastAPI、原子文件写、Pytest。

**工作目录：** `D:\agent\iris-agent`（后端测试用 `.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp=<全新目录>`）。

---

### 任务 1：扩展 Skill 模型与正文解析

**文件：** 修改 `iris_agent/skill_center/models.py`、`catalog.py`；测试 `tests/skill_center/test_catalog.py`。

- [ ] **步骤 1：编写失败测试**

```python
def test_catalog_parses_body_and_source(tmp_path):
    (tmp_path / "demo" / "SKILL.md").write_text(
        "---\nid: demo\nname: Demo\ndescription: d\nicon: sparkles\ncategory: custom\nentry_view: chat\nversion: 1\n---\n# Demo\n这是正文指令", encoding="utf-8")
    skill = SkillCatalog(tmp_path).get("demo")
    assert skill.body == "# Demo\n这是正文指令"
    assert skill.source == "bundled"
```

- [ ] **步骤 2：验证为红色** → FAIL（`body` 缺失）。

- [ ] **步骤 3：实现**

`models.py`：`SkillDefinition` 加 `body: str = ""`、`source: str = "bundled"`。`catalog.py`：解析 front matter 之后的正文为 `body`。

- [ ] **步骤 4：验证并提交**

```bash
git add iris_agent/skill_center/models.py iris_agent/skill_center/catalog.py tests/skill_center/test_catalog.py && git commit -m "feat(技能): 扩展技能模型与正文解析"
```

---

### 任务 2：用户 Skill 存储与目录合并

**文件：** 修改 `iris_agent/skill_center/service.py`；测试 `tests/skill_center/test_user_skills.py`。

- [ ] **步骤 1：编写失败测试**

```python
def test_save_and_load_user_skill(service):
    skill = service.save_user_skill("我的技能", "描述", "正文内容")
    assert skill.source == "user"
    assert service.load_skill(skill.id).body == "正文内容"

def test_list_merges_bundled_and_user(service):
    service.save_user_skill("自定义", "d", "c")
    ids = [s.id for s in service.list_skills()]
    assert "自定义" not in ids  # id 是 slug
    assert len(ids) >= 2
```

- [ ] **步骤 2：验证为红色** → FAIL。

- [ ] **步骤 3：实现**

`service.py`：加 `user_directory`、`max_body_chars`；`save_user_skill(name, description, content)` 生成安全 id（slug + 冲突短哈希）、原子写 `data/skills/<id>/SKILL.md`、同名更新版本 +1；`load_skill(skill_id)` 合并 bundled + user 查找返回含 body；`list_skills()` 合并两目录。

- [ ] **步骤 4：验证并提交**

```bash
git add iris_agent/skill_center/service.py tests/skill_center/test_user_skills.py && git commit -m "feat(技能): 支持用户技能存储与目录合并"
```

---

### 任务 3：use_skill 与 save_skill 工具

**文件：** 创建 `iris_agent/tools/builtin/skill_tools.py`；修改 `tools/builtin/__init__.py`；测试 `tests/tools/test_skill_tools.py`。

- [ ] **步骤 1：编写失败测试**

```python
def test_save_and_use_skill_tools(service):
    save = build_save_skill_tool(service)
    result = save.invoke({"name": "流程", "description": "d", "content": "步骤一"})
    assert result.ok
    use = build_use_skill_tool(service)
    loaded = use.invoke({"skill_id": result.value["id"]})
    assert "步骤一" in loaded.value["content"]
```

- [ ] **步骤 2：验证为红色** → FAIL。

- [ ] **步骤 3：实现工具**

`skill_tools.py`：`build_use_skill_tool(service)`（只读，返回 id/name/content）、`build_save_skill_tool(service)`（写用户技能，参数 name/description/content）。`__init__.py` 导出两个工厂。

- [ ] **步骤 4：验证并提交**

```bash
git add iris_agent/tools/builtin/skill_tools.py iris_agent/tools/builtin/__init__.py tests/tools/test_skill_tools.py && git commit -m "feat(技能): 提供 use_skill 与 save_skill 工具"
```

---

### 任务 4：配置与装配

**文件：** 修改 `iris_agent/config/settings.py`、`agent.yaml`、`iris_agent/bootstrap.py`；测试 `tests/test_bootstrap_services.py`。

- [ ] **步骤 1：编写失败测试**

```python
def test_build_application_registers_skill_tools(tmp_path, monkeypatch):
    ...
    tool_names = [schema["function"]["name"] for schema in application.agent.loop.tools.schemas()]
    assert "use_skill" in tool_names and "save_skill" in tool_names
```

- [ ] **步骤 2：验证为红色** → FAIL。

- [ ] **步骤 3：实现配置与装配**

`settings.py` 的 `SkillSettings` 加 `user_directory`、`max_body_chars`；`bootstrap.py` 构造 `SkillCenterService` 时传入 user 目录、注册两个工具。

- [ ] **步骤 4：验证并提交**

```bash
git add iris_agent/config/settings.py agent.yaml iris_agent/bootstrap.py tests/test_bootstrap_services.py && git commit -m "feat(技能): 接入配置与装配"
```

---

### 任务 5：全量验证

- [ ] **步骤 1：后端全量** `pytest -q -p no:cacheprovider --basetemp=<全新目录>` → 通过。
- [ ] **步骤 2：隐私核对** `save_skill` 只写主动提交的指令；不自动扫描会话；不触碰 bundled 只读目录；id 防路径穿越。

---

## 计划自检

- 规格覆盖：任务 1 覆盖正文解析；任务 2 覆盖用户技能存储与合并；任务 3 覆盖两个工具；任务 4 覆盖配置装配；任务 5 覆盖全量验证。
- 类型一致性：后端统一 `SkillDefinition`（含 body/source）、`save_user_skill`、`load_skill`；工具复用服务方法。
- 安全边界：`save_skill` 只写 `data/skills/`；`use_skill` 只读；id 严格校验防路径穿越；正文截断。

---

## 执行记录（2026-08-15）

五个任务全部完成并提交，分支 `feature/dynamic-skill`：

1. `feat(技能): 扩展技能模型与正文解析` —— `SkillDefinition` 加 `body`/`source`，`SkillCatalog` 解析正文，8 条测试。
2. `feat(技能): 支持用户技能存储与目录合并` —— `SkillCenterService` 加 `user_directory`/`save_user_skill`/`load_skill`，目录合并，5 条测试。
3. `feat(技能): 提供 use_skill 与 save_skill 工具` —— `skill_tools.py`（两个工具，requires_approval=False），3 条测试。
4. `feat(技能): 接入配置与装配` —— `SkillSettings` 加 `user_directory`/`max_body_chars`，`bootstrap.py` 注册工具，1 条测试。
5. 全量验证：后端 `370 passed, 3 skipped, 0 failed`（Python 3.13 下全绿）；隐私核对通过（save_skill 只写主动提交指令、use_skill 只读、不碰 bundled、id 防路径穿越）。

