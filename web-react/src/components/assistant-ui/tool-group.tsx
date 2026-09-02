import { useId, useState } from "react";
import { CheckIcon, ChevronDownIcon, LoaderCircleIcon, XCircleIcon } from "lucide-react";
import type { IrisToolGroupItem } from "@/lib/irisRuntime";
import { Terminal } from "@/components/tool-ui/terminal";
import { useIrisChat } from "./iris-chat-context";
import { KnowledgeDraftCard } from "./knowledge-draft-card";
import type { IrisKnowledgeDraftResult } from "@/lib/irisRuntime";

const TERMINAL_TOOLS = new Set(["terminal", "shell", "bash", "cmd", "command", "exec", "sh", "powershell", "run_command"]);

function isTerminalResult(item: IrisToolGroupItem): item is IrisToolGroupItem & { result: Record<string, unknown> } {
  return TERMINAL_TOOLS.has(item.name.toLowerCase()) && Boolean(item.result && typeof item.result === "object" && ("stdout" in item.result || "stderr" in item.result || "command" in item.result));
}

function progressLabel(items: IrisToolGroupItem[], running: number, failed: number, cancelled: number): string {
  const fetches = items.filter((item) => item.name === "fetch_page");
  if (fetches.some((item) => item.state === "running")) {
    const completed = fetches.filter((item) => item.state === "completed").length;
    return `正在读取网页 ${completed}/${fetches.length}`;
  }

  const runningSearch = items.find((item) => item.name === "web_search" && item.state === "running");
  if (runningSearch) {
    const args = runningSearch.args && typeof runningSearch.args === "object" ? runningSearch.args as Record<string, unknown> : {};
    const query = typeof args.query === "string" ? args.query.trim() : "";
    return query ? `正在搜索：${query}` : "正在搜索网页";
  }

  if (running) return `正在执行 ${items.length} 个工具`;
  if (cancelled) return `${cancelled} 个工具已停止`;
  if (failed) return `${failed} 个工具执行失败`;

  const searches = items.filter((item) => item.name === "web_search" && item.state === "completed");
  if (searches.length === 1 && Array.isArray(searches[0].result)) {
    return `找到 ${searches[0].result.length} 个结果`;
  }

  // Only web/fetch tools need the LLM to "think" after they finish. For
  // everything else, the existing "已执行 N 个工具" wording is more accurate
  // and keeps the existing tests stable.
  const needsAnalysis = items.some((item) => item.name === "fetch_page" || item.name === "web_search");
  if (items.length > 0 && items.every((item) => item.state === "completed") && needsAnalysis) {
    return `已读取 ${items.length} 个工具结果，正在分析…`;
  }
  return `已执行 ${items.length} 个工具`;
}

export function ToolGroup({ items }: { items: IrisToolGroupItem[] }) {
  const { knowledgeCollectionId } = useIrisChat();
  const [open, setOpen] = useState(false);
  const regionId = useId();
  const running = items.filter((item) => item.state === "running").length;
  const failed = items.filter((item) => item.state === "failed").length;
  const cancelled = items.filter((item) => item.state === "cancelled").length;
  const label = progressLabel(items, running, failed, cancelled);
  const drafts = items
    .map((item) => item.result)
    .filter((result): result is IrisKnowledgeDraftResult => Boolean(result && typeof result === "object" && (result as IrisKnowledgeDraftResult).__irisKind === "knowledge-draft"));

  return (
    <div className="iris-tool-group">
      <button
        type="button"
        className="iris-tool-group-toggle"
        aria-expanded={open}
        aria-controls={regionId}
        aria-label={label}
        onClick={() => setOpen((value) => !value)}
      >
        {running ? (
          <LoaderCircleIcon className="size-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
        ) : failed || cancelled ? (
          <XCircleIcon className="size-4" aria-hidden="true" />
        ) : (
          <CheckIcon className="size-4" aria-hidden="true" />
        )}
        <span>{label}</span>
        <ChevronDownIcon className={`ml-auto size-4 transition-transform ${open ? "rotate-180" : ""}`} aria-hidden="true" />
      </button>
      {drafts.map((draft, index) => <KnowledgeDraftCard key={`${draft.title}-${index}`} draft={draft} collectionId={knowledgeCollectionId} />)}
      {open && (
        <div id={regionId} className="iris-tool-group-content">
          {items.map((item) => (
            <details className="iris-tool-item" key={item.callId}>
              <summary>
                {item.state === "running" ? <LoaderCircleIcon className="size-3.5 animate-spin" /> : item.state === "failed" || item.state === "cancelled" ? <XCircleIcon className="size-3.5" /> : <CheckIcon className="size-3.5" />}
                <span>{item.name}{item.state === "cancelled" ? " · 已停止" : ""}</span>
              </summary>
              <div className="iris-tool-item-detail">
                <p>参数</p>
                <pre>{item.argsText}</pre>
                {isTerminalResult(item) ? (
                  <Terminal
                    className="iris-tool-terminal"
                    id={item.callId}
                    command={typeof item.result.command === "string" ? item.result.command : ""}
                    stdout={typeof item.result.stdout === "string" ? item.result.stdout : undefined}
                    stderr={typeof item.result.stderr === "string" ? item.result.stderr : undefined}
                    exitCode={typeof item.result.exitCode === "number" ? item.result.exitCode : 0}
                    durationMs={typeof item.result.durationMs === "number" ? item.result.durationMs : undefined}
                    cwd={typeof item.result.cwd === "string" ? item.result.cwd : undefined}
                  />
                ) : item.result !== undefined && (
                  <>
                    <p>结果</p>
                    <pre>{typeof item.result === "string" ? item.result : JSON.stringify(item.result, null, 2)}</pre>
                  </>
                )}
              </div>
            </details>
          ))}
        </div>
      )}
    </div>
  );
}
