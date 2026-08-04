# Iris Agent v0.2 工具审批与可视化实施计划

> **面向 AI 代理的工作者：** 使用 `subagent-driven-development`（推荐）或 `executing-plans` 逐任务实施，并按复选框跟踪进度。

**目标：** 为 Iris Agent 增加 Web/CLI 共用的工具审批层、受控文件写入与命令执行、持久化规则、审计日志和审批卡片。

**架构：** `ApprovalPolicy` 在工具执行前评估规则，`ApprovalBroker` 管理等待与决策，`ApprovalRuleStore` 持久化永久规则。Agent 循环通过审批事件与 Web/CLI 交互，受控工具仍由现有 `ToolRegistry` 执行。

**技术栈：** Python 3.11+、FastAPI、pytest、React 19、TypeScript、Vite。

---

## 文件结构

- 创建 `iris_agent/approvals/models.py`：审批请求、决策、规则与状态。
- 创建 `iris_agent/approvals/store.py`：永久规则原子 JSON 仓储。
- 创建 `iris_agent/approvals/policy.py`：路径范围与命令前缀评估。
- 创建 `iris_agent/approvals/broker.py`：并发安全的请求、等待、决策、超时和取消。
- 创建 `iris_agent/approvals/audit.py`：脱敏审计日志。
- 创建 `iris_agent/tools/builtin/write_file.py`：原子文件写入。
- 创建 `iris_agent/tools/builtin/patch_file.py`：受控文本补丁。
- 创建 `iris_agent/tools/builtin/command.py`：超时、取消和输出截断的命令执行。
- 修改 `iris_agent/tools/base.py`、`registry.py`：审批元数据和预执行校验。
- 修改 `iris_agent/core/agent.py`：审批事件和决策等待。
- 修改 `iris_agent/api/app.py`、`schemas.py`：审批决策 API 与取消。
- 修改 `iris_agent/cli.py`：交互式审批。
- 修改 `iris_agent/config/settings.py`、`agent.yaml`：审批、审计和工具配置。
- 修改 `web-react/src/types.ts`、`api/chat.ts`、`hooks/useChat.ts`：审批事件与决策。
- 创建 `web-react/src/components/ApprovalCard.tsx` 并修改聊天组件与 CSS。

### 任务 1：审批领域模型与规则仓储

**文件：**
- 创建：`iris_agent/approvals/__init__.py`
- 创建：`iris_agent/approvals/models.py`
- 创建：`iris_agent/approvals/store.py`
- 测试：`tests/approvals/test_models.py`
- 测试：`tests/approvals/test_store.py`

- [ ] 写失败测试：请求参数深拷贝后不可被调用方修改；决策状态只能转换一次。
- [ ] 写失败测试：永久规则原子保存、重启恢复；损坏 JSON 返回空规则且不自动放行。
- [ ] 运行 `python -m pytest tests/approvals/test_models.py tests/approvals/test_store.py -q`，确认因模块缺失失败。
- [ ] 最小实现 `ApprovalDecision`、`ApprovalStatus`、`ApprovalRequest`、`ApprovalRule` 与 `JsonApprovalRuleStore`。
- [ ] 重新运行测试并确认通过。

关键接口：

```python
@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    id: str
    session_id: str
    tool: str
    arguments: Mapping[str, Any]
    summary: str
    risk: str
    created_at: float
    expires_at: float

class ApprovalRuleStore(Protocol):
    def list(self) -> list[ApprovalRule]: ...
    def add(self, rule: ApprovalRule) -> None: ...
```

### 任务 2：审批策略与 Broker

**文件：**
- 创建：`iris_agent/approvals/policy.py`
- 创建：`iris_agent/approvals/broker.py`
- 测试：`tests/approvals/test_policy.py`
- 测试：`tests/approvals/test_broker.py`

- [ ] 写失败测试：只读工具免审、受控工具需审、保护路径禁止。
- [ ] 写失败测试：会话规则隔离、文件路径范围、命令数组前缀、复合 Shell 不继承前缀规则。
- [ ] 写失败测试：Broker 正常决策、120 秒逻辑超时、取消、重复决策、并发请求互不干扰。
- [ ] 运行上述测试并确认失败。
- [ ] 实现 `ApprovalPolicy.evaluate()` 与并发安全的 `ApprovalBroker`；等待使用 `threading.Condition`，测试注入时钟。
- [ ] 运行测试并确认通过。

### 任务 3：脱敏审计日志

**文件：**
- 创建：`iris_agent/approvals/audit.py`
- 测试：`tests/approvals/test_audit.py`

- [ ] 写失败测试：API Key、Token、password、authorization 和环境值均被替换为 `[REDACTED]`。
- [ ] 写失败测试：每行有效 JSON，包含会话、审批、决策、结果和耗时；写入失败抛出 `AuditError`。
- [ ] 运行测试并确认失败。
- [ ] 实现线程安全的 JSONL 审计器、递归脱敏和 flush/fsync。
- [ ] 运行测试并确认通过。

### 任务 4：受控文件工具

**文件：**
- 创建：`iris_agent/tools/builtin/write_file.py`
- 创建：`iris_agent/tools/builtin/patch_file.py`
- 修改：`iris_agent/tools/base.py`
- 修改：`iris_agent/tools/registry.py`
- 测试：`tests/tools/test_write_file.py`
- 测试：`tests/tools/test_patch_file.py`

- [ ] 写失败测试：写入新文件、原子覆盖、1 MB 限制、工作区逃逸、符号链接逃逸和保护路径。
- [ ] 写失败测试：补丁唯一匹配成功；零匹配或多匹配不修改文件。
- [ ] 运行测试并确认失败。
- [ ] 为 Tool 增加 `approval_kind`、摘要生成器和执行前复验钩子。
- [ ] 实现 `write_file(path, content)` 与 `apply_patch(path, old_text, new_text)`。
- [ ] 运行文件工具测试和现有 `tests/tools`，确认通过。

### 任务 5：受控命令工具

**文件：**
- 创建：`iris_agent/tools/builtin/command.py`
- 测试：`tests/tools/test_command.py`

- [ ] 写失败测试：`executable + args` 原样传递，不经 Shell 解释。
- [ ] 写失败测试：工作目录逃逸、环境密钥过滤、stdout/stderr 分别截断。
- [ ] 写失败测试：超时和取消在 Windows 上终止进程树，返回稳定错误码。
- [ ] 运行测试并确认失败。
- [ ] 使用 `subprocess.Popen(shell=False)` 实现命令工具；Windows 使用新进程组并通过 `taskkill /T` 清理，其他平台使用进程组。
- [ ] 限制默认超时 60 秒、最大 600 秒及输出上限。
- [ ] 运行命令工具测试并确认通过。

### 任务 6：Agent 审批循环与持久化审计

**文件：**
- 修改：`iris_agent/core/agent.py`
- 修改：`iris_agent/bootstrap.py`
- 修改：`iris_agent/config/settings.py`
- 修改：`agent.yaml`
- 测试：`tests/core/test_agent_approval.py`
- 测试：`tests/core/test_agent_service.py`

- [ ] 写失败测试：免审工具直接运行；受控工具先发 `approval_required`，决策后才发 `tool_started`。
- [ ] 写失败测试：拒绝、超时、取消均不调用处理函数并作为工具结果返回模型。
- [ ] 写失败测试：允许一次、本会话、永久规则和执行前复验。
- [ ] 写失败测试：审计失败时受控工具不执行。
- [ ] 运行测试并确认失败。
- [ ] 在 Agent 循环中接入 Policy、Broker 和 Audit；保持工具消息完整持久化。
- [ ] 更新依赖组装与配置，注册三个受控工具。
- [ ] 运行 `python -m pytest tests/core tests/approvals tests/tools -q` 并确认通过。

### 任务 7：FastAPI 与 CLI 审批通道

**文件：**
- 修改：`iris_agent/api/schemas.py`
- 修改：`iris_agent/api/app.py`
- 修改：`iris_agent/cli.py`
- 测试：`tests/api/test_approvals.py`
- 测试：`tests/test_cli_approvals.py`

- [ ] 写失败测试：提交四种决策、未知审批、重复决策、已超时审批和客户端取消。
- [ ] 写失败测试：CLI 四种输入映射；非 TTY 默认拒绝。
- [ ] 运行测试并确认失败。
- [ ] 实现 `POST /api/approvals/{id}/decision` 和取消接口；使用稳定错误码。
- [ ] CLI 在审批事件时打印摘要与风险，并调用同一 Broker。
- [ ] 运行 API、CLI 与既有测试并确认通过。

### 任务 8：React 审批卡片

**文件：**
- 修改：`web-react/src/types.ts`
- 修改：`web-react/src/api/chat.ts`
- 修改：`web-react/src/hooks/useChat.ts`
- 创建：`web-react/src/components/ApprovalCard.tsx`
- 修改：`web-react/src/components/ChatContainer.tsx`
- 修改：`web-react/src/App.css`

- [ ] 定义 `ApprovalRequestView`、审批状态和 `approval_required` 事件类型。
- [ ] 实现决策 API，检查 HTTP 状态并防止重复提交。
- [ ] `useChat` 按审批 ID 保存不可变请求与状态；停止生成时提交取消。
- [ ] 创建审批卡片：摘要、风险、参数展开、倒计时、四个按钮和终态。
- [ ] 将卡片渲染在对应助手输出下，不改变现有消息轨道。
- [ ] 运行 `npm run lint`、`tsc -b` 和 `vite build`，预期退出码均为 0。

### 任务 9：文档、回归与安全验收

**文件：**
- 修改：`README.md`
- 修改：`.env.example`
- 修改：`.gitignore`
- 测试：`tests/integration/test_approval_flow.py`

- [ ] 编写完整集成测试：模型请求写文件、Web 决策允许、文件落盘、审计记录生成、模型收到结果。
- [ ] 编写拒绝、超时、断线取消及永久规则重启恢复测试。
- [ ] README 增加审批级别、受控工具、安全限制、规则文件和审计位置。
- [ ] 忽略运行期审批规则和审计日志；示例配置不得包含真实密钥。
- [ ] 运行 `python -m pytest -q`，预期全部通过且无非预期警告。
- [ ] 运行 `python -m compileall -q iris_agent iris_agent.py server.py`。
- [ ] 运行 React lint、TypeScript 编译与 Vite 构建。
- [ ] 运行 `git diff --check` 和敏感信息扫描。

## 实施约束

- 每项生产行为必须先看到对应测试因功能缺失而失败。
- 受控工具默认关闭；只有配置启用后才注册。
- 审批基础设施或审计不可用时必须失败关闭。
- 不扩大到 MCP、Skills、记忆、子 Agent 或删除工具。
- 完成前进行独立代码审查，并修复全部 Critical/Important 问题。
