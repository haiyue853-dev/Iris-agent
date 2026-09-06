# 联网图标控制实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 `executing-plans` 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 让聊天输入框的联网图标成为联网工具的唯一开关，并在会话创建后锁定。

**架构：** 能力模式只提供基础、知识库和协作工具集；联网状态独立持久化。前端每次创建会话时将合并后的工具集传给后端，后端既有的运行时快照继续保证会话内权限不变。

**技术栈：** React、TypeScript、Vitest、FastAPI 既有聊天接口。

---

### 任务 1：工具集与联网状态

**文件：**
- 修改：`web-react/src/lib/capability-mode.ts`
- 创建：`web-react/src/lib/capability-mode.test.ts`

- [ ] **步骤 1：编写失败的测试**

```ts
expect(toolsetsForMode('research', false)).not.toContain('research');
expect(toolsetsForMode('daily', true)).toContain('research');
```

- [ ] **步骤 2：运行测试验证失败**

运行：`npm test -- --run src/lib/capability-mode.test.ts`

- [ ] **步骤 3：实现联网状态合并**

```ts
export function toolsetsForMode(mode: CapabilityMode, online = readOnlineSearchEnabled()): Toolset[] {
  const toolsets = [...MODE_TOOLSETS[mode]];
  return online ? [...toolsets, 'research'] : toolsets;
}
```

- [ ] **步骤 4：运行测试验证通过**

运行：`npm test -- --run src/lib/capability-mode.test.ts`

### 任务 2：联网图标交互

**文件：**
- 修改：`web-react/src/components/assistant-ui/prompt-preview-controls.tsx`
- 修改：`web-react/src/components/AssistantChat.tsx`
- 修改：`web-react/src/components/AssistantChat.composition.test.tsx`

- [ ] **步骤 1：编写失败的测试**

```tsx
await user.click(screen.getByRole('button', { name: '联网搜索' }));
expect(screen.getByRole('button', { name: '联网搜索' })).toHaveAttribute('aria-pressed', 'true');
```

- [ ] **步骤 2：运行测试验证失败**

运行：`npm test -- --run src/components/AssistantChat.composition.test.tsx`

- [ ] **步骤 3：实现开关与会话锁定**

```tsx
<button aria-pressed={online} disabled={capabilityModeLocked} onClick={toggleOnline}>
  <GlobeIcon /> <span>联网</span>
</button>
```

- [ ] **步骤 4：运行测试验证通过**

运行：`npm test -- --run src/components/AssistantChat.composition.test.tsx`

### 任务 3：定向验证

**文件：**
- 测试：`web-react/src/lib/capability-mode.test.ts`
- 测试：`web-react/src/components/AssistantChat.composition.test.tsx`

- [ ] **步骤 1：运行前端定向测试与构建**

运行：`npm test -- --run src/lib/capability-mode.test.ts src/components/AssistantChat.composition.test.tsx; npm run build`

- [ ] **步骤 2：检查改动格式**

运行：`git diff --check -- web-react/src/lib/capability-mode.ts web-react/src/lib/capability-mode.test.ts web-react/src/components/assistant-ui/prompt-preview-controls.tsx web-react/src/components/AssistantChat.tsx web-react/src/components/AssistantChat.composition.test.tsx`
