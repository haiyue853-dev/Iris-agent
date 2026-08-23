import { describe, expect, it, vi } from "vitest";
import { createEventQueue, createIrisAdapter, groupToolParts } from "../src/lib/irisRuntime";
import { streamChat } from "../src/api/chat";
import { cancelTask } from "../src/api/tasks";

vi.mock("../src/api/chat", () => ({
  streamChat: vi.fn(async () => undefined),
  streamToolApproval: vi.fn(async () => undefined),
}));

vi.mock("../src/api/tasks", () => ({
  cancelTask: vi.fn(async () => ({ status: "stopped" })),
}));

describe("Iris adapter thinking state", () => {
  it("emits a transient reasoning part before the first response event", async () => {
    const queue = createEventQueue();
    const adapter = createIrisAdapter({
      getSessionId: () => "session-1",
      ensureSession: async () => "session-1",
      enqueue: queue.push,
      queue,
      registerController: vi.fn(),
    });

    const run = adapter.run({
      messages: [{ role: "user", content: [{ type: "text", text: "你好" }] }],
      abortSignal: new AbortController().signal,
      context: {},
      config: {},
    } as never) as AsyncGenerator;

    const first = await run.next();
    expect(first.value).toEqual(
      expect.objectContaining({
        content: [expect.objectContaining({ type: "reasoning", text: "正在思考…" })],
        status: { type: "running" },
      }),
    );
    await run.return(undefined);
  });

  it("allows a browser paint between queued text deltas", async () => {
    let paint: FrameRequestCallback | undefined;
    const requestAnimationFrame = vi.fn((callback: FrameRequestCallback) => {
      paint = callback;
      return 1;
    });
    vi.stubGlobal("requestAnimationFrame", requestAnimationFrame);

    const queue = createEventQueue();
    queue.push({ type: "text_delta", data: { content: "第一段" } });
    queue.push({ type: "text_delta", data: { content: "第二段" } });
    queue.push({ type: "message_completed", data: { content: "第一段第二段" } });
    const adapter = createIrisAdapter({
      getSessionId: () => "session-1",
      ensureSession: async () => "session-1",
      enqueue: queue.push,
      queue,
      registerController: vi.fn(),
    });
    const run = adapter.run({
      messages: [{ role: "user", content: [{ type: "text", text: "你好" }] }],
      abortSignal: new AbortController().signal,
      context: {},
      config: {},
    } as never) as AsyncGenerator;

    await run.next();
    const firstDelta = await run.next();
    expect(firstDelta.value.content).toContainEqual({ type: "text", text: "第一段" });

    const nextDelta = run.next();
    await Promise.resolve();
    expect(requestAnimationFrame).toHaveBeenCalledOnce();
    expect(paint).toBeTypeOf("function");
    paint?.(0);
    expect((await nextDelta).value.content).toContainEqual({ type: "text", text: "第一段第二段" });
    await run.return(undefined);
    vi.unstubAllGlobals();
  });

  it("cancels the backend task and finishes as cancelled when aborted", async () => {
    let finishStream: (() => void) | undefined;
    vi.mocked(streamChat).mockImplementationOnce(async (_sessionId, _text, _signal, onEvent) => {
      onEvent({ type: "task_started", data: { task_id: "task-1" } });
      await new Promise<void>((resolve) => { finishStream = resolve; });
    });
    const queue = createEventQueue();
    const adapter = createIrisAdapter({
      getSessionId: () => "session-1",
      ensureSession: async () => "session-1",
      enqueue: queue.push,
      queue,
      registerController: vi.fn(),
    });
    const abortController = new AbortController();
    const run = adapter.run({
      messages: [{ role: "user", content: [{ type: "text", text: "停止" }] }],
      abortSignal: abortController.signal,
      context: {},
      config: {},
    } as never) as AsyncGenerator;

    await run.next();
    await run.next();
    abortController.abort();
    await vi.waitFor(() => expect(cancelTask).toHaveBeenCalledWith("task-1"));
    finishStream?.();
    const final = await run.next();

    expect(final.value.status).toEqual({ type: "incomplete", reason: "cancelled" });
  });

  it("marks only unfinished grouped tools as cancelled", () => {
    const grouped = groupToolParts([
      { type: "tool-call", toolCallId: "done", toolName: "read", args: {}, argsText: "{}", result: "ok" },
      { type: "tool-call", toolCallId: "running", toolName: "search", args: {}, argsText: "{}" },
    ], true);
    const result = grouped[0].result as { items: Array<{ callId: string; state: string }> };

    expect(result.items).toEqual([
      expect.objectContaining({ callId: "done", state: "completed" }),
      expect.objectContaining({ callId: "running", state: "cancelled" }),
    ]);
  });

  it("cancels once when task_started arrives after the local abort", async () => {
    vi.mocked(cancelTask).mockClear();
    let publishTask: (() => void) | undefined;
    vi.mocked(streamChat).mockImplementationOnce(async (_sessionId, _text, _signal, onEvent) => {
      await new Promise<void>((resolve) => { publishTask = resolve; });
      onEvent({ type: "task_started", data: { task_id: "task-late" } });
    });
    const queue = createEventQueue();
    const adapter = createIrisAdapter({
      getSessionId: () => "session-1",
      ensureSession: async () => "session-1",
      enqueue: queue.push,
      queue,
      registerController: vi.fn(),
    });
    const abortController = new AbortController();
    const run = adapter.run({
      messages: [{ role: "user", content: [{ type: "text", text: "停止" }] }],
      abortSignal: abortController.signal,
      context: {},
      config: {},
    } as never) as AsyncGenerator;

    await run.next();
    abortController.abort();
    const finalPending = run.next();
    publishTask?.();
    const final = await finalPending;

    expect(cancelTask).toHaveBeenCalledTimes(1);
    expect(cancelTask).toHaveBeenCalledWith("task-late");
    expect(final.value.status).toEqual({ type: "incomplete", reason: "cancelled" });
  });
});
