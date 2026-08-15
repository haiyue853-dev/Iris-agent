# 设计规格：上下文压缩（一期）

日期：2026-08-15
分支：feature/context-compression（计划）
参考：hermes `agent/context_compressor.py`、`conversation_compression.py`（取精简版）

## 1. 背景与目标

iris 的会话是**无限增长**的：`Session.messages` 每次对话都追加，永不裁剪。会话越长，每轮发给模型的上下文越大，token 成本与延迟持续上升。

目标：当会话超过阈值时，**自动把早期对话压缩成一段摘要**，用「摘要 + 最近若干条」替换完整历史，让模型永远只看到有限窗口。

hermes 的压缩器极其复杂（token 预算、skill 裁剪、图片剥离、会话旋转、锁），iris 一期只取**核心闭环**：阈值触发 → LLM 摘要 → 持久化摘要。

## 2. 核心流程

```
AgentService._build_messages(session)
  → ContextCompressor.needs_compression(session.messages)?
      → 总字符 > trigger_chars（默认 12000）→ 是
      → ContextCompressor.compress(messages)
          → 保留最近 keep_recent 条（默认 10）
          → 早期消息（含旧摘要）用 LLM 总结成 ≤ max_summary_chars 摘要
          → 返回 [摘要 system 消息, ...最近 keep_recent 条]
      → 写回 session.messages 并 save
  → 用压缩后的消息组装（system_prompt + 画像 + 记忆 + session.messages）
```

## 3. 摘要表示

摘要作为一条 `role=system` 的消息，`content` 以 `[对话摘要] ` 为前缀，持久化到会话 JSON。

- **幂等**：再次压缩时，若开头已有 `[对话摘要]` 消息，它与中间消息一起被并入新摘要，始终保持单条摘要。
- **隐私**：摘要只基于 user/assistant 文本；`tool` 消息仅保留工具名，不含参数、结果、密钥。

## 4. 配置

`agent.yaml` 新增 `context:` 节 → `ContextSettings`：

| 键 | 默认 | 说明 |
|----|------|------|
| `trigger_chars` | 12000 | 触发压缩的总字符阈值 |
| `keep_recent` | 10 | 保留最近消息条数 |
| `max_summary_chars` | 2000 | 摘要上限 |
| `enabled` | true | 是否启用 |

## 5. 安全与边界

- **best-effort**：LLM 摘要失败时跳过本次压缩，绝不影响对话。
- **不丢信息**：压缩只影响「发送给模型」的历史，记忆（P1）与画像已独立持久化，不随压缩丢失。
- **隐私**：摘要不含工具参数/结果/密钥。

## 6. 一期不做

- token 级预算估算（用字符数近似）。
- 会话旋转（把被压缩部分另存归档）。
- 压缩并发锁 / 心跳（iris 单用户串行，无需）。
- 异步压缩。

## 7. 验收标准

- [ ] 会话超过阈值自动压缩，模型收到「摘要 + 最近消息」。
- [ ] 摘要持久化，重复压缩幂等（始终单条摘要）。
- [ ] 摘要不含工具参数/结果/密钥。
- [ ] LLM 失败时跳过压缩，对话不受影响。
- [ ] 后端全量测试通过。
