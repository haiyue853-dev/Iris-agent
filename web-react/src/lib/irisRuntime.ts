import type {
  ChatModelAdapter,
  ChatModelRunOptions,
  ChatModelRunResult,
  ThreadAssistantMessagePart,
  ThreadMessageLike,
  ToolCallMessagePart,
} from "@assistant-ui/react";
import type { AgentEvent, Message } from "../types";
import { streamChat, streamToolApproval } from "../api/chat";
import { cancelTask } from "../api/tasks";

function waitForNextPaint(): Promise<void> {
  return new Promise((resolve) => {
    if (typeof requestAnimationFrame === "function") {
      requestAnimationFrame(() => resolve());
    } else {
      setTimeout(resolve, 16);
    }
  });
}

/**
 * Shared event queue bridging the NDJSON backend stream(s) into the
 * assistant-ui runtime generator. Both the original `/api/chat/stream`
 * connection and the approval continuation connection feed the same queue.
 */
export type IrisEventQueue = {
  push: (event: AgentEvent) => void;
  shift: () => AgentEvent | undefined;
  wait: (signal?: AbortSignal) => Promise<void>;
};

export function createEventQueue(): IrisEventQueue {
  const items: AgentEvent[] = [];
  let waiter: (() => void) | null = null;
  return {
    push(event) {
      items.push(event);
      const w = waiter;
      waiter = null;
      w?.();
    },
    shift() {
      return items.shift();
    },
    wait(signal?: AbortSignal) {
      if (items.length > 0) return Promise.resolve();
      return new Promise<void>((resolve, reject) => {
        waiter = resolve;
        if (signal) {
          if (signal.aborted) {
            waiter = null;
            reject(new DOMException("Aborted", "AbortError"));
            return;
          }
          signal.addEventListener(
            "abort",
            () => {
              waiter = null;
              reject(new DOMException("Aborted", "AbortError"));
            },
            { once: true },
          );
        }
      });
    },
  };
}

/** Encoded into a tool-call `result` so the renderer knows to show an approval card. */
export type IrisApprovalResult = {
  __irisKind: "approval";
  call_id: string;
  title: string;
  description?: string;
  metadata?: { key: string; value: string }[];
  icon?: string;
  choice?: "approved" | "denied";
  raw: unknown;
  realResult?: unknown;
  ok?: boolean;
};

export type IrisToolGroupItem = {
  callId: string;
  name: string;
  args: unknown;
  argsText: string;
  result?: unknown;
  state: "running" | "completed" | "failed" | "cancelled";
};

export type IrisToolGroupResult = {
  __irisKind: "tool-group";
  items: IrisToolGroupItem[];
};

export type IrisSourcesGroupResult = {
  __irisKind: "sources-group";
  items: Array<{ id: string; url: string; title?: string }>;
};

export function groupSourceParts(parts: ThreadAssistantMessagePart[]): ThreadAssistantMessagePart[] {
  const sources = parts.filter((part) => part.type === "source");
  const rest = parts.filter((part) => part.type !== "source");
  if (sources.length === 0) return rest;

  const result: IrisSourcesGroupResult = {
    __irisKind: "sources-group",
    items: sources.map((source) => ({ id: source.id, url: source.url, title: source.title })),
  };
  return [{
    type: "tool-call",
    toolCallId: "iris-sources-group",
    toolName: "iris_sources_group",
    args: {},
    argsText: "{}",
    result,
  } as unknown as ThreadAssistantMessagePart, ...rest];
}

function isApprovalResult(result: unknown): result is IrisApprovalResult {
  return Boolean(result && typeof result === "object" && (result as IrisApprovalResult).__irisKind === "approval");
}

/** Combines ordinary tool calls into one compact message part; approvals stay independent. */
export function groupToolParts(parts: ToolCallMessagePart[], cancelled = false): ToolCallMessagePart[] {
  const approvals = parts.filter((part) => isApprovalResult(part.result));
  const ordinary = parts.filter((part) => !isApprovalResult(part.result));
  if (ordinary.length === 0) return approvals;

  const result: IrisToolGroupResult = {
    __irisKind: "tool-group",
    items: ordinary.map((part) => ({
      callId: part.toolCallId,
      name: part.toolName,
      args: part.args,
      argsText: part.argsText ?? JSON.stringify(part.args ?? {}, null, 2),
      result: part.result,
      state: part.isError ? "failed" : part.result === undefined ? (cancelled ? "cancelled" : "running") : "completed",
    })),
  };

  return [{
    type: "tool-call",
    toolCallId: "iris-tool-group",
    toolName: "iris_tool_group",
    args: {},
    argsText: "{}",
    result,
  }, ...approvals];
}

export type IrisAdapterController = {
  resolveApproval: (callId: string, approved: boolean) => Promise<void>;
};

export type IrisAdapterDeps = {
  getSessionId: () => string;
  ensureSession: (text: string) => Promise<string>;
  enqueue: (event: AgentEvent) => void;
  queue: IrisEventQueue;
  registerController: (controller: IrisAdapterController) => void;
  onSessionCreated?: (sessionId: string) => void;
  onEvent?: (event: AgentEvent) => void;
};

function extractText(messages: readonly { role: string; content: unknown }[]): string {
  const last = messages[messages.length - 1];
  if (!last) return "";
  const content = last.content;
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .filter((p): p is { type: string; text?: string } => typeof p === "object" && p !== null && "type" in p)
      .map((p) => (p.type === "text" ? (p.text ?? "") : ""))
      .join("");
  }
  return "";
}

function describeArgs(args: Record<string, unknown>): string {
  return Object.entries(args)
    .slice(0, 6)
    .map(([k, v]) => `${k}: ${typeof v === "string" ? v : JSON.stringify(v)}`)
    .join("\n");
}

function metadataFromArgs(args: Record<string, unknown>): { key: string; value: string }[] {
  return Object.entries(args)
    .slice(0, 6)
    .map(([k, v]) => ({ key: k, value: typeof v === "string" ? v : JSON.stringify(v) }));
}

function guessIcon(name: string): string | undefined {
  const n = name.toLowerCase();
  if (n.includes("file") || n.includes("write")) return "FileText";
  if (n.includes("shell") || n.includes("term") || n.includes("exec") || n.includes("command")) return "Terminal";
  if (n.includes("browser") || n.includes("web") || n.includes("fetch") || n.includes("http")) return "Globe";
  if (n.includes("search")) return "Search";
  if (n.includes("mail") || n.includes("send")) return "Mail";
  return "ShieldCheck";
}

/**
 * Builds a custom ChatModelAdapter that streams from the iris-agent NDJSON
 * backend and translates AgentEvents into assistant-ui message parts:
 *   text_delta            -> text part
 *   tool_started          -> tool-call part
 *   tool_approval_requested -> marks the tool-call result as an approval card
 *   tool_finished         -> fills the tool-call result / approval receipt
 *   message_completed     -> finalizes text
 */
export function createIrisAdapter(deps: IrisAdapterDeps): ChatModelAdapter {
  return {
    async *run({ messages, abortSignal }: ChatModelRunOptions): AsyncGenerator<ChatModelRunResult, void> {
      const text = extractText(messages as unknown as { role: string; content: unknown }[]);
      if (!text.trim()) return;

      const sessionId = await deps.ensureSession(text);

      const toolParts = new Map<string, ToolCallMessagePart>();
      let textAccum = "";
      let errored = false;
      let hasResponseEvent = false;
      let taskId: string | undefined;
      let cancelRequested = false;
      let cancelPromise: Promise<void> | undefined;
      let cancelled = false;
      const transportAbort = new AbortController();

      const requestCancellation = () => {
        cancelRequested = true;
        if (!taskId || cancelPromise) return cancelPromise;
        cancelPromise = cancelTask(taskId)
          .then(() => undefined)
          .catch(() => undefined)
          .finally(() => transportAbort.abort());
        return cancelPromise;
      };
      const onAbort = () => { void requestCancellation(); };
      abortSignal.addEventListener("abort", onAbort, { once: true });
      const enqueueEvent = (event: AgentEvent) => {
        if (event.type === "task_started") {
          taskId = event.data.task_id;
          if (cancelRequested) void requestCancellation();
        }
        deps.onEvent?.(event);
        deps.enqueue(event);
      };

      const buildContent = (cancelPendingTools = false): ThreadAssistantMessagePart[] => {
        const parts: ThreadAssistantMessagePart[] = [];
        if (!hasResponseEvent) parts.push({ type: "reasoning", text: "正在思考…" });
        if (textAccum) parts.push({ type: "text", text: textAccum });
        for (const p of groupToolParts([...toolParts.values()], cancelPendingTools)) {
          parts.push(p as unknown as ThreadAssistantMessagePart);
        }
        return parts;
      };

      const applyEvent = (event: AgentEvent) => {
        if (event.type !== "task_started" && event.type !== "paused") {
          hasResponseEvent = true;
        }
        switch (event.type) {
          case "task_started":
            taskId = event.data.task_id;
            if (cancelRequested) void requestCancellation();
            break;
          case "text_delta":
            textAccum += event.data.content;
            break;
          case "tool_started":
            toolParts.set(event.data.call_id, {
              type: "tool-call",
              toolCallId: event.data.call_id,
              toolName: event.data.name,
              args: event.data.arguments as unknown as ToolCallMessagePart["args"],
              argsText: JSON.stringify(event.data.arguments, null, 2),
            });
            break;
          case "tool_approval_requested": {
            const payload: IrisApprovalResult = {
              __irisKind: "approval",
              call_id: event.data.call_id,
              title: event.data.name,
              description: describeArgs(event.data.arguments as Record<string, unknown>),
              metadata: metadataFromArgs(event.data.arguments as Record<string, unknown>),
              icon: guessIcon(event.data.name),
              raw: event.data,
            };
            const existing = toolParts.get(event.data.call_id);
            if (existing) {
              toolParts.set(event.data.call_id, { ...existing, result: payload });
            } else {
              toolParts.set(event.data.call_id, {
                type: "tool-call",
                toolCallId: event.data.call_id,
                toolName: event.data.name,
                args: event.data.arguments as unknown as ToolCallMessagePart["args"],
                argsText: JSON.stringify(event.data.arguments, null, 2),
                result: payload,
              });
            }
            break;
          }
          case "tool_finished": {
            const existing = toolParts.get(event.data.call_id);
            if (existing) {
              const res = existing.result as IrisApprovalResult | undefined;
              const newResult = res && res.__irisKind === "approval"
                ? { ...res, realResult: event.data.result, ok: event.data.ok }
                : (event.data.result as ToolCallMessagePart["result"]);
              toolParts.set(event.data.call_id, {
                ...existing,
                result: newResult,
                isError: !event.data.ok,
              });
            }
            break;
          }
          case "message_completed":
            if (event.data.content && event.data.content.trim()) textAccum = event.data.content;
            break;
          case "error":
            errored = true;
            break;
          default:
            break;
        }
      };

      // Expose the approval resolver so the in-message approval card can
      // continue the backend stream after the user decides.
      deps.registerController({
        resolveApproval: async (callId: string, approved: boolean) => {
          await streamToolApproval(sessionId, callId, approved, abortSignal, deps.enqueue);
        },
      });

      // Original stream: yields up to `tool_approval_requested`, then ends.
      const streamPromise = streamChat(sessionId, text, transportAbort.signal, enqueueEvent).catch((err) => {
        if ((err as Error)?.name !== "AbortError") {
          deps.enqueue({ type: "error", data: { code: "stream_error", message: String(err) } });
        }
      });

      let finished = false;
      try {
        yield { content: buildContent(), status: { type: "running" } };
        while (!finished) {
          const ev = deps.queue.shift();
          if (!ev) {
            await deps.queue.wait(abortSignal);
            continue;
          }
          applyEvent(ev);
          if (ev.type === "message_completed" || ev.type === "error") finished = true;
          yield { content: buildContent(), status: { type: "running" } };
          if (ev.type === "text_delta" && !finished) await waitForNextPaint();
        }
      } catch (err) {
        if ((err as Error)?.name === "AbortError") {
          cancelled = true;
        } else {
          errored = true;
          yield {
            content: buildContent(),
            status: { type: "incomplete", reason: "error", error: String(err) },
          };
          return;
        }
      } finally {
        await streamPromise;
        if (cancelPromise) await cancelPromise;
        abortSignal.removeEventListener("abort", onAbort);
      }

      deps.onSessionCreated?.(sessionId);
      if (cancelled || cancelRequested) {
        yield {
          content: buildContent(true),
          status: { type: "incomplete", reason: "cancelled" },
        };
        return;
      }
      yield {
        content: buildContent(),
        status: errored
          ? { type: "incomplete", reason: "error" }
          : { type: "complete", reason: "stop" },
      };
    },
  };
}

/** Maps the persisted chat history into assistant-ui seed messages. */
export function toThreadMessages(history: Message[]): ThreadMessageLike[] {
  return history
    .filter((m) => m.role === "user" || m.role === "assistant")
    .map((m, i) => {
      const content: ThreadAssistantMessagePart[] = [];
      if (m.role === "assistant" && m.reasoning) {
        content.push({ type: "reasoning", text: m.reasoning });
      }
      if (m.role === "assistant") {
        for (const source of m.sources ?? []) {
          content.push({
            type: "source",
            sourceType: "url",
            id: source.id,
            url: source.url,
            title: source.title,
          });
        }
      }
      content.push({ type: "text", text: m.content });
      return {
        role: m.role,
        content: m.role === "assistant" ? groupSourceParts(content) : content,
        id: `${m.role}-${i}`,
      };
    }) as ThreadMessageLike[];
}
