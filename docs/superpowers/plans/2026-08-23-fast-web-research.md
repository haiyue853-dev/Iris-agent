# 快速联网与可见研究进度实现计划

> **面向 AI 代理的工作者：** 使用 executing-plans 逐任务执行；步骤使用复选框跟踪。

**目标：** 减少普通联网问答的重复搜索与串行等待，并把当前搜索和网页读取进度展示给用户。

**架构：** 研究 Skill 控制调用预算，AgentLoop 仅并行同批次的 `fetch_page`，前端从已有工具事件推导进度文案。配置层降低失败等待时间，不新增接口协议。

**技术栈：** Python 3.11+、concurrent.futures、React、TypeScript、Vitest、pytest

---

### 任务 1：快速搜索默认值与研究预算

**文件：**
- 修改：`agent.yaml`
- 修改：`iris_agent/config/settings.py`
- 修改：`iris_agent/skill_center/bundled/web-research/SKILL.md`
- 测试：`tests/config/test_settings.py`
- 测试：`tests/skill_center/test_catalog.py`

- [ ] 先写测试，断言默认 `timeout_seconds == 6`、`max_retries == 1`，并通过实际 Catalog 读取研究 Skill。
- [ ] 运行：`.\.venv\Scripts\python.exe -m pytest tests/config/test_settings.py tests/skill_center/test_catalog.py -q`，确认旧默认值导致失败。
- [ ] 修改默认配置和 Skill：普通模式一次搜索、最多两页；明确深度模式才允许 2–4 查询、最多三页。
- [ ] 重跑同一命令，预期全部通过。

### 任务 2：并行执行只读网页抓取

**文件：**
- 修改：`iris_agent/core/agent.py`
- 测试：`tests/core/test_agent_loop.py`

- [ ] 编写失败测试：三个带屏障的 `fetch_page` 调用必须同时开始，完成事件和模型工具消息仍按原调用顺序排列。
- [ ] 编写失败测试：普通工具和需要审批的工具保持串行；取消后不产生迟到的完成事件。
- [ ] 运行：`.\.venv\Scripts\python.exe -m pytest tests/core/test_agent_loop.py -q`，确认并行测试失败。
- [ ] 用最多三个 worker 执行连续 `fetch_page` 批次；其他调用沿用原逻辑。
- [ ] 重跑核心测试及后端全量测试。

### 任务 3：显示搜索与读取进度

**文件：**
- 修改：`web-react/src/components/assistant-ui/tool-group.tsx`
- 测试：`web-react/src/components/assistant-ui/tool-group.test.tsx`

- [ ] 编写失败测试：搜索运行显示查询词，完成显示结果数，多页面抓取显示完成数/总数。
- [ ] 运行：`npm test -- --run src/components/assistant-ui/tool-group.test.tsx`（目录 `web-react`），确认失败。
- [ ] 实现纯函数生成阶段文案，并保留失败、取消和普通工具文案。
- [ ] 运行前端测试、构建与 lint。

### 任务 4：最终验证

- [ ] 后端：`.\.venv\Scripts\python.exe -m pytest -q`。
- [ ] 前端：`npm test`、`npm run build`、`npm run lint`（目录 `web-react`）。
- [ ] 更新本计划执行结果，记录精确测试数量和既有警告。

## 计划自检

- 性能策略、并行边界、取消语义与进度文案均有对应任务。
- 不并行有副作用或审批工具，不修改聊天流协议。
- 当前目录不是 Git 仓库，因此没有 commit 或 worktree 步骤。

## 执行结果（2026-08-23）

- 快速搜索默认值：`timeout_seconds=6`、`max_retries=1`；研究 Skill 区分快速模式与明确触发的深度模式。
- `AgentLoop` 对同批次连续 `fetch_page` 使用最多 3 个 worker 并行执行；其他工具保持串行，取消后不发送迟到结果。
- 工具卡显示搜索词、搜索结果数量和网页读取进度。
- 后端全量：`941 passed, 4 skipped`，0 失败；23 条既有弃用警告。
- 前端全量：43 个测试文件、`188 passed`，0 失败。
- 前端构建：退出码 0；存在既有的 bundle 大小提示。
- 前端 lint：退出码 0；存在 16 条既有 Fast Refresh / unused import 警告。
