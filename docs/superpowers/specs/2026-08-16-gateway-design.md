# 多平台 Gateway 一期设计（QQ OneBot + 企业微信）

## 1. 背景与目标

iris-agent 目前只有 Web 对话入口。目标是把对话能力延伸到用户常用的聊天平台，一期覆盖：

- **QQ**：OneBot 11 协议（NapCat / LLOneBot / go-cqhttp），反向 WebSocket，本地可用。
- **微信**：企业微信自建应用（官方 API）。

单用户、无需鉴权，每个平台用户对应一个隔离的 agent 会话。

## 2. 架构

```
平台事件 ──▶ Adapter（解析）──▶ GatewayService ──▶ AgentService.run()
                                          │
                                          └──▶ 会话映射 (platform,user_id)→session_id
Adapter（回传）◀── 最终回复文本 ◀──────────┘
```

### 2.1 `GatewayService`（`iris_agent/gateway/service.py`）

- 负责会话映射：`(platform, user_id)` → 稳定的 `session_id`，复用现有 `SessionRepository`（每个平台用户一个独立会话，也会出现在 Web 会话列表）。
- 映射持久化到 `data/gateway/sessions.json`，重启不丢上下文。
- `handle(message) -> str`：调 `agent.run()` 收集最终回复；遇到 `tool_approval_requested`（MCP 非只读工具）自动拒绝（网关无审批 UI）。

### 2.2 适配器

| 适配器 | 入站 | 出站 |
|--------|------|------|
| `QQOneBotAdapter` | FastAPI WebSocket 端点（NapCat 反向 WS 连入） | 同一 WS 回发 `send_msg` action |
| `WeComAdapter` | HTTP 回调端点（验签 + AES 解密） | `message/send` 主动推送 |

## 3. QQ OneBot 11

- 端点：`GET /gateway/qq/ws`（WebSocket）。NapCat 配置反向 WS 地址为 `ws://127.0.0.1:8000/gateway/qq/ws`。
- 处理 `message` 事件：私聊总是响应；群聊默认忽略（`qq.respond_groups=true` 才响应，避免刷屏）。
- 文本提取：优先取 `message` 段的 `text` 段拼接，回退 `raw_message`。
- 回复：`send_msg` action，私聊带 `user_id`、群聊带 `group_id`。
- agent 调用通过 `asyncio.to_thread` 放入线程池，不阻塞事件循环。

## 4. 企业微信自建应用

- 主动推送：`access_token`（corpid+corpsecret）→ `message/send`，**本地可用**（无需公网）。
- 接收消息：回调 URL + `msg_signature` 验签 + AES-256-CBC 解密（`pycryptodome`）。**需公网可达的回调 URL**（或内网穿透），这是企业微信自建应用的硬约束。
- 回复采用主动推送而非同步回调响应，因为 agent 可能超过企微 5 秒回调窗口。
- 消息按 ~1900 字节分段推送。

## 5. 关键约束（重要）

- **QQ（OneBot）**：完全本地可用，双向对话闭环。
- **企业微信**：主动推送（agent→用户）本地可用；**接收用户消息（用户→agent）必须公网回调**，纯本地环境收不到。

## 6. 配置（`agent.yaml` 的 `gateway` 节）

```yaml
gateway:
  enabled: false
  directory: data/gateway
  session_prefix: gateway
  qq:
    enabled: false
    path: /gateway/qq/ws
    respond_groups: false
  wecom:
    enabled: false
    corp_id: ""
    agent_id: 0
    secret: ""
    token: ""
    aes_key: ""
    callback_path: /gateway/wecom/callback
```

## 7. 验证

- 后端全量测试（含 gateway 21 条单测 + 配置/装配测试）。
- 单元测试覆盖：会话映射稳定/持久化、审批自动拒绝、QQ 事件解析与群聊开关、企微加解密 roundtrip/验签/corp_id 校验、长文本分段。
