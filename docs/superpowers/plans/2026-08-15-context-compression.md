# 实现计划：上下文压缩（一期）

日期：2026-08-15
分支：feature/context-compression

## 任务清单

| # | 任务 | 交付 |
|---|------|------|
| 1 | 上下文压缩器 | `context_compression/compressor.py` |
| 2 | Agent 接入压缩 | `core/agent.py` |
| 3 | 配置 + 装配 + 全量验证 | `settings.py` + `bootstrap.py` + `agent.yaml` |

（一期纯后端，无前端）

## 任务细节

### 任务 1：上下文压缩器
- `ContextCompressor(provider, trigger_chars, keep_recent, max_summary_chars, enabled)`。
- `needs_compression(messages) -> bool`；`compress(messages) -> list[Message]`（保留最近 N 条 + 早期消息 LLM 摘要，幂等合并旧摘要）。
- 测试：`tests/context_compression/test_compressor.py`（fake provider，验证阈值/保留/幂等/隐私/失败跳过）。

### 任务 2：Agent 接入
- `AgentService` 加可选 `compressor`；`_build_messages` 里超阈值则压缩并 `save`。
- 测试：`tests/core/test_agent_compression.py`。

### 任务 3：配置 + 装配 + 全量验证
- `ContextSettings`；`bootstrap.py` 构造压缩器注入 AgentService；`agent.yaml` 加 `context:` 节。
- 测试装配；后端全量 pytest + 隐私核对；提交文档。

## 计划自检

- 规格覆盖：任务 1 覆盖压缩逻辑；任务 2 覆盖 Agent 接入；任务 3 覆盖配置/装配/验证。
- 类型一致性：压缩返回 `list[Message]`，复用现有 Message/Session。
- 安全边界：best-effort 失败跳过；摘要只含 user/assistant 文本；tool 只保留工具名；幂等单摘要。

## 执行结果（2026-08-15）

- 3 个任务全部完成并提交（3 个 commit）：压缩器 → Agent 接入 → 配置/装配。
- 核心实现：`context_compression/compressor.py`（needs_compression/compress，保留最近 N 条 + LLM 摘要，`[对话摘要]` system 消息持久化，幂等单摘要，tool 只留工具名）；`core/agent.py` 在 `_build_messages` 超阈值压缩并 save；`ContextSettings`。
- 全量验证：后端 `435 passed, 3 skipped, 0 failed`（新增 13 条压缩测试全绿）。
- 隐私核对：摘要不含工具参数/结果/密钥；LLM 失败跳过压缩，对话不受影响。

