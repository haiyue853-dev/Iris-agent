# 设计规格：用户建模 / 画像（一期）

日期：2026-08-15
分支：feature/user-profile（计划）
参考：hermes `agent/memory_provider.py`（`on_session_end` 提取钩子）、Honcho 式画像

## 1. 背景与目标

iris 已有 P1 记忆（通用条目：`remember` 工具 + 注入）和 P2 会话搜索（`recall` 工具）。但记忆是**零散、任意内容**的条目集合，缺少一份「**这个用户是谁**」的稳定结构化快照。

用户画像的目标：从对话中**自动沉淀**用户的长期维度——称呼、偏好、目标、沟通风格、长期事实——形成一份结构化的 `UserProfile`，每次对话开始自动注入，让 Agent 无需用户重复自我介绍即可「认识」用户。

## 2. 与 P1 记忆的关系（不重复）

| 维度 | P1 记忆 | 用户画像 |
|------|---------|----------|
| 内容 | 零散通用条目（任意内容） | 结构化「用户是谁」 |
| 字段 | content + category | name/preferences/goals/style/facts |
| 沉淀 | Agent 主动 `remember` / 手动 | **自动提取**（LLM 从对话沉淀）+ 手动编辑 |
| 注入 | 最近 20 条记忆 | 单份画像快照 |

两者并存互补：记忆回答「用户说过什么」，画像回答「用户是什么样的人」。

## 3. 数据模型

新模块 `iris_agent/profile/`：

```python
# models.py
@dataclass(slots=True)
class UserProfile:
    name: str = ""
    preferences: list[str] = field(default_factory=list)
    goals: list[str] = field(default_factory=list)
    style: str = ""
    facts: list[str] = field(default_factory=list)
    updated_at: str = ""

@dataclass(slots=True)
class ProfilePatch:
    """LLM 提取的增量，字段 None 表示无更新。"""
    name: str | None = None
    preferences: list[str] | None = None
    goals: list[str] | None = None
    style: str | None = None
    facts: list[str] | None = None
```

单用户单画像（iris 无登录）。存储 `data/profile/profile.json`，复用 JSON 原子写 + Windows 文件锁。

## 4. 自动提取流程

```
AgentService.run 消费完一轮（message_completed 后）
  → ProfileService.maybe_update(本轮对话文本)
      → 节流判断：距上次提取 >= N 轮（默认 10）或画像为空 → 提取；否则跳过
      → ProfileExtractor.extract(对话文本) → ProfilePatch
          → 用同一 provider，system 提示「提取用户画像」，要求输出 JSON
      → ProfileService.apply_patch(patch) → merge 去重 → 持久化
```

- **best-effort**：提取失败（LLM 报错/JSON 解析失败）静默跳过，绝不影响主对话。
- **节流**：默认每 10 轮提取一次，控制额外 LLM 调用成本。
- **同步执行**：与 iris 现有同步 `AgentLoop` 一致，在 task_queue 后台线程里跑，不阻塞前端。

## 5. 注入

`AgentService._build_messages` 在 system_prompt 之后、记忆之前注入：

```
[画像] 称呼：小明；偏好：中文简洁回答；目标：构建个人 agent；风格：直接务实；事实：后端工程师
```

画像为空时不注入。render 结果总长 ≤ 800 字。

## 6. 配置

`agent.yaml` 新增 `profile:` 节 → `ProfileSettings`：

| 键 | 默认 | 说明 |
|----|------|------|
| `directory` | data/profile | 存储目录 |
| `max_items_per_field` | 20 | 每个列表字段上限 |
| `max_item_chars` | 200 | 单条截断 |
| `extract_interval_rounds` | 10 | 提取节流轮数 |
| `enabled` | true | 是否启用自动提取 |

## 7. API（一期不做前端页面）

- `GET /api/profile` — 读取画像
- `PUT /api/profile` — 手动覆盖（白名单字段校验 + 截断）
- 一期不做前端画像页面，画像能力通过自动提取 + API 提供；前端页面留后续。

## 8. 一期不做

- 多画像/多用户（无登录）。
- 画像历史版本 / 回滚。
- 画像与记忆的自动互转。
- 异步提取（跨线程 LLM 调用）。

## 9. 验收标准

- [ ] 画像从对话中自动提取并持久化。
- [ ] 新会话开始自动注入画像。
- [ ] 节流生效（每 N 轮提取一次）。
- [ ] 提取失败不影响主对话。
- [ ] GET/PUT /api/profile 可用，字段白名单校验。
- [ ] 后端全量测试通过，隐私核对（画像只含用户维度，不含工具参数/密钥）。
