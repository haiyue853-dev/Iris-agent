import {
  ComposerAddAttachment,
  ComposerAttachments,
  UserMessageAttachments,
} from "@/components/assistant-ui/attachment";
import { MarkdownText } from "@/components/assistant-ui/markdown-text";
import { Reasoning } from "@/components/assistant-ui/reasoning";
import { Source } from "@/components/assistant-ui/sources";
import { ToolFallback } from "@/components/assistant-ui/tool-fallback";
import { StreamingCursor } from "@/components/assistant-ui/streaming-cursor";
import { PromptPreviewControls } from "@/components/assistant-ui/prompt-preview-controls";
import { ActiveSkillChip, SkillPicker } from "@/components/assistant-ui/skill-picker";
import { CAPABILITY_MODE_KEY, CAPABILITY_MODE_LABELS, nextCapabilityMode, readCapabilityMode } from "@/lib/capability-mode";
import { Suggestions } from "@/components/assistant-ui/suggestions";
import { TooltipIconButton } from "@/components/assistant-ui/tooltip-icon-button";
import { useChatAutoFollow } from "@/components/assistant-ui/use-chat-auto-follow";
import { optimizePrompt } from "@/api/prompt";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/ui/cn";
import {
  ActionBarPrimitive,
  AssistantIf,
  BranchPickerPrimitive,
  ComposerPrimitive,
  ErrorPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  useAuiState,
  useComposer,
  useComposerRuntime,
} from "@assistant-ui/react";
import {
  ArrowDownIcon,
  ArrowUpIcon,
  CheckIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  CopyIcon,
  DownloadIcon,
  PencilIcon,
  RefreshCwIcon,
  LoaderCircleIcon,
  SquareIcon,
  WandSparklesIcon,
} from "lucide-react";
import { useEffect, useRef, useState, type FC } from "react";
import { useIrisChat } from "@/components/assistant-ui/iris-chat-context";

type PromptOptimizerNotice = { message: string; hasError: boolean } | null;

export const Thread: FC = () => {
  const autoFollow = useChatAutoFollow();
  const [optimizerNotice, setOptimizerNotice] = useState<PromptOptimizerNotice>(null);

  return (
    <ThreadPrimitive.Root
      className="aui-root aui-thread-root iris-conversation @container flex h-full flex-col bg-background"
      style={{
        ["--thread-max-width" as string]: "44rem",
      }}
    >
      <ThreadPrimitive.Viewport
        ref={autoFollow.viewportRef}
        onScroll={autoFollow.onScroll}
        onSubmitCapture={autoFollow.resume}
        turnAnchor="top"
        className="aui-thread-viewport iris-chat-viewport relative flex flex-1 flex-col overflow-x-auto overflow-y-scroll px-4 pt-4"
      >
        <AssistantIf condition={({ thread }) => thread.isEmpty}>
          <ThreadWelcome optimizerNotice={optimizerNotice} onOptimizerNoticeChange={setOptimizerNotice} />
        </AssistantIf>

        <ThreadPrimitive.Messages
          components={{
            UserMessage,
            EditComposer,
            AssistantMessage,
          }}
        />

        <AssistantIf condition={({ thread }) => !thread.isEmpty}>
          <ThreadPrimitive.ViewportFooter className="aui-thread-viewport-footer aui-thread-active-composer iris-composer-dock sticky bottom-0 mx-auto mt-auto flex w-full max-w-(--thread-max-width) flex-col gap-4 overflow-visible rounded-t-3xl bg-background pb-4 md:pb-6">
            <ThreadScrollToBottom onResume={autoFollow.resume} />
            <Composer optimizerNotice={optimizerNotice} onOptimizerNoticeChange={setOptimizerNotice} />
          </ThreadPrimitive.ViewportFooter>
        </AssistantIf>
      </ThreadPrimitive.Viewport>
    </ThreadPrimitive.Root>
  );
};

const ThreadScrollToBottom: FC<{ onResume: () => void }> = ({ onResume }) => {
  return (
    <ThreadPrimitive.ScrollToBottom asChild>
      <TooltipIconButton
        onClick={onResume}
        tooltip="滚动到底部"
        variant="outline"
        className="aui-thread-scroll-to-bottom absolute -top-12 z-10 self-center rounded-full p-4 disabled:invisible dark:bg-background dark:hover:bg-accent"
      >
        <ArrowDownIcon />
      </TooltipIconButton>
    </ThreadPrimitive.ScrollToBottom>
  );
};

const ThreadWelcome: FC<{ optimizerNotice: PromptOptimizerNotice; onOptimizerNoticeChange: (notice: PromptOptimizerNotice) => void }> = ({ optimizerNotice, onOptimizerNoticeChange }) => {
  return (
    <div className="aui-thread-welcome-root iris-chat-welcome mx-auto flex min-h-[70dvh] w-full max-w-(--thread-max-width) grow flex-col justify-center pb-[10dvh] sm:pb-[6dvh]">
      <div className="aui-thread-welcome-center flex w-full flex-col gap-6">
        <div className="aui-thread-welcome-message flex flex-col px-1 sm:px-4">
          <h1 className="aui-thread-welcome-message-inner fade-in slide-in-from-bottom-1 animate-in font-semibold text-2xl duration-200">
            有什么我可以帮你？
          </h1>
          <p className="aui-thread-welcome-message-inner fade-in slide-in-from-bottom-1 animate-in text-muted-foreground text-xl delay-75 duration-200">
            发送消息或添加附件，开始新的对话。
          </p>
        </div>
        <div className="aui-thread-empty-composer w-full">
          <Composer optimizerNotice={optimizerNotice} onOptimizerNoticeChange={onOptimizerNoticeChange} />
        </div>
      </div>
    </div>
  );
};

const Composer: FC<{ optimizerNotice: PromptOptimizerNotice; onOptimizerNoticeChange: (notice: PromptOptimizerNotice) => void }> = ({ optimizerNotice, onOptimizerNoticeChange }) => {
  const runtime = useComposerRuntime();
  useEffect(() => {
    const useFollowUp = (event: Event) => {
      const text = (event as CustomEvent<{ text?: unknown }>).detail?.text;
      if (typeof text === "string" && text.trim()) runtime.setText(text);
    };
    window.addEventListener("iris:use-follow-up", useFollowUp);
    return () => window.removeEventListener("iris:use-follow-up", useFollowUp);
  }, [runtime]);
  return (
    <ComposerPrimitive.Root className="aui-composer-root iris-prompt-input relative flex w-full flex-col">
      <ComposerSuggestions />
      <ComposerPrimitive.AttachmentDropzone className="aui-composer-attachment-dropzone iris-prompt-dropzone flex w-full flex-col rounded-2xl border border-input bg-background outline-none transition-shadow has-[textarea:focus-visible]:border-ring has-[textarea:focus-visible]:ring-2 has-[textarea:focus-visible]:ring-ring/20 data-[dragging=true]:border-ring data-[dragging=true]:border-dashed data-[dragging=true]:bg-accent/50">
        <div className="iris-prompt-header"><ComposerAttachments /><ActiveSkillChip /></div>
        <div className="iris-prompt-body"><ImeSafeComposerInput /></div>
        <div className="iris-prompt-footer">
          <div className="iris-prompt-tools"><ComposerAddAttachment /><SkillPicker /><PromptOptimizer notice={optimizerNotice} onNoticeChange={onOptimizerNoticeChange} /><ResponseModeSelect /><CapabilityModeSelect /><PromptPreviewControls /></div>
          <ComposerAction />
        </div>
      </ComposerPrimitive.AttachmentDropzone>
    </ComposerPrimitive.Root>
  );
};

const ResponseModeSelect: FC = () => {
  const [mode, setMode] = useState<"fast" | "thinking">(
    () => localStorage.getItem("iris_chat_response_mode") === "thinking" ? "thinking" : "fast",
  );
  return (
    <button
      type="button"
      className="iris-prompt-tool"
      aria-label={`回答模式：${mode === "fast" ? "快速" : "思考"}`}
      onClick={() => {
        const next = mode === "fast" ? "thinking" : "fast";
        setMode(next);
        localStorage.setItem("iris_chat_response_mode", next);
      }}
    >
      <span>{mode === "fast" ? "快速" : "思考"}</span>
    </button>
  );
};

const CapabilityModeSelect: FC = () => {
  const [mode, setMode] = useState(readCapabilityMode);
  const label = CAPABILITY_MODE_LABELS[mode];

  return (
    <button
      type="button"
      className="iris-prompt-tool"
      aria-label={`能力模式：${label}`}
      onClick={() => {
        const next = nextCapabilityMode(mode);
        setMode(next);
        localStorage.setItem(CAPABILITY_MODE_KEY, next);
      }}
    >
      <span>{label}</span>
    </button>
  );
};
const ImeSafeComposerInput: FC = () => {
  const runtime = useComposerRuntime();
  const runtimeText = useComposer((state) => state.text);
  const [draft, setDraft] = useState(runtimeText);
  const composingRef = useRef(false);

  useEffect(() => {
    if (!composingRef.current) setDraft(runtimeText);
  }, [runtimeText]);

  return (
    <ComposerPrimitive.Input
      value={draft}
      placeholder="输入消息…"
      className="aui-composer-input mb-1 max-h-32 min-h-14 w-full resize-none overflow-y-auto bg-transparent px-4 pt-2 pb-3 text-sm outline-none placeholder:text-muted-foreground focus-visible:ring-0"
      rows={1}
      autoFocus
      aria-label="消息输入框"
      onChange={(event) => {
        const next = event.currentTarget.value;
        setDraft(next);
        if (!composingRef.current) runtime.setText(next);
      }}
      onCompositionStart={() => {
        composingRef.current = true;
      }}
      onCompositionEnd={(event) => {
        composingRef.current = false;
        const next = event.currentTarget.value;
        setDraft(next);
        runtime.setText(next);
      }}
    />
  );
};

const ComposerSuggestions: FC = () => {
  const runtime = useComposerRuntime();
  return <Suggestions items={["分析这个项目", "帮我定位问题", "运行项目测试"]} onSelect={(value) => runtime.setText(value)} />;
};

const PromptOptimizer: FC<{ notice: PromptOptimizerNotice; onNoticeChange: (notice: PromptOptimizerNotice) => void }> = ({ notice, onNoticeChange }) => {
  const runtime = useComposerRuntime();
  const text = useComposer((state) => state.text);
  const isRunning = useAuiState(({ thread }) => thread.isRunning);
  const [optimizing, setOptimizing] = useState(false);

  const optimize = async () => {
    if (!text.trim() || optimizing || isRunning) return;
    setOptimizing(true);
    onNoticeChange({ message: "正在优化提示词…", hasError: false });
    try {
      const optimizedText = await optimizePrompt(text);
      runtime.setText(optimizedText);
      onNoticeChange({ message: optimizedText === text ? "已检查，原提示词已足够清晰" : "已优化提示词", hasError: false });
    } catch (error) {
      onNoticeChange({ message: error instanceof Error ? error.message : "提示词优化失败，请稍后重试", hasError: true });
    } finally {
      setOptimizing(false);
    }
  };

  return <span className="iris-prompt-optimizer">
    <TooltipIconButton
      type="button"
      tooltip="优化提示词"
      aria-label="优化提示词"
      disabled={!text.trim() || optimizing || isRunning}
      onClick={() => void optimize()}
      className="iris-prompt-icon-tool"
    >
      {optimizing ? <LoaderCircleIcon className="animate-spin" /> : <WandSparklesIcon />}
    </TooltipIconButton>
    {notice && <span className={cn("iris-prompt-optimizer-status", notice.hasError && "is-error")} role="status" aria-live="polite" aria-label="提示词优化状态">{notice.message}</span>}
  </span>;
};

const ComposerAction: FC = () => {
  return (
    <div className="aui-composer-action-wrapper iris-prompt-submit relative flex items-center">
      <AssistantIf condition={({ thread }) => !thread.isRunning}>
        <ComposerPrimitive.Send asChild>
          <TooltipIconButton
            tooltip="发送消息"
            side="bottom"
            type="submit"
            variant="default"
            size="icon"
            className="aui-composer-send size-8 rounded-full"
            aria-label="发送消息"
          >
            <ArrowUpIcon className="aui-composer-send-icon size-4" />
          </TooltipIconButton>
        </ComposerPrimitive.Send>
      </AssistantIf>

      <AssistantIf condition={({ thread }) => thread.isRunning}>
        <ComposerPrimitive.Cancel asChild>
          <Button
            type="button"
            variant="default"
            size="icon"
            className="aui-composer-cancel size-8 rounded-full"
            aria-label="停止生成"
          >
            <SquareIcon className="aui-composer-cancel-icon size-3 fill-current" />
          </Button>
        </ComposerPrimitive.Cancel>
      </AssistantIf>
    </div>
  );
};

const MessageError: FC = () => {
  return (
    <MessagePrimitive.Error>
      <ErrorPrimitive.Root className="aui-message-error-root mt-2 rounded-md border border-destructive bg-destructive/10 p-3 text-destructive text-sm dark:bg-destructive/5 dark:text-red-200">
        <ErrorPrimitive.Message className="aui-message-error-message line-clamp-2" />
      </ErrorPrimitive.Root>
    </MessagePrimitive.Error>
  );
};

const AssistantMessage: FC = () => {
  return (
    <MessagePrimitive.Root
      className="aui-assistant-message-root iris-assistant-message fade-in slide-in-from-bottom-1 relative mx-auto w-full max-w-(--thread-max-width) animate-in py-3 duration-150"
      data-role="assistant"
    >
      <div className="aui-assistant-message-content wrap-break-word px-2 text-foreground leading-relaxed">
        <MessagePrimitive.Parts
          components={{
            Text: MarkdownText,
            Reasoning: Reasoning,
            Source: Source,
            tools: { Fallback: ToolFallback },
          }}
        />
        <AssistantIf condition={({ message }) => message.status?.type === "running"}>
          <StreamingCursor running />
        </AssistantIf>
        <MessageError />
      </div>

      <LatencyBadge />

      <div className="aui-assistant-message-footer mt-1 ml-2 flex">
        <BranchPicker />
        <AssistantActionBar />
      </div>
    </MessagePrimitive.Root>
  );
};

const LatencyBadge: FC = () => {
  const metrics = useAuiState((state) => state.message.metadata.custom.modelMetrics as { first_token_ms: number | null; duration_ms: number; model?: string | null } | undefined);
  if (!metrics) return null;
  const first = metrics.first_token_ms === null ? "无流式首字" : `首字 ${(metrics.first_token_ms / 1000).toFixed(1)}s`;
  return <p className="iris-model-latency ml-2 text-xs text-muted-foreground">{metrics.model ? `${metrics.model} · ` : ""}{first} · 总耗时 {(metrics.duration_ms / 1000).toFixed(1)}s</p>;
};

const AssistantActionBar: FC = () => {
  return (
    <ActionBarPrimitive.Root
      hideWhenRunning
      autohide="not-last"
      autohideFloat="single-branch"
      className="aui-assistant-action-bar-root col-start-3 row-start-2 -ml-1 flex gap-1 text-muted-foreground data-floating:absolute data-floating:rounded-md data-floating:border data-floating:bg-background data-floating:p-1 data-floating:shadow-sm"
    >
      <ActionBarPrimitive.Copy asChild>
        <TooltipIconButton tooltip="复制">
          <AssistantIf condition={({ message }) => message.isCopied}>
            <CheckIcon />
          </AssistantIf>
          <AssistantIf condition={({ message }) => !message.isCopied}>
            <CopyIcon />
          </AssistantIf>
        </TooltipIconButton>
      </ActionBarPrimitive.Copy>
      <ActionBarPrimitive.ExportMarkdown asChild>
        <TooltipIconButton tooltip="导出 Markdown">
          <DownloadIcon />
        </TooltipIconButton>
      </ActionBarPrimitive.ExportMarkdown>
      <RegenerateButton />
    </ActionBarPrimitive.Root>
  );
};

const RegenerateButton: FC = () => {
  const userMessageId = useAuiState((state) => state.message.parentId);
  const { regenerate, isRegenerating } = useIrisChat();

  return (
    <TooltipIconButton
      tooltip="重新生成"
      disabled={!userMessageId || isRegenerating}
      onClick={() => {
        if (userMessageId) void regenerate(userMessageId);
      }}
    >
      <RefreshCwIcon className={isRegenerating ? "animate-spin" : undefined} />
    </TooltipIconButton>
  );
};

const UserMessage: FC = () => {
  return (
    <MessagePrimitive.Root
      className="aui-user-message-root iris-user-message fade-in slide-in-from-bottom-1 mx-auto grid w-full max-w-(--thread-max-width) animate-in auto-rows-auto grid-cols-1 content-start gap-y-2 px-2 py-3 duration-150 [&:where(>*)]:col-start-1"
      data-role="user"
    >
      <UserMessageAttachments />

      <div className="aui-user-message-content-wrapper relative col-start-1 min-w-0">
        <div className="aui-user-message-content iris-user-message-content wrap-break-word rounded-2xl bg-muted px-4 py-2.5 text-foreground">
          <MessagePrimitive.Parts />
        </div>
        <div className="aui-user-action-bar-wrapper absolute top-1/2 left-0 -translate-x-full -translate-y-1/2 pr-2">
          <UserActionBar />
        </div>
      </div>

      <BranchPicker className="aui-user-branch-picker col-span-full col-start-1 row-start-3 -mr-1 justify-end" />
    </MessagePrimitive.Root>
  );
};

const UserActionBar: FC = () => {
  return (
    <ActionBarPrimitive.Root
      hideWhenRunning
      autohide="not-last"
      className="aui-user-action-bar-root flex flex-col items-end"
    >
      <ActionBarPrimitive.Edit asChild>
        <TooltipIconButton tooltip="编辑消息" className="aui-user-action-edit p-4">
          <PencilIcon />
        </TooltipIconButton>
      </ActionBarPrimitive.Edit>
    </ActionBarPrimitive.Root>
  );
};

const EditComposer: FC = () => {
  const composer = useComposerRuntime();

  return (
    <MessagePrimitive.Root className="aui-edit-composer-wrapper mx-auto flex w-full max-w-(--thread-max-width) flex-col px-2 py-3">
      <ComposerPrimitive.Root className="aui-edit-composer-root ml-auto flex w-full max-w-[85%] flex-col rounded-2xl bg-muted">
        <ComposerPrimitive.Input
          className="aui-edit-composer-input min-h-14 w-full resize-none bg-transparent p-4 text-foreground text-sm outline-none"
          autoFocus
        />
        <div className="aui-edit-composer-footer mx-3 mb-3 flex items-center gap-2 self-end">
          <ComposerPrimitive.Cancel asChild>
            <Button variant="ghost" size="sm">
              取消
            </Button>
          </ComposerPrimitive.Cancel>
          <Button size="sm" type="button" onClick={() => composer.send({ startRun: true })}>
            更新并重发
          </Button>
        </div>
      </ComposerPrimitive.Root>
    </MessagePrimitive.Root>
  );
};

const BranchPicker: FC<BranchPickerPrimitive.Root.Props> = ({
  className,
  ...rest
}) => {
  const branchNumber = useAuiState((state) => state.message.branchNumber);

  return (
    <BranchPickerPrimitive.Root
      hideWhenSingleBranch
      className={cn(
        "aui-branch-picker-root mr-2 -ml-2 inline-flex items-center text-muted-foreground text-xs",
        className,
      )}
      {...rest}
    >
      <BranchPickerPrimitive.Previous asChild>
        <TooltipIconButton tooltip="Previous">
          <ChevronLeftIcon />
        </TooltipIconButton>
      </BranchPickerPrimitive.Previous>
      <span className="aui-branch-picker-state font-medium">
        {displayBranchPosition(branchNumber)} / <BranchPickerPrimitive.Count />
      </span>
      <BranchPickerPrimitive.Next asChild>
        <TooltipIconButton tooltip="Next">
          <ChevronRightIcon />
        </TooltipIconButton>
      </BranchPickerPrimitive.Next>
    </BranchPickerPrimitive.Root>
  );
};

export function displayBranchPosition(branchNumber: number): number {
  return branchNumber;
}
