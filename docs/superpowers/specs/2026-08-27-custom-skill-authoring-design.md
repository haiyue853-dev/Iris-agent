# 自定义 Skill 编写设计

日期：2026-08-27

## 目标

让用户在 Skills 中心直接创建、编辑、启用、停用和删除自己的 Skill。第一版聚焦提示词型 Skill，不提供脚本执行、文件上传或自定义入口页配置。

## 范围

- Skills 中心增加“我的 Skills”分区和“新建 Skill”入口。
- 提供内嵌编辑器，字段为名称、用途说明和 Markdown 正文。
- 自定义 Skill 卡片支持编辑、启用/停用和删除。
- 后端新增用户 Skill 的读取、保存和删除 API。
- 保存后 Skill 可在聊天中通过既有 Skill 工具被加载；仅已启用的 Skill 会参与 Agent 可用能力。

## 不在范围内

- 不执行 Skill 正文中的命令、脚本或外部链接。
- 不支持用户配置图标、入口页、命令、环境变量或文件附件。
- 不改变内置 Skill 的编辑权限；内置 Skill 只能启用或停用。
- 不增加云同步或多用户协作。

## 用户界面

Skills 页面保持现有 OpenCode 风格，按来源分为“内置 Skills”和“我的 Skills”。

“新建 Skill”展开内嵌编辑器，包含：

1. 名称：显示名称，同名保存视为更新。
2. 用途说明：用于卡片摘要和模型识别。
3. Skill 正文：Markdown 提示词正文，编辑器显示字符计数和格式提示。

编辑器提供“保存”“取消”。已有用户 Skill 卡片增加“编辑”“删除”操作；删除前使用现有确认弹窗。所有用户 Skill 固定显示默认图标，打开入口固定为聊天页。

## 数据与 API

沿用 `SkillCenterService.save_user_skill` 的本地持久化逻辑。每个 Skill 保存为用户目录下独立的 `SKILL.md`，其 front matter 使用安全固定值：

- `icon: sparkles`
- `category: custom`
- `entry_view: chat`

新增 API：

- `GET /api/skills/{skill_id}/content`：读取自定义 Skill 的可编辑字段和正文；内置 Skill 不返回正文。
- `POST /api/skills/user`：创建或按同名更新用户 Skill。
- `DELETE /api/skills/user/{skill_id}`：删除用户 Skill；内置 Skill 返回受控错误。

输入长度限制沿用服务端 `max_body_chars`；名称、说明和正文均需非空。API 仅返回经过验证的定义或公开元数据，绝不返回服务器路径。

## 安全与错误处理

- Skill ID 继续由服务端生成并校验，禁止路径穿越。
- 只允许用户目录下且 `source == user` 的定义被编辑、读取正文或删除。
- 失败响应转换为稳定、中文可读的 API 错误消息。
- 删除操作需确认；保存过程中禁用重复提交。
- Skill 正文只作为模型上下文，不被后端解析或执行。

## 测试

后端测试覆盖：创建、同名更新版本、读取正文、拒绝读取内置正文、拒绝删除内置 Skill、字段校验。

前端测试覆盖：创建表单显示、保存请求、用户 Skill 的编辑与删除入口、内置 Skill 不出现编辑/删除入口。

回归验证：运行相关 Python pytest、前端 Vitest 和 `npm run build`。

## 自检

- 范围仅覆盖提示词型自定义 Skill，未包含脚本执行或无关配置。
- UI、API、持久化和聊天调用路径使用已有 Skill 中心边界，无新增重复存储。
- 内置与用户 Skill 的权限边界明确，所有编辑性操作只作用于用户 Skill。
