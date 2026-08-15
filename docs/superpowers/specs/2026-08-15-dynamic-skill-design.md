# 动态 Skill 一期设计（P3）

日期：2026-08-15  
状态：方案待确认

## 目标与范围

让 Iris 的 Skill 从「只读的前端入口目录」升级为「可执行、可沉淀、可改进」的能力：Agent 完成一次复杂任务后，能把可复用的流程沉淀成一条 Skill；下次遇到同类任务时，加载该 Skill 的内容照着做。

一期做「Skill 正文加载 + 用户 Skill 创建/更新」，即两个内置工具：

- `use_skill(skill_id)`：加载某条 Skill 的正文指令（供 Agent 参考执行）。
- `save_skill(name, description, content)`：把经验沉淀为一条用户 Skill（创建或更新）。

一期不做 hermes 的 curator（后台定期审查）、自动触发创建、Skill 生命周期（pin/archive）或版本管理——这些留到后续。

## 关键差异：从「入口目录」到「执行指令」

iris 当前 `SkillCatalog` 只解析 SKILL.md 的 front matter（元数据），**从不读取正文**；前端把它当「功能入口」展示。hermes 的 SKILL.md 正文是给 Agent 的 how-to 指令。本期把正文纳入模型，并让 Agent 能按需加载。

## 数据模型

`SkillDefinition`（`skill_center/models.py`）扩展两个字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `body` | `str` | SKILL.md 正文（执行指令），加载时返回、写入时保存 |
| `source` | `str` | `bundled`（随包内置）或 `user`（Agent/用户创建） |

现有白名单字段（`id/name/description/icon/category/entry_view/version`）不变。

## 存储

- **内置 Skill**：`iris_agent/skill_center/bundled/`（只读，随包分发）。
- **用户 Skill**：`data/skills/<skill_id>/SKILL.md`（可写，`save_skill` 写入）。

用户 Skill 的 front matter 自动补全默认值：`icon="sparkles"`、`category="custom"`、`entry_view="chat"`、`version=1`（更新时版本 +1）。`id` 由名称生成安全 slug（小写连字符），冲突时追加短哈希。

## 工具

### use_skill

```python
def build_use_skill_tool(skills) -> Tool:
    def use_skill(skill_id: str):
        skill = skills.load_skill(skill_id)  # 含 body
        return {"id": skill.id, "name": skill.name, "content": skill.body}
```

`requires_approval=False`（只读）。正文过长时截断到 `max_body_chars`（默认 4000）。

### save_skill

```python
def build_save_skill_tool(skills) -> Tool:
    def save_skill(name: str, description: str, content: str):
        skill = skills.save_user_skill(name, description, content)
        return {"id": skill.id, "name": skill.name, "version": skill.version}
```

`requires_approval=False`（写入的是 Agent 自己的知识库，类似 `remember`）。参数 `name`/`description`/`content` 均非空，`content` 上限 `max_body_chars`。

## 服务扩展

`SkillCenterService` 增加：

- `load_skill(skill_id) -> SkillDefinition`：合并 bundled + user 目录查找，返回含 `body` 的定义。
- `save_user_skill(name, description, content) -> SkillDefinition`：写入 `data/skills/`，原子写 SKILL.md；同名更新则版本 +1。
- `list_skills()`：合并返回 bundled + user。

## 配置

`SkillSettings` 增加：`user_directory=Path("data/skills")`、`max_body_chars=4000`。`bootstrap.py` 注册 `build_use_skill_tool`、`build_save_skill_tool`。

## 隐私与安全

- `save_skill` 写入的内容是 Agent 主动沉淀的指令，不自动扫描会话、不写入工具参数/结果/环境变量/密钥。
- `use_skill` 只读；`save_skill` 只写 `data/skills/`，不触碰 bundled 只读目录。
- Skill `id` 严格校验（安全字符），拒绝路径穿越。

## 测试与验收

后端覆盖：

- `save_skill` 创建/更新用户 Skill，版本递增，非法参数报错；
- `use_skill` 返回正文、内置与用户 Skill 均可加载、不存在返回错误码；
- 目录合并（bundled + user），`id` 冲突处理；
- 正文截断、front matter 默认值补全、路径穿越拒绝；
- 装配与工具注册。

验收标准：Agent 完成一个复杂任务后能通过 `save_skill` 沉淀流程，下次调用 `use_skill` 加载该流程照着执行；写入内容只含 Agent 主动提交的指令，不含敏感数据。
