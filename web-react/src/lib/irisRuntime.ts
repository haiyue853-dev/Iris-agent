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
import type { Toolset } from "./capability-mode";
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

export type IrisKnowledgeDraftResult = {
  __irisKind: "knowledge-draft";
  title: string;
  content: string;
  category: string;
  source_url?: string | null;
};

export type IrisSourcesGroupResult = {
  __irisKind: "sources-group";
  items: Array<{ id: string; url: string; title?: string }>;
};

export type IrisKnowledgeCitationsResult = {
  __irisKind: "knowledge-citations";
  items: Array<{ index: number; document_id: string; chunk_id: string; title: string; content: string; location?: string | null; score: number; keyword_score?: number; vector_score?: number; reranker_score?: number | null; collection_id?: string | null; collection_name?: string | null }>;
};

export type IrisFollowUpSuggestionsResult = {
  __irisKind: "follow-up-suggestions";
  items: string[];
};

export type IrisRagPipelineStage = {
  stage: "planning" | "retrieval" | "rerank" | "generation";
  status: "running" | "completed" | "failed";
  detail: { mode?: string; citations?: number; routes?: string[] };
};

export type IrisRagPipelineResult = {
  __irisKind: "rag-pipeline";
  stages: IrisRagPipelineStage[];
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
export function groupToolParts(parts: ToolCallMessagePart[], cancelled = false, previousResult?: IrisToolGroupResult): ToolCallMessagePart[] {
  const approvals = parts.filter((part) => isApprovalResult(part.result));
  const ordinary = parts.filter((part) => !isApprovalResult(part.result));
  if (ordinary.length === 0) return approvals;

  const items = ordinary.map((part) => ({
      callId: part.toolCallId,
      name: part.toolName,
      args: part.args,
      argsText: part.argsText ?? JSON.stringify(part.args ?? {}, null, 2),
      result: part.result,
      state: part.isError ? "failed" : part.result === undefined ? (cancelled ? "cancelled" : "running") : "completed",
    }));
  const result = previousResult ?? { __irisKind: "tool-group" as const, items };
  result.items = items;

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
  getKnowledgeCollectionId?: () => string;
  getKnowledgeQueryMode?: () => string;
  getUseKnowledge?: () => boolean;
  getResponseMode?: () => "fast" | "thinking";
  getToolsets?: () => Toolset[];
  getSkillId?: () => string | undefined;
  onSkillUsed?: () => void;
  onDelegationQueued?: (delegationId: string) => void;
  ensureSession: (text: string) => Promise<string>;
  enqueue: (event: AgentEvent) => void;
  queue: IrisEventQueue;
  registerController: (controller: IrisAdapterController) => void;
  onSessionCreated?: (sessionId: string) => void;
  onEvent?: (event: AgentEvent) => void;
  getModelProfileId?: () => string | null;
  onRunningChange?: (running: boolean) => void;
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

function regenerationMessageId(messages: readonly { id?: string; role: string }[], runConfig: unknown): string | undefined {
  if (!(runConfig as { custom?: { irisRegenerate?: boolean } } | undefined)?.custom?.irisRegenerate) return undefined;
  return [...messages].reverse().find((message) => message.role === "user")?.id;
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
    async *run({ messages, abortSignal, runConfig }: ChatModelRunOptions): AsyncGenerator<ChatModelRunResult, void> {
      const text = extractText(messages as unknown as { role: string; content: unknown }[]);
      if (!text.trim()) return;
      const regenerateFromMessageId = regenerationMessageId(messages, runConfig);

      const sessionId = await deps.ensureSession(text);
      deps.onRunningChange?.(true);
      const toolsets = deps.getToolsets?.();
      const skillId = deps.getSkillId?.();

      const toolParts = new Map<string, ToolCallMessagePart>();
      let renderedToolGroup: IrisToolGroupResult | undefined;
      let knowledgeCitations: IrisKnowledgeCitationsResult["items"] = [];
      let followUpSuggestions: string[] = [];
      let ragStages: IrisRagPipelineStage[] = [];
      let textAccum = "";
      let errored = false;
      let errorMessage = "";
      let awaitingFirstResponse = true;
      let modelMetrics: { first_token_ms: number | null; duration_ms: number } | undefined;
      let taskId: string | undefined;
      let cancelRequested = false;
      let cancelPromise: Promise<void> | undefined;
      let cancelled = false;
      const transportAbort = new AbortController();

      const requestCancellation = () => {
        cancelRequested = true;
        if (renderedToolGroup) groupToolParts([...toolParts.values()], true, renderedToolGroup);
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

      const buildContent = (cancelPendingTools = false, terminalNotice = ""): ThreadAssistantMessagePart[] => {
        const parts: ThreadAssistantMessagePart[] = [];
        if (ragStages.length) {
          parts.push({ type: "tool-call", toolCallId: "iris-rag-pipeline", toolName: "iris_rag_pipeline", args: {}, argsText: "{}", result: { __irisKind: "rag-pipeline", stages: ragStages } } as unknown as ThreadAssistantMessagePart);
        }
        // Put tool state first. A failed call is actionable context and must
        // not be pushed below a long assistant reply.
        const groupedTools = groupToolParts([...toolParts.values()], cancelPendingTools, renderedToolGroup);
        const toolGroup = groupedTools.find((part) => part.toolName === "iris_tool_group");
        if (toolGroup?.result && typeof toolGroup.result === "object") renderedToolGroup = toolGroup.result as IrisToolGroupResult;
        for (const p of groupedTools) {
          parts.push(p as unknown as ThreadAssistantMessagePart);
        }
        if (textAccum) parts.push({ type: "text", text: textAccum });
        if (!textAccum && terminalNotice) parts.push({ type: "text", text: terminalNotice });
        if (knowledgeCitations.length) {
          parts.push({ type: "tool-call", toolCallId: "iris-knowledge-citations", toolName: "iris_knowledge_citations", args: {}, argsText: "{}", result: { __irisKind: "knowledge-citations", items: knowledgeCitations } } as unknown as ThreadAssistantMessagePart);
        }
        if (followUpSuggestions.length) {
          parts.push({ type: "tool-call", toolCallId: "iris-follow-up-suggestions", toolName: "iris_follow_up_suggestions", args: {}, argsText: "{}", result: { __irisKind: "follow-up-suggestions", items: followUpSuggestions } } as unknown as ThreadAssistantMessagePart);
        }
        if (parts.length === 0 && awaitingFirstResponse) parts.push({ type: "reasoning", text: "正在思考…" });
        return parts;
      };

      const applyEvent = (event: AgentEvent) => {
        switch (event.type) {
          case "task_started":
            taskId = event.data.task_id;
            if (cancelRequested) void requestCancellation();
            break;
          case "pipeline_stage": {
            awaitingFirstResponse = false;
            const next = { ...event.data, detail: event.data.detail || {} } as IrisRagPipelineStage;
            const order = ["planning", "retrieval", "rerank", "generation"];
            ragStages = [...ragStages.filter((item) => item.stage !== next.stage), next]
              .sort((left, right) => order.indexOf(left.stage) - order.indexOf(right.stage));
            break;
          }
          case "text_delta":
            awaitingFirstResponse = false;
            textAccum += event.data.content;
            break;
          case "tool_started":
            awaitingFirstResponse = false;
            toolParts.set(event.data.call_id, {
              type: "tool-call",
              toolCallId: event.data.call_id,
              toolName: event.data.name,
              args: event.data.arguments as unknown as ToolCallMessagePart["args"],
              argsText: JSON.stringify(event.data.arguments, null, 2),
            });
            break;
          case "tool_approval_requested": {
            awaitingFirstResponse = false;
            const isCollaborationRequest = event.data.name === "request_subagent_collaboration";
            const payload: IrisApprovalResult = {
              __irisKind: "approval",
              call_id: event.data.call_id,
              title: isCollaborationRequest ? "此任务较复杂，是否启用子代理协作？" : event.data.name,
              description: isCollaborationRequest
                ? `将拆分并并行处理任务。${describeArgs(event.data.arguments as Record<string, unknown>)}`
                : describeArgs(event.data.arguments as Record<string, unknown>),
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
          case "tool_progress": {
            const existing = toolParts.get(event.data.call_id);
            if (!existing) break;
            const previous = existing.result as IrisApprovalResult | undefined;
            const live = previous && previous.__irisKind === "approval" && previous.realResult && typeof previous.realResult === "object" ? previous.realResult as Record<string, unknown> : {};
            const output = `${typeof live.stdout === "string" ? live.stdout : ""}${event.data.output || ""}`;
            const terminal = { ...live, command: typeof live.command === "string" ? live.command : (existing.args as Record<string, unknown>).command, stdout: output, output, cwd: typeof live.cwd === "string" ? live.cwd : (existing.args as Record<string, unknown>).cwd };
            toolParts.set(event.data.call_id, { ...existing, result: previous && previous.__irisKind === "approval" ? { ...previous, choice: "approved", realResult: terminal } : terminal });
            break;
          }
          case "tool_finished": {
            awaitingFirstResponse = false;
            const delegation = event.data.result as { delegation_id?: unknown; status?: unknown } | undefined;
            if (event.data.name === "delegate_task" && delegation?.status === "queued" && typeof delegation.delegation_id === "string") {
              deps.onDelegationQueued?.(delegation.delegation_id);
            }
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
            awaitingFirstResponse = false;
            knowledgeCitations = Array.isArray(event.data.citations) ? event.data.citations as IrisKnowledgeCitationsResult["items"] : [];
            followUpSuggestions = Array.isArray(event.data.follow_up_suggestions)
              ? event.data.follow_up_suggestions.filter((item): item is string => typeof item === "string" && item.trim().length > 0)
              : [];
            modelMetrics = event.data.metrics;
            ragStages = ragStages.map((item) => item.stage === "generation" ? { ...item, status: "completed" } : item);
            if (skillId) deps.onSkillUsed?.();
            break;
          case "error":
            awaitingFirstResponse = false;
            errored = true;
            errorMessage = event.data.message || "生成失败，请稍后重试。";
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
      const streamPromise = streamChat(sessionId, text, transportAbort.signal, enqueueEvent, [], deps.getKnowledgeCollectionId?.(), deps.getKnowledgeQueryMode?.() || "mix", deps.getUseKnowledge?.() || false, regenerateFromMessageId, deps.getResponseMode?.() || "fast", toolsets, skillId).catch((err) => {
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
          yield { content: buildContent(false, errored ? `生成失败：${errorMessage || "请稍后重试。"}` : ""), status: { type: "running" } };
          if (ev.type === "text_delta" && !finished) await waitForNextPaint();
        }
      } catch (err) {
        if ((err as Error)?.name === "AbortError") {
          cancelled = true;
        } else {
          errored = true;
          errorMessage = String(err);
          yield {
            content: buildContent(false, `生成失败：${errorMessage}`),
            status: { type: "incomplete", reason: "error", error: String(err) },
          };
          return;
        }
      } finally {
        await streamPromise;
        if (cancelPromise) await cancelPromise;
        abortSignal.removeEventListener("abort", onAbort);
        deps.onRunningChange?.(false);
      }

      deps.onSessionCreated?.(sessionId);
      if (cancelled || cancelRequested) {
        yield {
          content: buildContent(true, "已停止生成。"),
          status: { type: "incomplete", reason: "cancelled" },
        };
        return;
      }
      yield {
        content: buildContent(false, errored ? `生成失败：${errorMessage || "请稍后重试。"}` : ""),
        status: errored
          ? { type: "incomplete", reason: "error", error: errorMessage || "生成失败，请稍后重试。" }
          : { type: "complete", reason: "stop" },
        metadata: { custom: modelMetrics ? { modelMetrics } : {} },
      };
    },
  };
}

/** Maps the persisted chat history into assistant-ui seed messages. */
export function toThreadMessages(history: Message[]): ThreadMessageLike[] {
  const result: ThreadMessageLike[] = [];
  history.forEach((m, i) => {
      const role = (m as unknown as { role: string }).role;
      if (role === "tool") {
        let parsed: unknown;
        try { parsed = JSON.parse(m.content); } catch { parsed = m.content; }
        result.push({
          role: "assistant",
          content: [{
            type: "tool-call",
            toolCallId: m.tool_call_id || m.id || `tool-${i}`,
            toolName: m.name || "tool",
            args: {},
            argsText: "{}",
            result: parsed,
          } as unknown as ThreadAssistantMessagePart],
          id: m.id || `tool-${i}`,
        } as ThreadMessageLike);
        return;
      }
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
        if (m.citations?.length) {
          content.push({
            type: "tool-call",
            toolCallId: `iris-knowledge-citations-${m.id || i}`,
            toolName: "iris_knowledge_citations",
            args: {},
            argsText: "{}",
            result: { __irisKind: "knowledge-citations", items: m.citations },
          } as unknown as ThreadAssistantMessagePart);
        }
      }
      content.push({ type: "text", text: m.content });
      result.push({
        role: role as "user" | "assistant",
        content: m.role === "assistant" ? groupSourceParts(content) : content,
        id: m.id || `${m.role}-${i}`,
      } as ThreadMessageLike);
  });
  return result;
}
