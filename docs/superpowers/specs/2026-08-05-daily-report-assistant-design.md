# Iris Agent 日报助手设计规格

**日期：** 2026-08-05

**状态：** 已完成交互设计，等待用户书面审查

**目标版本：** Iris Agent v0.2（个人提效路线）

## 1. 背景与目标

Iris Agent 的近期目标从“完整复刻 Hermes Agent 的高级执行能力”调整为“个人工作提效助手”。第一项可用能力是独立的日报助手：用户输入当天工作记录，可选择导入当前聊天内容，生成适合向领导或团队汇报的日报，并能继续用自然语言修改、手动编辑、保存历史和下载 Markdown。

已完成的工具审批分支继续保留，但不作为日报功能的前置依赖，也不继续扩展命令执行等高级能力。

## 2. 产品范围

### 2.1 第一版包含

- 独立“日报”页面，而不是聊天命令。
- 手动输入当天工作记录。
- 可选择导入当前会话的用户与助手文本消息快照。
- 默认生成“汇报版”日报。
- 固定章节：今日完成、进行中、遇到的问题、明日计划、需要协助。
- 支持直接编辑每个章节。
- 支持输入自然语言要求让 AI 修改当前日报。
- 自动保存本地草稿，并按日期查看历史。
- 同一天只有一份日报，但保留有限版本历史并支持恢复。
- 支持复制和下载 `.md`。
- 桌面端使用三栏工作台，窄屏使用标签切换。

### 2.2 第一版不包含

- Word、PDF 或富文本导出。
- 定时生成、系统通知或后台任务。
- 联网搜索和热点日报。
- UML 生成。
- 多账号、云同步或多人协作。
- 自定义模板和任意磁盘路径。
- 自动执行命令或修改日报目录以外的文件。

## 3. 用户体验与布局

### 3.1 导航

现有侧栏增加“聊天”和“日报”两个一级入口。第一版不引入路由依赖，由 `App` 保存当前视图；刷新后通过 `localStorage` 恢复最近视图，但服务端数据仍是唯一事实来源。

### 3.2 三栏工作台

1. **历史栏（20%）**：按更新时间倒序列出日期、摘要和修改时间；当天条目优先。
2. **来源栏（32%）**：日期、手动工作记录、导入当前对话开关和“生成汇报版日报”按钮。
3. **预览栏（48%）**：五个可编辑章节、保存状态、复制、下载和 AI 修改输入框。

当视口不足以容纳三栏时，页面改为“历史 / 记录 / 预览”三个标签，不进行横向挤压。

原型保存在忽略提交的 `.superpowers/brainstorm/daily-report-layout-20260805/` 中。

## 4. 核心流程

### 4.1 生成

1. 页面默认选择本地日期的当天日报。
2. 用户填写工作记录，并决定是否导入当前会话。
3. 前端提交日期、手动记录、当前 `session_id` 和导入开关。
4. 若导入会话，服务端通过 `SessionRepository` 读取该会话，仅截取 `user` 和 `assistant` 的文本消息；其他会话不可见。
5. `DailyReportService` 组合固定系统提示词、手动记录和会话快照，调用现有 `ModelProvider.complete(messages, tools=[])`，不向模型提供工具。
6. 模型必须返回结构化 JSON；服务端严格验证五个章节，拒绝缺字段、错误类型或额外不可识别结构。
7. 验证成功后保存新版本，前端展示结构化章节；Markdown 由服务端统一渲染。

### 4.2 手动编辑与自动保存

- 预览栏按章节编辑，而不是编辑整段原始 Markdown。
- 前端停止输入 600 ms 后自动保存，并携带不可回退的 `expected_revision` 做乐观并发控制；恢复或日期切换会取消尚未发出的自动保存。
- 同一批连续输入只产生一个手动编辑版本；服务端最多保留最近 20 个版本。
- 保存期间显示“正在保存”，成功后显示“已保存”；失败时保留本地内容并显示“保存失败，可重试”，不能显示虚假的成功状态。

### 4.3 AI 修改

1. 用户输入最多 2,000 字的修改要求，例如“更简短，突出成果”。
2. 服务端将当前五个章节和修改要求发送给模型，仍要求返回相同结构。
3. 验证成功后创建 `ai_revision` 版本；失败时原版本保持不变。

### 4.4 版本恢复

- 用户可查看当前日报的版本时间、类型和修改说明。
- 恢复旧版本不会删除后续历史，也不会复制或新建版本；被选中的历史版本直接成为当前版本。
- 恢复成功后，页面自动切到日报预览区域并滚动到顶部；同一天始终只有一个当前版本。
- 恢复会递增日报修订号，但不会改变历史版本列表；旧页面因此不能在恢复后覆盖当前内容。

### 4.5 复制和下载

- 复制使用前端从结构化章节生成的同一 Markdown 预览文本。
- 下载由服务端生成 UTF-8 Markdown，文件名固定为 `日报-YYYY-MM-DD.md`。
- 日期必须通过服务端 `YYYY-MM-DD` 校验，客户端不能提供文件路径或文件名。

## 5. 数据模型与存储

新增 `iris_agent/reports/` 包。

```python
@dataclass(frozen=True, slots=True)
class ReportSections:
    completed: tuple[str, ...]
    in_progress: tuple[str, ...]
    problems: tuple[str, ...]
    next_day: tuple[str, ...]
    assistance: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class ReportVersion:
    number: int
    sections: ReportSections
    kind: Literal["generated", "manual", "ai_revision", "restored"]
    instruction: str | None
    created_at: float

@dataclass(slots=True)
class DailyReport:
    date: str
    source_notes: str
    source_session_id: str | None
    source_chat_snapshot: tuple[ReportSourceMessage, ...]
    versions: list[ReportVersion]
    current_version: int
    revision: int  # 单调递增的写入令牌，不等同于历史版本号
    created_at: float
    updated_at: float
```

### 5.1 本地仓库

- 接口：`DailyReportRepository`。
- 实现：`JsonDailyReportRepository`。
- 目录：默认 `data/reports/`，可通过配置修改目录但不能由 API 请求修改。
- 每天一个 JSON 文件，文件名为已校验日期。
- 同一日期使用进程内锁保护读取—修改—保存。
- 保存使用同目录临时文件、`flush`、`fsync` 和 `os.replace`；失败时原文件保持可读。
- 损坏文件返回稳定的 `ReportStorageError`，不能默认为空并覆盖原数据。
- 版本超过 20 个时只删除最旧的非当前版本。

## 6. 后端模块

- `iris_agent/reports/models.py`：数据模型、验证和不可变章节。
- `iris_agent/reports/repository.py`：协议及 JSON 原子存储。
- `iris_agent/reports/prompts.py`：汇报版生成和修改提示词。
- `iris_agent/reports/service.py`：生成、修改、手动保存、恢复和 Markdown 渲染。
- `iris_agent/api/report_schemas.py`：请求与响应模型。
- `iris_agent/api/app.py`：注册日报接口。
- `iris_agent/bootstrap.py`：组装仓库和服务。
- `iris_agent/config/settings.py`、`agent.yaml`：日报目录、输入限制和版本上限。

日报服务直接依赖 `ModelProvider` 和 `SessionRepository`，不依赖 `AgentLoop`、工具注册表或审批系统。

## 7. API 设计

### 7.1 查询

- `GET /api/reports`：返回日报摘要列表。
- `GET /api/reports/{report_date}`：返回当前日报、来源信息和版本元数据。
- `GET /api/reports/{report_date}/versions/{version}`：返回指定版本内容。

### 7.2 修改

- `POST /api/reports/generate`：创建或重新生成当天日报。
- `POST /api/reports/{report_date}/revise`：AI 修改当前日报。
- `PUT /api/reports/{report_date}`：保存手动编辑的结构化章节。
- `POST /api/reports/{report_date}/versions/{version}/restore`：将指定历史版本设为当前版本，不创建复制版本。

所有修改请求携带 `expected_revision`；响应同时返回 `current_version`（当前历史内容）和 `revision`（单调递增写入令牌）。为短期兼容，`expected_version` 可作为同值别名；冲突返回 HTTP 409 和稳定错误码 `report_version_conflict`。

### 7.3 下载

- `GET /api/reports/{report_date}/download`：返回 `text/markdown; charset=utf-8` 和安全的 `Content-Disposition`。

### 7.4 稳定错误码

- `report_not_found`
- `report_invalid_date`
- `report_input_too_long`
- `report_session_required`
- `report_model_output_invalid`
- `report_generation_failed`
- `report_version_conflict`
- `report_storage_error`

错误响应沿用现有 `{ "detail": { "code", "message" } }` 结构，不返回模型原始异常、磁盘路径或密钥。

## 8. 前端模块

- `web-react/src/components/reports/DailyReportPage.tsx`
- `web-react/src/components/reports/ReportHistory.tsx`
- `web-react/src/components/reports/ReportSourceEditor.tsx`
- `web-react/src/components/reports/ReportPreview.tsx`
- `web-react/src/components/reports/ReportRevisionBox.tsx`
- `web-react/src/hooks/useDailyReports.ts`
- `web-react/src/api/reports.ts`
- `web-react/src/types.ts`：增加日报 API 类型。
- `web-react/src/App.tsx`、`Sidebar.tsx`、`App.css`：视图切换和三栏/窄屏布局。

前端状态按职责拆分：API 模块只处理 HTTP；Hook 处理加载、并发版本、自动保存和错误；组件只负责交互与展示。生成、AI 修改和恢复期间禁用相应重复操作。

## 9. 提示词与模型输出

生成提示词明确要求：

- 只根据输入事实整理，不虚构完成项、数据或进度。
- 使用简洁、正式、适合向领导或团队汇报的中文。
- 成果优先，问题描述客观，明日计划可执行。
- 未提供内容的章节返回空数组，不编造内容。
- 只返回约定 JSON 对象，不返回 Markdown 代码块或解释。

服务端从模型响应中提取单个 JSON 对象并严格校验。校验失败只返回 `report_model_output_invalid`，不保存部分结果。第一版不做自动二次调用修复格式，避免不可控成本和重复生成。

## 10. 限制与安全边界

- 手动工作记录最多 50,000 字；AI 修改要求最多 2,000 字。
- 会话导入必须提供存在的当前 `session_id`；服务端不接受会话 ID 列表。
- 导入内容只包括用户和助手文本，不包括工具参数、工具结果、系统提示词或密钥。
- 日报模型调用不暴露任何工具。
- 日报文件路径完全由仓库按日期决定。
- UI 对模型生成内容按纯文本展示，不能执行 HTML 或脚本。
- 本地数据可能包含工作信息；`data/` 继续保持在 `.gitignore` 中。

## 11. 测试与验收

### 11.1 后端

- 模型、JSON 编解码和日期验证。
- 原子保存、损坏文件、并发更新和版本上限。
- 仅导入指定当前会话的允许角色文本。
- 生成成功、模型无效 JSON、模型异常和输入超限。
- AI 修改失败不改变当前版本。
- 手动保存的版本冲突。
- 版本恢复不创建新版本、不删除历史，并跳转到恢复后的预览内容。
- Markdown 标题、章节、UTF-8 下载文件名和响应类型。
- API 成功路径及全部稳定错误码。

### 11.2 前端

- 历史加载和日期切换。
- 导入对话开关与缺少当前会话的提示。
- 生成、AI 修改、保存、恢复期间防止重复提交。
- 600 ms 自动保存及版本冲突提示。
- 保存失败保留页面内容。
- 复制和下载动作。
- 三栏桌面布局与窄屏标签布局。

### 11.3 完成标准

- Python 全量测试通过，无新增非预期警告。
- React ESLint、TypeScript 编译和 Vite 构建通过。
- `git diff --check` 通过。
- 使用真实本地服务手工验证：创建日报、导入当前会话、AI 修改、刷新恢复、查看历史、恢复版本、复制和下载。

## 12. 后续路线

日报助手完成后，再分别设计并实现：

1. UML 助手：生成 Mermaid/PlantUML 与页面预览。
2. 热点总结助手：联网检索、来源引用、去重和每日简报。

这两个功能不进入本规格，也不作为日报助手验收条件。
