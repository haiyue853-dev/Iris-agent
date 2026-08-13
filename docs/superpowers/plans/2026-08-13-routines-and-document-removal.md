# 自动化任务中心与文档工作台移除实施计划

> **面向 AI 代理的工作者：** 使用 `executing-plans` 逐项执行，并在每项提交前运行列出的验证命令。

**目标：** 彻底移除文档工作台及其数据，新增可持久化、可审计的自动化任务中心 MVP。

**架构：** 新的 `iris_agent.automation` 独立保存任务、运行记录与调度状态；API 仅暴露已允许的自动化目标。React 任务中心通过专用 API 客户端加载并管理任务；文档模块从应用组合、配置、Skill 目录和前端路由全部摘除。

**技术栈：** Python 3.14、FastAPI、Pydantic、JSON 原子持久化、React、TypeScript、Vitest。

---

## 文件结构

- 删除 `iris_agent/documents/`、`iris_agent/api/documents_api.py`、`iris_agent/api/documents_schemas.py`：移除资料、草稿和导出能力。
- 修改 `iris_agent/bootstrap.py`、`iris_agent/api/app.py`、`iris_agent/config/settings.py`、`agent.yaml`：移除 documents 服务、路由和配置。
- 删除 `iris_agent/skill_center/bundled/document-workbench/`，修改 `iris_agent/skill_center/catalog.py`：移除内置 Skill 与入口视图。
- 创建 `iris_agent/automation/models.py`、`storage.py`、`service.py`、`scheduler.py`：定义例程的模型、追加式执行账本、目标执行和调度。
- 创建 `iris_agent/api/automation_schemas.py`、`automation_api.py`：定义并注册任务 API。
- 删除 `web-react/src/components/documents/`、`hooks/useDocumentWorkbench*`、`api/documents*`；修改 `App.tsx`、`Sidebar.tsx`、`App.css`、Skills 类型和测试：移除 documents 入口并添加 automation 入口。
- 创建 `web-react/src/components/automation/AutomationPage.tsx`、`web-react/src/api/automation.ts` 与对应测试：实现任务中心。
- 删除 `tests/documents/`、`tests/api/test_documents.py` 与文档相关断言；创建 `tests/automation/`、`tests/api/test_automation.py`。

### 任务 1：先移除文档工作台的可见入口与应用依赖

**文件：**

- 修改 `web-react/src/App.tsx`、`web-react/src/components/Sidebar.tsx`、`web-react/src/components/skills/SkillsPage.tsx`
- 修改 `iris_agent/bootstrap.py`、`iris_agent/api/app.py`、`iris_agent/config/settings.py`、`iris_agent/skill_center/catalog.py`、`agent.yaml`
- 测试 `tests/test_bootstrap_services.py`、`tests/config/test_settings.py`、`tests/skill_center/test_catalog.py`、`web-react/src/components/Sidebar.test.tsx`

- [ ] 1. 写出失败测试，断言应用服务没有 `documents` 属性、Skill 目录不含 `document-workbench`、前端 `AppView` 不含 `documents`。
- [ ] 2. 运行对应 pytest/Vitest 测试，确认失败原因是旧 documents 能力仍存在。
- [ ] 3. 移除服务注入、配置段、API 注册、Skill 目录与前端导航/路由；新增 `automation` 视图占位入口。
- [ ] 4. 再运行步骤 2 的测试，确认通过；提交 `refactor: 移除文档工作台入口与服务依赖`。

### 任务 2：安全删除文档实现、测试与数据

**文件：**

- 删除 `iris_agent/documents/`、`iris_agent/api/documents_api.py`、`iris_agent/api/documents_schemas.py`
- 删除 `tests/documents/`、`tests/api/test_documents.py`
- 删除 `web-react/src/components/documents/`、`web-react/src/hooks/useDocumentWorkbench.ts`、`web-react/src/hooks/useDocumentWorkbench.test.tsx`、`web-react/src/api/documents.ts`、`web-react/src/api/documents.test.ts`
- 删除 `data/documents/`，修改 `docs/superpowers` 中已废弃的文档工作台计划和规格

- [ ] 1. 读取并解析 `data/documents` 的绝对路径，确认它精确等于项目 `data/documents`，并确认 `data/reports` 存在且不是删除目标。
- [ ] 2. 删除列出的文档工作台文件与精确确认后的 `data/documents`；不处理 `.pytest_tmp`、`.basetmp_*`、`PROJECT_STATUS.md` 或 `tmp_c.py`。
- [ ] 3. 使用 `rg "documents|DocumentWorkbench|document-workbench"` 检查生产代码；只允许非功能性历史说明中保留的文字。
- [ ] 4. 运行后端测试收集和前端类型检查，修复所有悬挂 imports；提交 `refactor: 彻底移除文档工作台`。

### 任务 3：以 TDD 实现任务与执行账本

**文件：**

- 创建 `iris_agent/automation/models.py`、`storage.py`、`service.py`、`__init__.py`
- 创建 `tests/automation/test_storage.py`、`tests/automation/test_service.py`

- [ ] 1. 编写失败测试：创建日报任务后重新加载仍存在；声明执行会产生 `pending` 后变为 `succeeded`；重复计划窗口会被拒绝；重启恢复把 `running` 变为 `unknown`。
- [ ] 2. 运行 `pytest tests/automation -v`，确认缺少 `iris_agent.automation`。
- [ ] 3. 实现不可变 ID 模型、严格目标和状态枚举、原子 JSON 存储、声明/终结执行接口；终态不允许覆盖。
- [ ] 4. 运行 `pytest tests/automation -v`，确认通过；提交 `feat: 添加自动化任务执行账本`。

### 任务 4：实现安全目标、调度器与 API

**文件：**

- 创建 `iris_agent/automation/scheduler.py`、`iris_agent/api/automation_schemas.py`、`iris_agent/api/automation_api.py`
- 修改 `iris_agent/bootstrap.py`、`iris_agent/api/app.py`
- 创建 `tests/automation/test_scheduler.py`、`tests/api/test_automation.py`

- [ ] 1. 编写失败 API 测试：仅接受 `daily_report_draft` 与 `hot_radar_scan`；可创建、启停、手动运行并读取执行记录；未知目标和无效计划返回 422；API 输出不包含秘密。
- [ ] 2. 编写失败调度测试：同一到期窗口只声明一次；手动运行标为 `manual`；不可用热点雷达目标记录为 `failed`。
- [ ] 3. 实现 API 路由、计划验证、调度声明和安全摘要；日报仅生成草稿，热点雷达仅走只读扫描，绝不调用 MCP。
- [ ] 4. 运行 `pytest tests/automation tests/api/test_automation.py -v`，确认通过；提交 `feat: 提供自动化任务 API 与调度`。

### 任务 5：以 TDD 构建自动化任务中心

**文件：**

- 创建 `web-react/src/api/automation.ts`、`web-react/src/api/automation.test.ts`
- 创建 `web-react/src/components/automation/AutomationPage.tsx`、`AutomationPage.test.tsx`
- 修改 `web-react/src/App.tsx`、`web-react/src/components/Sidebar.tsx`、`web-react/src/App.css`、前端 Skills 测试夹具

- [ ] 1. 编写失败测试：侧栏显示“自动化任务”且不显示“文档工作台”；页面显示概览、任务状态、启停与立即执行；请求失败显示可读错误。
- [ ] 2. 使用 `C:\Program Files\nodejs\npm.cmd test -- --run ...` 运行针对测试，确认因模块不存在而失败。
- [ ] 3. 实现 API 客户端与任务页面，复用 MCP 的卡片、指标和按钮视觉语言；创建/编辑表单只暴露两个白名单目标，运行记录显示状态和摘要。
- [ ] 4. 重新运行前端测试和 `C:\Program Files\nodejs\npm.cmd run build`，确认通过；提交 `feat: 添加自动化任务中心`。

### 任务 6：完整验证与交付

**文件：**

- 修改 `PROJECT_STATUS.md`：只在用户允许后更新当前能力与验证记录。

- [ ] 1. 运行 `pytest -q`、前端全量 `npm test -- --run` 与 `npm run build`。
- [ ] 2. 通过本地浏览器验证移除后的侧栏、任务创建、暂停、立即执行和运行记录。
- [ ] 3. 检查 `git diff --check` 与 `git status --short`，确认只有本任务文件被提交，用户已有未跟踪文件仍未改动。
- [ ] 4. 提交 `test: 覆盖自动化任务中心回归场景`（若验证产生代码/测试调整），再汇报验证证据。
