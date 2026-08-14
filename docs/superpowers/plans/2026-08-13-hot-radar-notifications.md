# 热点雷达站内通知实现计划

> **面向 AI 代理的工作者：** 必须使用 `executing-plans` 逐任务实现此计划。

**目标：** 热点扫描发现新增条目时生成可管理的站内通知，并在任务中心展示执行详情。

**架构：** 通知服务独立持久化 JSON；自动化服务把扫描结果写入执行账本并按新增数量创建通知；前端复用任务中心加载通知和执行记录。

**技术栈：** FastAPI、dataclass、JSON 原子写入、React、Vitest、pytest。

---

### 任务 1：扫描结果与通知服务

**文件：**
- 创建：`iris_agent/notifications/service.py`
- 创建：`iris_agent/notifications/__init__.py`
- 修改：`iris_agent/hot_radar/service.py`
- 测试：`tests/notifications/test_service.py`、`tests/hot_radar/test_service.py`

- [ ] 写出失败测试：扫描返回新增条目 ID；通知可创建、读取、标已读和删除。
- [ ] 运行对应 pytest，确认因缺少服务/字段失败。
- [ ] 实现 `ScanResult.item_ids` 和 `NotificationService` 的 JSON 原子读写。
- [ ] 重跑测试并提交。

### 任务 2：自动化账本与通知 API

**文件：**
- 修改：`iris_agent/automation/service.py`、`iris_agent/bootstrap.py`、`server.py`
- 创建：`iris_agent/api/notifications_api.py`
- 修改：`iris_agent/api/app.py`、`iris_agent/api/automation_api.py`
- 测试：`tests/automation/test_service.py`、`tests/api/test_notifications.py`、`tests/api/test_automation.py`

- [ ] 写出失败测试：新增热点生成未读通知、零命中不生成通知、执行响应包含详情。
- [ ] 运行 pytest，确认 API 或字段缺失。
- [ ] 注入通知服务；扩展执行账本；注册通知路由。
- [ ] 重跑测试并提交。

### 任务 3：任务中心通知与执行详情

**文件：**
- 修改：`web-react/src/api/automation.ts`
- 修改：`web-react/src/components/automation/AutomationPage.tsx`
- 修改：`web-react/src/App.css`
- 测试：`web-react/src/components/automation/AutomationPage.test.tsx`

- [ ] 写出失败测试：展示未读通知、标已读、展开执行详情和热点链接。
- [ ] 运行目标 Vitest，确认界面功能缺失。
- [ ] 实现 API 调用与主题一致的通知/详情卡片。
- [ ] 运行 Vitest 和生产构建并提交。

### 任务 4：回归验证

**文件：** 无生产代码变更。

- [ ] 运行 `python -m pytest -q`。
- [ ] 运行自动化页面 Vitest 与 `npm run build`。
- [ ] 检查 `git diff --check` 与工作区，确认未误纳入原有未跟踪文件。
