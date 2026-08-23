# Iris AI Elements 风格聊天页面重设计实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 在保留现有 assistant-ui 运行时和 Python API 的前提下，将 Iris 应用框架与聊天界面改造成接近 AI Elements Chatbot 示例的紧凑浅色设计，并将同一助手消息中的普通工具调用聚合为一个折叠小窗。

**架构：** `App`、`Sidebar` 和现有业务路由保持职责不变，只调整应用壳结构与主题；`Thread` 继续使用 assistant-ui primitives，但拆出欢迎区、输入区和消息内容的紧凑表现。工具聚合在 `irisRuntime` 的消息部件转换层完成：审批调用保留独立工具部件，其他工具调用组成一个合成的 `iris_tool_group` 部件，由专用组件渲染聚合状态和逐项详情。

**技术栈：** React 19、TypeScript、assistant-ui 0.12、Tailwind CSS 4、Vitest、Testing Library、Vite、oxlint。

---

## 文件结构

- 创建 `web-react/src/components/assistant-ui/tool-group.tsx`：渲染消息级工具聚合窗和单项详情。
- 创建 `web-react/src/components/assistant-ui/tool-group.test.tsx`：覆盖折叠、状态摘要、逐项详情和审批排除后的输入。
- 创建 `web-react/src/components/assistant-ui/thread.test.tsx`：覆盖欢迎区、消息语义、推理/来源折叠和输入区可访问性。
- 修改 `web-react/src/lib/irisRuntime.ts`：把普通工具调用转换成单个合成工具组部件，审批调用保持独立。
- 修改 `web-react/src/lib/irisRuntime.parts.test.ts`：覆盖聚合数据、流式状态、失败/取消和审批分离。
- 修改 `web-react/src/components/assistant-ui/tool-fallback.tsx`：识别合成工具组并交给 `ToolGroup`，保留审批卡路径。
- 修改 `web-react/src/components/assistant-ui/thread.tsx`：实现 AI Elements 风格欢迎区、消息、输入区、推理与来源布局。
- 修改 `web-react/src/components/assistant-ui/reasoning.tsx`：收敛成紧凑折叠行。
- 修改 `web-react/src/components/assistant-ui/sources.tsx`：收敛成“使用 N 个来源”折叠行。
- 修改 `web-react/src/components/Sidebar.tsx`：重排品牌、导航、历史会话和底部设置的语义结构。
- 修改 `web-react/src/components/Sidebar.test.tsx`：覆盖桌面折叠、移动展开和现有入口保留。
- 修改 `web-react/src/App.tsx`：给应用壳与主内容区增加稳定的 AI Elements 风格类名，不改变路由。
- 修改 `web-react/src/App.test.tsx`：覆盖应用壳、导航和聊天区组合。
- 修改 `web-react/src/index.css`：定义新的中性主题变量与基础页面背景。
- 修改 `web-react/src/App.css`：在文件末尾增加作用域明确的新版应用壳、侧栏、聊天和响应式样式；不重写业务页面内部样式。
- 修改 `web-react/tests/ChatLayout.theme.test.ts`：锁定关键布局类与主题规则。
- 修改 `web-react/tests/Sidebar.theme.test.ts`：锁定侧栏宽度、折叠和窄屏规则。

### 任务 1：建立新版主题和应用壳

**文件：**
- 修改：`web-react/src/App.tsx`
- 修改：`web-react/src/index.css`
- 修改：`web-react/src/App.css`
- 修改：`web-react/src/App.test.tsx`
- 修改：`web-react/tests/ChatLayout.theme.test.ts`

- [ ] **步骤 1：编写失败的应用壳测试**

在 `App.test.tsx` 增加断言，要求根布局具有新版语义类名：

```tsx
it('renders the AI Elements inspired application shell', async () => {
  render(<App />);
  expect(document.querySelector('.iris-app-shell')).toBeInTheDocument();
  expect(screen.getByRole('main')).toHaveClass('iris-main-surface');
});
```

在 `tests/ChatLayout.theme.test.ts` 增加文本级主题检查：

```ts
it('defines the neutral application shell and chat surface', () => {
  const css = readFileSync(resolve('src/App.css'), 'utf8');
  expect(css).toContain('.iris-app-shell');
  expect(css).toContain('.iris-main-surface');
  expect(css).toContain('background: var(--aui-page)');
});
```

- [ ] **步骤 2：运行测试并确认因类名和主题规则缺失而失败**

运行：`npm test -- --run src/App.test.tsx tests/ChatLayout.theme.test.ts`

预期：FAIL，缺少 `.iris-app-shell`、`.iris-main-surface` 或 `--aui-page` 规则。

- [ ] **步骤 3：实现最小应用壳与主题变量**

将 `App.tsx` 顶层结构改为：

```tsx
<div className="iris-app-shell">
  <Sidebar {...sidebarProps} />
  <main className="main-content iris-main-surface" aria-label={mainLabel}>
    {content}
  </main>
</div>
```

在 `index.css` 的 `@theme` 中定义：

```css
--color-background: #ffffff;
--color-foreground: #18181b;
--color-muted: #f4f4f5;
--color-muted-foreground: #71717a;
--color-border: #e4e4e7;
--color-ring: #a1a1aa;
```

在 `App.css` 末尾增加新版作用域规则：

```css
:root {
  --aui-page: #ffffff;
  --aui-panel: #fafafa;
  --aui-soft: #f4f4f5;
  --aui-border: #e4e4e7;
  --aui-text: #18181b;
  --aui-muted: #71717a;
}
.iris-app-shell { display: flex; width: 100%; height: 100dvh; overflow: hidden; background: var(--aui-page); color: var(--aui-text); }
.iris-main-surface { min-width: 0; flex: 1; background: var(--aui-page); }
```

- [ ] **步骤 4：运行聚焦测试并确认通过**

运行：`npm test -- --run src/App.test.tsx tests/ChatLayout.theme.test.ts`

预期：PASS。

- [ ] **步骤 5：提交本任务（仅当仓库已初始化 Git）**

```bash
git add web-react/src/App.tsx web-react/src/index.css web-react/src/App.css web-react/src/App.test.tsx web-react/tests/ChatLayout.theme.test.ts
git commit -m "feat: add AI Elements inspired app shell"
```

当前工作区没有 `.git` 时跳过提交，但不要跳过测试。

### 任务 2：重设计完整侧栏

**文件：**
- 修改：`web-react/src/components/Sidebar.tsx`
- 修改：`web-react/src/components/Sidebar.test.tsx`
- 修改：`web-react/src/App.css`
- 修改：`web-react/tests/Sidebar.theme.test.ts`

- [ ] **步骤 1：编写失败的侧栏行为测试**

在 `Sidebar.test.tsx` 增加：

```tsx
it('keeps brand, create action, navigation, conversations and settings in the compact sidebar', () => {
  renderSidebar({ sessions: [{ id: 's1', name: '设计讨论', updated_at: 1 }] });
  expect(screen.getByText('Iris')).toBeVisible();
  expect(screen.getByRole('button', { name: /新建会话/ })).toBeVisible();
  expect(screen.getByRole('navigation', { name: '功能导航' })).toBeVisible();
  expect(screen.getByRole('navigation', { name: '历史对话' })).toBeVisible();
  expect(screen.getByRole('button', { name: '设置' })).toBeVisible();
});
```

增加折叠状态断言：

```tsx
it('exposes the collapsed state on the sidebar shell', () => {
  const { container } = renderSidebar({ collapsed: true });
  expect(container.querySelector('.iris-sidebar')).toHaveAttribute('data-collapsed', 'true');
});
```

- [ ] **步骤 2：运行测试并确认语义导航和新版类名缺失**

运行：`npm test -- --run src/components/Sidebar.test.tsx tests/Sidebar.theme.test.ts`

预期：FAIL，找不到命名导航或 `.iris-sidebar`。

- [ ] **步骤 3：重排侧栏结构但保留全部事件接口**

将侧栏根节点和两组导航改为：

```tsx
<aside className="sidebar iris-sidebar" data-collapsed={collapsed}>
  <div className="iris-sidebar-brand">...</div>
  <button className="iris-new-chat" onClick={onNewChat}>...</button>
  <nav aria-label="功能导航" className="iris-primary-nav">...</nav>
  <nav aria-label="历史对话" className="iris-session-nav">...</nav>
  <div className="iris-sidebar-footer">...</div>
</aside>
```

保留 `onViewChange`、`onSessionSwitch`、`onSessionDelete`、确认删除和设置弹窗逻辑。为原先用 `div` 承载的可点击功能入口和会话行改用 `button type="button"`，保证键盘操作。

- [ ] **步骤 4：增加紧凑侧栏和响应式样式**

在 `App.css` 末尾新增：

```css
.iris-sidebar { width: 260px; padding: 10px; border-right: 1px solid var(--aui-border); background: var(--aui-panel); }
.iris-sidebar[data-collapsed='true'] { width: 0; padding-inline: 0; border-right: 0; }
.iris-primary-nav, .iris-session-nav { display: grid; gap: 2px; }
.iris-session-nav { min-height: 0; flex: 1; overflow-y: auto; }
.iris-new-chat, .iris-primary-nav button, .iris-session-nav button { min-height: 36px; border-radius: 9px; }
@media (max-width: 720px) {
  .iris-sidebar { position: fixed; inset: 0 auto 0 0; z-index: 50; width: min(86vw, 300px); box-shadow: 12px 0 32px rgb(0 0 0 / 10%); }
}
```

- [ ] **步骤 5：运行侧栏测试并确认通过**

运行：`npm test -- --run src/components/Sidebar.test.tsx tests/Sidebar.theme.test.ts`

预期：PASS。

- [ ] **步骤 6：提交本任务（Git 可用时）**

```bash
git add web-react/src/components/Sidebar.tsx web-react/src/components/Sidebar.test.tsx web-react/src/App.css web-react/tests/Sidebar.theme.test.ts
git commit -m "feat: redesign Iris sidebar"
```

### 任务 3：重设计欢迎区、消息列和组合输入框

**文件：**
- 创建：`web-react/src/components/assistant-ui/thread.test.tsx`
- 修改：`web-react/src/components/assistant-ui/thread.tsx`
- 修改：`web-react/src/App.css`
- 修改：`web-react/tests/ChatLayout.theme.test.ts`
- 验证：`web-react/src/components/AssistantChat.composition.test.tsx`

- [ ] **步骤 1：编写失败的聊天结构测试**

使用一个最小 `useLocalRuntime` 测试包装器渲染 `Thread`，断言：

```tsx
expect(screen.getByRole('heading', { name: '有什么我可以帮你？' })).toBeVisible();
expect(screen.getByRole('textbox', { name: '消息输入框' })).toBeVisible();
expect(screen.getByRole('button', { name: '添加附件' })).toBeVisible();
expect(screen.getByRole('button', { name: '发送消息' })).toBeDisabled();
expect(container.querySelector('.iris-conversation')).toBeInTheDocument();
expect(container.querySelector('.iris-prompt-input')).toBeInTheDocument();
```

- [ ] **步骤 2：运行测试并确认新版语义和类名缺失**

运行：`npm test -- --run src/components/assistant-ui/thread.test.tsx src/components/AssistantChat.composition.test.tsx tests/ChatLayout.theme.test.ts`

预期：新增测试 FAIL；现有中文组合输入测试仍 PASS。

- [ ] **步骤 3：拆分 Thread 内部表现组件**

在 `thread.tsx` 内保持文件级私有组件，整理为：

```tsx
const ThreadWelcome: FC = () => <section className="iris-chat-welcome">...</section>;
const Composer: FC = () => <ComposerPrimitive.Root className="iris-prompt-input">...</ComposerPrimitive.Root>;
const AssistantMessage: FC = () => <MessagePrimitive.Root className="iris-assistant-message">...</MessagePrimitive.Root>;
const UserMessage: FC = () => <MessagePrimitive.Root className="iris-user-message">...</MessagePrimitive.Root>;
```

将输入框 `aria-label` 改为“消息输入框”，保留 `ImeSafeComposerInput` 的 `draft`、`compositionRef` 和同步逻辑，不以示例的普通受控 textarea 替换它。

- [ ] **步骤 4：添加 AI Elements 风格聊天样式**

在 `App.css` 末尾增加：

```css
.iris-conversation { height: 100%; background: var(--aui-page); }
.iris-chat-viewport { padding: 0 24px; }
.iris-chat-welcome, .iris-thread-width { width: min(100%, 768px); margin-inline: auto; }
.iris-assistant-message { padding-block: 18px; }
.iris-user-message { display: flex; justify-content: flex-end; padding-block: 12px; }
.iris-user-message-content { max-width: min(80%, 620px); border-radius: 18px; background: var(--aui-soft); padding: 10px 14px; }
.iris-composer-dock { position: sticky; bottom: 0; padding: 16px 0 24px; background: linear-gradient(transparent, var(--aui-page) 28%); }
.iris-prompt-input { border: 1px solid var(--aui-border); border-radius: 20px; background: #fff; box-shadow: 0 8px 30px rgb(0 0 0 / 6%); }
```

- [ ] **步骤 5：运行聊天结构与中文输入测试**

运行：`npm test -- --run src/components/assistant-ui/thread.test.tsx src/components/AssistantChat.composition.test.tsx tests/ChatLayout.theme.test.ts`

预期：PASS，且中文输入测试继续证明组合输入期间文字不被清空。

- [ ] **步骤 6：提交本任务（Git 可用时）**

```bash
git add web-react/src/components/assistant-ui/thread.tsx web-react/src/components/assistant-ui/thread.test.tsx web-react/src/components/AssistantChat.composition.test.tsx web-react/src/App.css web-react/tests/ChatLayout.theme.test.ts
git commit -m "feat: redesign chat conversation and composer"
```

### 任务 4：收敛推理与来源折叠项

**文件：**
- 修改：`web-react/src/components/assistant-ui/reasoning.tsx`
- 修改：`web-react/src/components/assistant-ui/sources.tsx`
- 修改：`web-react/src/components/assistant-ui/thread.test.tsx`
- 修改：`web-react/src/App.css`
- 修改：`web-react/tests/ThreadRichParts.theme.test.ts`

- [ ] **步骤 1：编写失败的折叠语义测试**

在 `thread.test.tsx` 用包含 reasoning 和两个 source 部件的初始消息断言：

```tsx
expect(screen.getByRole('button', { name: /思考过程/ })).toHaveAttribute('aria-expanded', 'false');
expect(screen.getByRole('button', { name: '使用 2 个来源' })).toHaveAttribute('aria-expanded', 'false');
```

点击后断言内容可见：

```tsx
await user.click(screen.getByRole('button', { name: /思考过程/ }));
expect(screen.getByText('分析用户问题')).toBeVisible();
```

- [ ] **步骤 2：运行测试并确认当前标签或默认状态不匹配**

运行：`npm test -- --run src/components/assistant-ui/thread.test.tsx tests/ThreadRichParts.theme.test.ts`

预期：FAIL，缺少指定中文标签或默认折叠语义。

- [ ] **步骤 3：实现紧凑折叠触发器**

在 `reasoning.tsx` 使用 `ReasoningPrimitive.Root` 与 trigger，默认 `open={false}`，触发器文案为运行中“正在思考…”、完成后“思考过程”。在 `sources.tsx` 通过来源数量渲染“使用 {count} 个来源”，内容区只在展开时显示来源链接。

统一触发器类名：

```tsx
className="iris-inline-disclosure"
```

- [ ] **步骤 4：添加紧凑样式并运行测试**

```css
.iris-inline-disclosure { display: inline-flex; align-items: center; gap: 6px; min-height: 28px; color: var(--aui-muted); font-size: 13px; }
.iris-inline-disclosure-content { margin-top: 6px; padding-left: 20px; color: var(--aui-muted); }
```

运行：`npm test -- --run src/components/assistant-ui/thread.test.tsx tests/ThreadRichParts.theme.test.ts`

预期：PASS。

- [ ] **步骤 5：提交本任务（Git 可用时）**

```bash
git add web-react/src/components/assistant-ui/reasoning.tsx web-react/src/components/assistant-ui/sources.tsx web-react/src/components/assistant-ui/thread.test.tsx web-react/src/App.css web-react/tests/ThreadRichParts.theme.test.ts
git commit -m "feat: compact reasoning and source disclosures"
```

### 任务 5：定义工具聚合数据结构并在运行时生成

**文件：**
- 修改：`web-react/src/lib/irisRuntime.ts`
- 修改：`web-react/src/lib/irisRuntime.parts.test.ts`

- [ ] **步骤 1：编写失败的工具聚合转换测试**

为两个普通工具事件输入增加断言：

```ts
expect(latest.content).toContainEqual(expect.objectContaining({
  type: 'tool-call',
  toolName: 'iris_tool_group',
  result: expect.objectContaining({
    __irisKind: 'tool-group',
    items: [
      expect.objectContaining({ callId: 'c1', name: 'list_directory' }),
      expect.objectContaining({ callId: 'c2', name: 'read_file' }),
    ],
  }),
}));
```

再加入一个审批事件，断言 `iris_tool_group` 仅含普通工具，同时审批工具部件仍以原 `toolName` 存在。

- [ ] **步骤 2：运行测试并确认当前输出为多个独立工具部件**

运行：`npm test -- --run src/lib/irisRuntime.parts.test.ts`

预期：FAIL，找不到 `iris_tool_group`。

- [ ] **步骤 3：定义聚合类型与纯构建函数**

在 `irisRuntime.ts` 增加：

```ts
export type IrisToolGroupItem = {
  callId: string;
  name: string;
  args: Record<string, unknown>;
  argsText: string;
  result?: unknown;
  state: 'running' | 'completed' | 'failed' | 'cancelled';
  error?: string;
};

export type IrisToolGroupResult = {
  __irisKind: 'tool-group';
  items: IrisToolGroupItem[];
};
```

新增 `buildContent()` 逻辑：遍历 `toolParts`，将 `result.__irisKind === 'approval'` 的部件原样加入；其余部件映射为 `IrisToolGroupItem`，有项目时仅加入一个 `toolName: 'iris_tool_group'` 的合成工具部件。

- [ ] **步骤 4：补齐运行、成功、失败和取消映射**

在 `applyEvent` 中保证：

```ts
tool_started  -> state: 'running'
tool_finished ok=true -> state: 'completed'
tool_finished ok=false -> state: 'failed'
error/abort 且能关联 callId -> state: 'cancelled' 或 'failed'
```

无法关联具体调用的流错误继续走消息级 `incomplete`，不伪造工具错误。

- [ ] **步骤 5：运行运行时测试并确认通过**

运行：`npm test -- --run src/lib/irisRuntime.parts.test.ts`

预期：PASS。

- [ ] **步骤 6：提交本任务（Git 可用时）**

```bash
git add web-react/src/lib/irisRuntime.ts web-react/src/lib/irisRuntime.parts.test.ts
git commit -m "feat: aggregate assistant tool parts"
```

### 任务 6：实现工具聚合小窗

**文件：**
- 创建：`web-react/src/components/assistant-ui/tool-group.tsx`
- 创建：`web-react/src/components/assistant-ui/tool-group.test.tsx`
- 修改：`web-react/src/components/assistant-ui/tool-fallback.tsx`
- 修改：`web-react/src/App.css`

- [ ] **步骤 1：编写失败的 ToolGroup 组件测试**

覆盖默认折叠和摘要：

```tsx
render(<ToolGroup result={{ __irisKind: 'tool-group', items: completedItems(4) }} />);
const trigger = screen.getByRole('button', { name: '已执行 4 个工具' });
expect(trigger).toHaveAttribute('aria-expanded', 'false');
expect(screen.queryByText('list_directory')).not.toBeInTheDocument();
```

覆盖展开和单项详情：

```tsx
await user.click(trigger);
await user.click(screen.getByRole('button', { name: /list_directory/ }));
expect(screen.getByText('参数')).toBeVisible();
expect(screen.getByText('结果')).toBeVisible();
```

分别断言运行中、失败和取消标题：“正在执行 2 个工具”“有 1 个工具执行失败”“有 1 个工具已取消”。

- [ ] **步骤 2：运行测试并确认组件不存在**

运行：`npm test -- --run src/components/assistant-ui/tool-group.test.tsx`

预期：FAIL，模块或组件不存在。

- [ ] **步骤 3：实现聚合摘要和折叠列表**

`tool-group.tsx` 导出：

```tsx
export function ToolGroup({ result }: { result: IrisToolGroupResult }) {
  const [open, setOpen] = useState(false);
  return (
    <section className="iris-tool-group">
      <button className="iris-tool-group-trigger" aria-expanded={open} onClick={() => setOpen(v => !v)}>
        {summaryFor(result.items)}
      </button>
      {open && <div className="iris-tool-group-list">...</div>}
    </section>
  );
}
```

每个单项使用自己的 `openItemIds: Set<string>`；列表行显示状态图标、工具名称和状态标签。参数和结果使用 `pre`，失败与取消用文字区分。

- [ ] **步骤 4：复用终端详情而不放大折叠头**

当工具名属于现有 `TERMINAL_TOOLS` 且结果含 `stdout`、`stderr` 或 `command` 时，在单项展开区域渲染 `Terminal`；其他工具渲染 JSON 参数与结果。将 `TERMINAL_TOOLS` 移到 `tool-group.tsx` 导出的共享常量，`tool-fallback.tsx` 引用它，避免重复。

- [ ] **步骤 5：让 ToolFallback 路由合成工具组**

在审批判断之后、终端判断之前加入：

```tsx
if (result && typeof result === 'object' && (result as IrisToolGroupResult).__irisKind === 'tool-group') {
  return <ToolGroup result={result as IrisToolGroupResult} />;
}
```

- [ ] **步骤 6：添加紧凑工具窗样式**

```css
.iris-tool-group { margin: 8px 0; border: 1px solid var(--aui-border); border-radius: 12px; background: var(--aui-panel); overflow: hidden; }
.iris-tool-group-trigger { width: 100%; min-height: 38px; display: flex; align-items: center; gap: 8px; padding: 8px 12px; border: 0; background: transparent; text-align: left; }
.iris-tool-group-list { border-top: 1px solid var(--aui-border); padding: 4px 8px 8px; }
.iris-tool-row { width: 100%; min-height: 34px; border-radius: 8px; }
.iris-tool-detail { margin: 0 4px 6px; padding: 10px; border-radius: 8px; background: #fff; font-size: 12px; }
```

- [ ] **步骤 7：运行工具组件和运行时测试**

运行：`npm test -- --run src/components/assistant-ui/tool-group.test.tsx src/lib/irisRuntime.parts.test.ts`

预期：PASS。

- [ ] **步骤 8：提交本任务（Git 可用时）**

```bash
git add web-react/src/components/assistant-ui/tool-group.tsx web-react/src/components/assistant-ui/tool-group.test.tsx web-react/src/components/assistant-ui/tool-fallback.tsx web-react/src/App.css
git commit -m "feat: add compact grouped tool window"
```

### 任务 7：响应式与完整回归验证

**文件：**
- 修改：`web-react/src/App.css`
- 修改：`web-react/tests/ChatLayout.theme.test.ts`
- 修改：`web-react/tests/Sidebar.theme.test.ts`
- 修改：`web-react/src/App.test.tsx`

- [ ] **步骤 1：编写失败的窄屏规则测试**

在主题测试中断言存在：

```ts
expect(css).toContain('@media (max-width: 720px)');
expect(css).toContain('.iris-chat-viewport');
expect(css).toContain('.iris-sidebar');
expect(css).toContain('width: min(86vw, 300px)');
```

在 `App.test.tsx` 模拟 `window.innerWidth = 600`，断言初始侧栏折叠，并可通过“展开侧边栏”按钮打开。

- [ ] **步骤 2：运行测试并确认缺少最终窄屏行为**

运行：`npm test -- --run src/App.test.tsx tests/ChatLayout.theme.test.ts tests/Sidebar.theme.test.ts`

预期：FAIL，直到移动端布局规则和打开行为齐全。

- [ ] **步骤 3：完成桌面与窄屏样式**

补充规则：桌面消息最大宽度 768px；720px 以下聊天左右 padding 为 12px、输入 dock 底部 padding 为 12px、用户气泡最大宽度 88%；侧栏以覆盖层打开且不挤压主内容。确保 `.main-content`、`.aui-thread-root` 和业务页根节点都有 `min-width: 0`。

- [ ] **步骤 4：运行所有前端测试**

运行：`npm test -- --run`

预期：全部测试 PASS，0 failed。

- [ ] **步骤 5：运行构建和 lint**

运行：`npm run build`

预期：退出码 0；允许现有 chunk size warning。

运行：`npm run lint`

预期：退出码 0；不得新增与本次文件相关的 warning，项目既有 `only-export-components` warning 可记录但不扩展范围处理。

- [ ] **步骤 6：浏览器桌面验收**

启动应用后在 `http://localhost:5173/` 验证：

1. 左侧栏包含全部现有业务入口、历史会话与设置。
2. 新会话欢迎区和输入框布局接近 AI Elements 示例。
3. 输入“中文测试 123”后文字持续保留；清空测试文字，不发送。
4. 切换历史会话后输入框仍可用。
5. 包含多个工具的消息只出现一个默认折叠的工具小窗。
6. 展开聚合窗后可展开单个工具并查看参数与结果。
7. 审批卡独立显示且批准/拒绝按钮可见；不实际触发有副作用的审批。

- [ ] **步骤 7：浏览器窄屏验收**

将浏览器 viewport 设为 390×844，验证侧栏默认折叠、展开后覆盖主内容、消息无水平滚动、输入框和发送按钮完整可见；验收后恢复默认 viewport。

- [ ] **步骤 8：提交最终验证调整（Git 可用时）**

```bash
git add web-react/src/App.css web-react/src/App.test.tsx web-react/tests/ChatLayout.theme.test.ts web-react/tests/Sidebar.theme.test.ts
git commit -m "test: verify responsive AI chat redesign"
```

## 最终完成标准

- 设计规格中的页面框架、聊天区域、输入区、推理、来源、工具聚合、错误和可访问性均有对应实现与测试。
- 普通工具无论一项或多项都只显示一个默认折叠聚合窗；审批卡不被聚合。
- 中文输入法回归测试继续通过。
- `npm test -- --run`、`npm run build`、`npm run lint` 均以退出码 0 完成。
- 桌面与 390px 窄屏浏览器验收完成，未发送测试消息、未执行工具审批。
