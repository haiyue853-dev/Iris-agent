import type { ToolCallMessagePartComponent } from "@assistant-ui/react";
import { ApprovalCard } from "@/components/tool-ui/approval-card";
import { Terminal } from "@/components/tool-ui/terminal";
import { useIrisChat } from "./iris-chat-context";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/ui/cn";
import { CheckIcon, ChevronDownIcon, ChevronUpIcon, LoaderCircleIcon, XCircleIcon } from "lucide-react";
import { useState } from "react";

import type { IrisApprovalResult, IrisSourcesGroupResult, IrisToolGroupResult } from "@/lib/irisRuntime";
import { ToolGroup } from "./tool-group";
import { SourcesGroup } from "./sources-group";

const TERMINAL_TOOLS = new Set([
  "terminal",
  "shell",
  "bash",
  "cmd",
  "command",
  "exec",
  "sh",
  "powershell",
]);

/** Renders the appropriate tool card for an assistant-ui tool-call part. */
export const ToolFallback: ToolCallMessagePartComponent = ({
  toolName,
  argsText,
  result,
  status,
}: DefaultProps) => {
  if (result && typeof result === "object" && (result as IrisToolGroupResult).__irisKind === "tool-group") {
    return <ToolGroup items={(result as IrisToolGroupResult).items} />;
  }
  if (result && typeof result === "object" && (result as IrisSourcesGroupResult).__irisKind === "sources-group") {
    return <SourcesGroup items={(result as IrisSourcesGroupResult).items} />;
  }

  return <ToolFallbackWithContext toolName={toolName} argsText={argsText} result={result} status={status} />;
};

const ToolFallbackWithContext: React.FC<DefaultProps> = ({ toolName, argsText, result, status }) => {
  const iris = useIrisChat();

  // 1) Pending / resolved approval rendered as an approval card inside the message.
  if (result && typeof result === "object" && (result as IrisApprovalResult).__irisKind === "approval") {
    const approval = result as IrisApprovalResult;
    const decided = approval.choice === "approved" || approval.choice === "denied";
    return (
      <ApprovalCard
        id={approval.call_id}
        title={approval.title}
        description={approval.description}
        metadata={approval.metadata}
        icon={approval.icon}
        choice={approval.choice}
        onConfirm={decided ? undefined : () => void iris.resolveApproval(approval.call_id, true)}
        onCancel={decided ? undefined : () => void iris.resolveApproval(approval.call_id, false)}
      />
    );
  }

  // 2) Terminal-like tool results.
  if (toolName && TERMINAL_TOOLS.has(toolName.toLowerCase()) && result && typeof result === "object") {
    const r = result as Record<string, unknown>;
    if ("stdout" in r || "stderr" in r || "command" in r) {
      return (
        <Terminal
          id={toolName}
          command={typeof r.command === "string" ? r.command : ""}
          stdout={typeof r.stdout === "string" ? r.stdout : undefined}
          stderr={typeof r.stderr === "string" ? r.stderr : undefined}
          exitCode={typeof r.exitCode === "number" ? r.exitCode : 0}
          durationMs={typeof r.durationMs === "number" ? r.durationMs : undefined}
          cwd={typeof r.cwd === "string" ? r.cwd : undefined}
        />
      );
    }
  }

  // 3) Default fallback (original styling).
  return (
    <DefaultToolFallback toolName={toolName} argsText={argsText} result={result} status={status} />
  );
};

type DefaultProps = {
  toolName?: string;
  argsText?: string;
  result?: unknown;
  status?: { type: string; reason?: string; error?: unknown };
};

const DefaultToolFallback: React.FC<DefaultProps> = ({ toolName, argsText, result, status }) => {
  const [isCollapsed, setIsCollapsed] = useState(true);

  const isCancelled = status?.type === "incomplete" && status.reason === "cancelled";
  const isRunning = status?.type === "running";
  const isFailed = status?.type === "incomplete" && !isCancelled;
  const statusLabel = isRunning
    ? "工具运行中"
    : isCancelled
      ? "工具已停止"
      : isFailed
        ? "工具执行失败"
        : "工具已完成";
  const cancelledReason =
    isCancelled && status?.error
      ? typeof status.error === "string"
        ? status.error
        : JSON.stringify(status.error)
      : null;

  return (
    <div
      className={cn(
        "aui-tool-fallback-root mb-4 flex w-full flex-col gap-3 rounded-lg border py-3",
        isCancelled && "border-muted-foreground/30 bg-muted/30",
      )}
    >
      <div className="aui-tool-fallback-header flex items-center gap-2 px-4">
        {isRunning ? (
          <LoaderCircleIcon className="aui-tool-fallback-icon size-4 animate-spin motion-reduce:animate-none" />
        ) : isCancelled || isFailed ? (
          <XCircleIcon className="aui-tool-fallback-icon size-4 text-muted-foreground" />
        ) : (
          <CheckIcon className="aui-tool-fallback-icon size-4" />
        )}
        <p
          className={cn(
            "aui-tool-fallback-title grow",
            (isCancelled || isFailed) && "text-muted-foreground",
          )}
        >
          {statusLabel}：<b>{toolName}</b>
        </p>
        <Button onClick={() => setIsCollapsed(!isCollapsed)}>
          {isCollapsed ? <ChevronUpIcon /> : <ChevronDownIcon />}
        </Button>
      </div>
      {!isCollapsed && (
        <div className="aui-tool-fallback-content flex flex-col gap-2 border-t pt-2">
          {cancelledReason && (
            <div className="aui-tool-fallback-cancelled-root px-4">
              <p className="aui-tool-fallback-cancelled-header font-semibold text-muted-foreground">
                取消原因：
              </p>
              <p className="aui-tool-fallback-cancelled-reason text-muted-foreground">
                {cancelledReason}
              </p>
            </div>
          )}
          <div
            className={cn(
              "aui-tool-fallback-args-root px-4",
              isCancelled && "opacity-60",
            )}
          >
            <pre className="aui-tool-fallback-args-value whitespace-pre-wrap">{argsText}</pre>
          </div>
          {!isCancelled && result !== undefined && (
            <div className="aui-tool-fallback-result-root border-t border-dashed px-4 pt-2">
              <p className="aui-tool-fallback-result-header font-semibold">结果：</p>
              <pre className="aui-tool-fallback-result-content whitespace-pre-wrap">
                {typeof result === "string" ? result : JSON.stringify(result, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
