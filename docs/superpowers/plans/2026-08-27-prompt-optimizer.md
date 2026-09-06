# 提示词优化专家实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 提供内置提示词优化 Skill 和输入框魔杖按钮，将日常工作草稿优化后直接回填。

**架构：** 后端加载内置 Skill，以当前 Provider 执行不带工具和会话记录的一次性优化；前端通过 Composer Runtime 调用接口并替换草稿。优化请求和聊天发送完全分离。

**技术栈：** FastAPI、Python、React、TypeScript、Vitest、pytest。

---

### 任务 1：内置 Skill 与优化 API

**文件：**
- 创建：`iris_agent/skill_center/bundled/prompt-optimizer/SKILL.md`
- 修改：`iris_agent/api/schemas.py`
- 修改：`iris_agent/api/app.py`
- 修改：`iris_agent/core/agent.py`
- 测试：`tests/api/test_prompt_optimizer.py`

- [ ] **步骤 1：编写失败的 API 测试**

```python
response = client.post("/api/prompt/optimize", json={"prompt": "帮我写邮件"})
assert response.status_code == 200
assert response.json() == {"prompt": "优化后的提示词"}
```

- [ ] **步骤 2：运行测试验证失败**

运行：`$env:PYTHONPATH='D:\agent\Iris-agent'; pytest tests/api/test_prompt_optimizer.py -q --basetemp .tmp/prompt-red`

预期：FAIL，原因是优化路由尚不存在。

- [ ] **步骤 3：实现最少代码**

```python
def optimize_prompt(self, draft: str, instruction: str) -> str:
    response = self.loop.get_provider().complete(
        [Message(role="system", content=instruction), Message(role="user", content=draft)], []
    )
    return response.content.strip()
```

API 加载 `prompt-optimizer` Skill，拒绝空白输入，并返回 `{"prompt": result}`。

- [ ] **步骤 4：运行测试验证通过**

运行：`$env:PYTHONPATH='D:\agent\Iris-agent'; pytest tests/api/test_prompt_optimizer.py -q --basetemp .tmp/prompt-green`

预期：PASS。

### 任务 2：Composer 优化图标

**文件：**
- 创建：`web-react/src/api/prompt.ts`
- 修改：`web-react/src/components/assistant-ui/thread.tsx`
- 测试：`web-react/src/components/AssistantChat.composition.test.tsx`

- [ ] **步骤 1：编写失败的前端测试**

```tsx
expect(screen.getByRole("button", { name: "优化提示词" })).toBeVisible();
```

- [ ] **步骤 2：运行测试验证失败**

运行：`npm test -- --run src/components/AssistantChat.composition.test.tsx`

预期：FAIL，找不到“优化提示词”按钮。

- [ ] **步骤 3：实现最少代码**

```tsx
const optimized = await optimizePrompt(text);
runtime.setText(optimized);
```

使用 `WandSparklesIcon`、`TooltipIconButton` 和本地 loading 状态；空草稿或对话生成中时禁用按钮。

- [ ] **步骤 4：运行测试验证通过**

运行：`npm test -- --run src/components/AssistantChat.composition.test.tsx`

预期：PASS。

### 任务 3：定向验证

**文件：**
- 验证：`tests/api/test_prompt_optimizer.py`
- 验证：`web-react/src/components/AssistantChat.composition.test.tsx`

- [ ] **步骤 1：运行后端定向验证**

运行：`$env:PYTHONPATH='D:\agent\Iris-agent'; pytest tests/api/test_prompt_optimizer.py tests/api/test_skills.py -q --basetemp .tmp/prompt-final`

预期：PASS。

- [ ] **步骤 2：运行前端测试及构建**

运行：`npm test -- --run src/components/AssistantChat.composition.test.tsx; npm run build`

预期：测试与构建均为 exit 0。
