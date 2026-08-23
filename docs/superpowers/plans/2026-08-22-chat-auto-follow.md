# 聊天流式输出自动追底实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 流式回复增长时智能跟随底部，同时在用户向上阅读历史消息时暂停追底。

**架构：** 新建一个独立的自动追底控制器与 React hook，控制器负责底部阈值和状态，hook 负责连接滚动视口、DOM 内容变化和浏览器绘制周期。`Thread` 只负责把视口 ref、滚动事件、发送事件和现有回底按钮接入 hook。

**技术栈：** React 19、TypeScript、assistant-ui、Vitest、Testing Library、MutationObserver、requestAnimationFrame

---

## 文件结构

- 创建 `web-react/src/components/assistant-ui/use-chat-auto-follow.ts`：封装追底状态、阈值判断、DOM 变化监听和恢复行为。
- 创建 `web-react/tests/ChatAutoFollow.test.ts`：验证追底、暂停和恢复行为。
- 修改 `web-react/src/components/assistant-ui/thread.tsx`：把 hook 接到聊天视口、发送动作和现有回底按钮。
- 修改 `web-react/tests/ChatLayout.theme.test.ts`：验证线程组件保留自动追底接线。

### 任务 1：自动追底控制器

**文件：**
- 创建：`web-react/src/components/assistant-ui/use-chat-auto-follow.ts`
- 创建：`web-react/tests/ChatAutoFollow.test.ts`

- [ ] **步骤 1：编写失败的控制器测试**

```ts
it("follows growth while near the bottom", () => {
  const viewport = fakeViewport({ scrollTop: 700, clientHeight: 300, scrollHeight: 1000 });
  const controller = createChatAutoFollowController(() => viewport, runNow);
  viewport.scrollHeight = 1100;
  controller.onContentChange();
  expect(viewport.scrollTop).toBe(1100);
});

it("pauses after the user scrolls away and resumes explicitly", () => {
  const viewport = fakeViewport({ scrollTop: 400, clientHeight: 300, scrollHeight: 1000 });
  const controller = createChatAutoFollowController(() => viewport, runNow);
  controller.onScroll();
  viewport.scrollHeight = 1200;
  controller.onContentChange();
  expect(viewport.scrollTop).toBe(400);
  controller.resume();
  expect(viewport.scrollTop).toBe(1200);
});
```

- [ ] **步骤 2：运行测试并验证红灯**

运行：`npm test -- --run tests/ChatAutoFollow.test.ts`

预期：FAIL，因为 `createChatAutoFollowController` 尚不存在。

- [ ] **步骤 3：实现最小控制器**

```ts
export const AUTO_FOLLOW_THRESHOLD = 100;

export function createChatAutoFollowController(
  getViewport: () => HTMLElement | null,
  schedule: (callback: () => void) => void,
) {
  let isFollowing = true;
  const scrollToBottom = () => {
    const viewport = getViewport();
    if (viewport) viewport.scrollTop = viewport.scrollHeight;
  };
  return {
    onScroll() {
      const viewport = getViewport();
      if (!viewport) return;
      isFollowing = viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight <= AUTO_FOLLOW_THRESHOLD;
    },
    onContentChange() {
      if (isFollowing) schedule(scrollToBottom);
    },
    resume() {
      isFollowing = true;
      schedule(scrollToBottom);
    },
  };
}
```

- [ ] **步骤 4：实现 React hook 接线**

`useChatAutoFollow` 返回 `viewportRef`、`onScroll` 和 `resume`。在 effect 中对视口建立 `{ childList: true, characterData: true, subtree: true }` 的 `MutationObserver`，内容变化时调用 `controller.onContentChange()`；清理时断开 observer，并用 `requestAnimationFrame` 调度滚动。

- [ ] **步骤 5：运行控制器测试验证绿灯**

运行：`npm test -- --run tests/ChatAutoFollow.test.ts`

预期：2 项测试全部 PASS。

### 任务 2：接入聊天视口与现有按钮

**文件：**
- 修改：`web-react/src/components/assistant-ui/thread.tsx`
- 修改：`web-react/tests/ChatLayout.theme.test.ts`

- [ ] **步骤 1：编写失败的组件接线测试**

```ts
expect(threadSource).toContain("useChatAutoFollow");
expect(threadSource).toContain("ref={autoFollow.viewportRef}");
expect(threadSource).toContain("onScroll={autoFollow.onScroll}");
expect(threadSource).toContain("onSubmitCapture={autoFollow.resume}");
expect(threadSource).toContain("<ThreadScrollToBottom onResume={autoFollow.resume}");
```

- [ ] **步骤 2：运行布局测试验证红灯**

运行：`npm test -- --run tests/ChatLayout.theme.test.ts`

预期：FAIL，因为 `Thread` 尚未接入自动追底 hook。

- [ ] **步骤 3：完成最小组件接线**

在 `Thread` 顶层调用：

```tsx
const autoFollow = useChatAutoFollow();
```

把 `viewportRef`、`onScroll`、`onSubmitCapture` 传给 `ThreadPrimitive.Viewport`。将 `ThreadScrollToBottom` 改为接收 `onResume: () => void`，并把它传给按钮的 `onClick`，让发送、用户自行回到底部和点击按钮都能恢复追底。

- [ ] **步骤 4：运行相关测试**

运行：`npm test -- --run tests/ChatAutoFollow.test.ts tests/ChatLayout.theme.test.ts`

预期：两个测试文件全部 PASS。

### 任务 3：完整验证

**文件：**
- 验证：`web-react/src/components/assistant-ui/use-chat-auto-follow.ts`
- 验证：`web-react/src/components/assistant-ui/thread.tsx`

- [ ] **步骤 1：运行完整前端测试**

运行：`npm test -- --run`

预期：全部测试通过，0 failed。

- [ ] **步骤 2：运行 TypeScript 与生产构建**

运行：`npm run build`

预期：退出码 0。

- [ ] **步骤 3：运行 lint**

运行：`npm run lint`

预期：0 errors；允许项目中现有的 Fast Refresh 警告。

- [ ] **步骤 4：检查实现边界**

确认未修改后端协议、未增加新按钮、阈值为 100px，并且用户离开底部后内容变化不会更改 `scrollTop`。

> 说明：当前目录不是 Git 仓库，因此省略计划模板中的 commit 步骤。
