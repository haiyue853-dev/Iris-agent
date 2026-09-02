import { describe, expect, it, vi } from "vitest";

const { streamChat } = vi.hoisted(() => ({
  streamChat: vi.fn(async (...args: unknown[]) => {
    const onEvent = args[3] as (event: unknown) => void;
    onEvent({ type: "message_completed", data: { content: "已完成", citations: [] } });
  }),
}));

vi.mock("../api/chat", () => ({
  streamChat,
  streamToolApproval: vi.fn(),
}));
vi.mock("../api/tasks", () => ({ cancelTask: vi.fn() }));

import { createEventQueue, createIrisAdapter } from "./irisRuntime";

describe("Iris chat adapter", () => {
  it("does not treat assistant-ui's local parent ID as a backend regeneration ID", async () => {
    const queue = createEventQueue();
    const adapter = createIrisAdapter({
      getSessionId: () => "session-1",
      getToolsets: () => ["safe", "research"],
      ensureSession: async () => "session-1",
      enqueue: queue.push,
      queue,
      registerController: () => undefined,
    });
    const stream = adapter.run({
      messages: [{ id: "local-user-id", role: "user", content: [{ type: "text", text: "你好" }] }],
      abortSignal: new AbortController().signal,
      unstable_parentId: "local-user-id",
    } as never) as AsyncGenerator<unknown>;

    const first = await stream.next();

    expect((first.value as { content: unknown[] }).content).toEqual([{ type: "reasoning", text: "正在思考…" }]);

    const request = streamChat.mock.calls[0];
    expect(request).toEqual([
      "session-1", "你好", expect.any(AbortSignal), expect.any(Function), [], undefined, "mix", false, undefined, "fast", ["safe", "research"], undefined,
    ]);
    expect(request).toHaveLength(12);
  });

  it("sends the selected Skill ID without changing the visible user text", async () => {
    streamChat.mockClear();
    const queue = createEventQueue();
    const adapter = createIrisAdapter({
      getSessionId: () => "session-1",
      getSkillId: () => "web-research",
      ensureSession: async () => "session-1",
      enqueue: queue.push,
      queue,
      registerController: () => undefined,
    });
    const stream = adapter.run({
      messages: [{ role: "user", content: [{ type: "text", text: "分析这个页面" }] }],
      abortSignal: new AbortController().signal,
    } as never) as AsyncGenerator<unknown>;

    await stream.next();

    expect(streamChat.mock.calls[0]?.[1]).toBe("分析这个页面");
    expect(streamChat.mock.calls[0]?.[11]).toBe("web-research");
  });

  it("forwards the source user message ID when regenerating an answer", async () => {
    streamChat.mockClear();
    const queue = createEventQueue();
    const adapter = createIrisAdapter({
      getSessionId: () => "session-1",
      ensureSession: async () => "session-1",
      enqueue: queue.push,
      queue,
      registerController: () => undefined,
    });
    const stream = adapter.run({
      messages: [{ id: "backend-user-id", role: "user", content: [{ type: "text", text: "你好" }] }],
      runConfig: { custom: { irisRegenerate: true } },
      abortSignal: new AbortController().signal,
    } as never) as AsyncGenerator<unknown>;

    await stream.next();

    expect(streamChat.mock.calls[0]?.[8]).toBe("backend-user-id");
  });

  it("notifies the chat when a background delegation is queued", async () => {
    streamChat.mockImplementationOnce(async (...args: unknown[]) => {
      const onEvent = args[3] as (event: unknown) => void;
      onEvent({ type: "tool_started", data: { call_id: "delegate-1", name: "delegate_task", arguments: {} } });
      onEvent({ type: "tool_finished", data: { call_id: "delegate-1", name: "delegate_task", ok: true, result: { delegation_id: "delegation-1", status: "queued" } } });
      onEvent({ type: "message_completed", data: { content: "已开始执行", citations: [] } });
    });
    const onDelegationQueued = vi.fn();
    const queue = createEventQueue();
    const adapter = createIrisAdapter({
      getSessionId: () => "session-1",
      ensureSession: async () => "session-1",
      enqueue: queue.push,
      queue,
      registerController: () => undefined,
      onDelegationQueued,
    });
    const stream = adapter.run({
      messages: [{ role: "user", content: [{ type: "text", text: "请后台整理" }] }],
      abortSignal: new AbortController().signal,
    } as never) as AsyncGenerator<unknown>;

    for (let index = 0; index < 4; index += 1) await stream.next();

    expect(onDelegationQueued).toHaveBeenCalledWith("delegation-1");
  });

  it("renders a stream error as an assistant message", async () => {
    streamChat.mockImplementationOnce(async (...args: unknown[]) => {
      const onEvent = args[3] as (event: unknown) => void;
      onEvent({ type: "error", data: { code: "tool_round_limit", message: "工具调用次数超过限制" } });
    });
    const queue = createEventQueue();
    const adapter = createIrisAdapter({
      getSessionId: () => "session-1",
      ensureSession: async () => "session-1",
      enqueue: queue.push,
      queue,
      registerController: () => undefined,
    });
    const stream = adapter.run({
      messages: [{ role: "user", content: [{ type: "text", text: "抓取网页" }] }],
      abortSignal: new AbortController().signal,
    } as never) as AsyncGenerator<{ content: Array<{ type: string; text?: string }>; status: { type: string } }>;

    await stream.next();
    const failure = await stream.next();

    expect(failure.value.content).toEqual([{ type: "text", text: "生成失败：工具调用次数超过限制" }]);
  });

  it("uses a clear question for collaboration approval", async () => {
    streamChat.mockImplementationOnce(async (...args: unknown[]) => {
      const onEvent = args[3] as (event: unknown) => void;
      onEvent({ type: "tool_started", data: { call_id: "ask-1", name: "request_subagent_collaboration", arguments: { reason: "任务包含多个独立步骤" } } });
      onEvent({ type: "tool_approval_requested", data: { call_id: "ask-1", name: "request_subagent_collaboration", arguments: { reason: "任务包含多个独立步骤" } } });
    });
    const queue = createEventQueue();
    const adapter = createIrisAdapter({
      getSessionId: () => "session-1",
      ensureSession: async () => "session-1",
      enqueue: queue.push,
      queue,
      registerController: () => undefined,
    });
    const stream = adapter.run({
      messages: [{ role: "user", content: [{ type: "text", text: "复杂任务" }] }],
      abortSignal: new AbortController().signal,
    } as never) as AsyncGenerator<{ content: Array<{ result?: { title?: string } }> }>;

    await stream.next();
    await stream.next();
    const approval = await stream.next();

    expect(approval.value.content[0].result?.title).toBe("此任务较复杂，是否启用子代理协作？");
  });
});
