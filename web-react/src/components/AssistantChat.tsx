import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AssistantRuntimeProvider, useLocalRuntime } from "@assistant-ui/react";
import { Thread } from "@/components/assistant-ui/thread";
import {
  IrisChatContext,
  type IrisChatContextValue,
} from "@/components/assistant-ui/iris-chat-context";
import {
  createIrisAdapter,
  createEventQueue,
  toThreadMessages,
  type IrisAdapterController,
} from "@/lib/irisRuntime";
import type { AgentEvent, Message } from "@/types";
import { createSession, setSessionModelProfile, streamChat } from "@/api/chat";
import { getDelegation } from "@/api/delegations";
import { fetchSettingsProfiles } from "@/api/settings";
import { fetchSkills } from "@/api/skills";
import { readCapabilityMode, readOnlineSearchEnabled, toolsetsForMode, withOnlineSearch } from "@/lib/capability-mode";
import type { SkillInfo } from "@/types";

type AssistantChatProps = {
  sessionId: string;
  messages: Message[];
  onEvent?: (event: AgentEvent) => void;
  onSessionCreated?: (sessionId: string) => void;
  onSessionRefreshed?: (sessionId: string) => Promise<Message[] | null>;
  knowledgeCollectionId?: string;
  knowledgeQueryMode?: "precise" | "global" | "mix";
  useKnowledge?: boolean;
  initialSkill?: SkillInfo | null;
  onSkillUsed?: () => void;
  sessionModelProfileId?: string | null;
  onModelProfileChanged?: () => void;
};

export function AssistantChat({
  sessionId,
  messages,
  onEvent,
  onSessionCreated,
  onSessionRefreshed,
  knowledgeCollectionId,
  knowledgeQueryMode = "mix",
  useKnowledge = false,
  initialSkill,
  onSkillUsed,
  sessionModelProfileId,
  onModelProfileChanged,
}: AssistantChatProps) {
  // Tracks the active session across the lifecycle of this chat view.
  const sessionIdRef = useRef(sessionId);
  sessionIdRef.current = sessionId;

  const controllerRef = useRef<IrisAdapterController | null>(null);
  const queue = useMemo(() => createEventQueue(), []);
  const [modelProfiles, setModelProfiles] = useState<Array<{ id: string; name: string; model: string }>>([]);
  const [activeModelProfileId, setActiveModelProfileId] = useState<string | null>(null);
  const [selectedModelProfileId, setSelectedModelProfileId] = useState<string | null>(null);
  const [modelSelectionLocked, setModelSelectionLocked] = useState(false);
  const [isRegenerating, setIsRegenerating] = useState(false);
  const [queuedDelegationIds, setQueuedDelegationIds] = useState<string[]>([]);
  const [activeSkill, setActiveSkill] = useState<SkillInfo | null>(initialSkill ?? null);
  const [skillMenuOpen, setSkillMenuOpen] = useState(false);
  const [availableSkills, setAvailableSkills] = useState<SkillInfo[] | null>(null);
  const [skillsLoading, setSkillsLoading] = useState(false);
  const [skillsError, setSkillsError] = useState("");
  const activeSkillRef = useRef<SkillInfo | null>(activeSkill);
  activeSkillRef.current = activeSkill;

  useEffect(() => { void fetchSettingsProfiles().then((state) => { setModelProfiles(state.profiles); setActiveModelProfileId(state.active_id); }).catch(() => setModelProfiles([])); }, []);
  useEffect(() => { setSelectedModelProfileId(sessionId ? (sessionModelProfileId ?? null) : null); }, [sessionId, sessionModelProfileId]);
  const handleSkillUsed = useCallback(() => {
    setActiveSkill(null);
    onSkillUsed?.();
  }, [onSkillUsed]);

  const selectSkill = useCallback((skill: SkillInfo | null) => {
    setActiveSkill(skill);
    setSkillMenuOpen(false);
  }, []);

  const closeSkillMenu = useCallback(() => {
    setSkillMenuOpen(false);
  }, []);

  const toggleSkillMenu = useCallback(async () => {
    const nextOpen = !skillMenuOpen;
    setSkillMenuOpen(nextOpen);
    if (!nextOpen || availableSkills || skillsLoading) return;
    setSkillsLoading(true);
    setSkillsError("");
    try {
      const items = await fetchSkills();
      setAvailableSkills(items.filter((skill) => skill.enabled && skill.entry_view === "chat"));
    } catch (reason) {
      setSkillsError(reason instanceof Error ? reason.message : "Skills 加载失败");
    } finally {
      setSkillsLoading(false);
    }
  }, [availableSkills, skillMenuOpen, skillsLoading]);

  const enqueue = useCallback(
    (event: AgentEvent) => {
      queue.push(event);
      onEvent?.(event);
    },
    [queue, onEvent],
  );

  const adapter = useMemo(
    () =>
      createIrisAdapter({
        getSessionId: () => sessionIdRef.current,
        getKnowledgeCollectionId: () => knowledgeCollectionId || "",
        getKnowledgeQueryMode: () => knowledgeQueryMode,
        getUseKnowledge: () => useKnowledge,
        getResponseMode: () =>
          localStorage.getItem("iris_chat_response_mode") === "thinking"
            ? "thinking"
            : "fast",
        getToolsets: () => activeSkillRef.current?.allowed_toolsets?.length
          ? withOnlineSearch(activeSkillRef.current.allowed_toolsets, readOnlineSearchEnabled())
          : toolsetsForMode(readCapabilityMode(), readOnlineSearchEnabled()),
        getSkillId: () => activeSkillRef.current?.id,
        onSkillUsed: handleSkillUsed,
        ensureSession: async (text: string) => {
          if (sessionIdRef.current) return sessionIdRef.current;
          const session = await createSession(text.slice(0, 30) || "新会话", selectedModelProfileId);
          sessionIdRef.current = session.id;
          return session.id;
        },
        enqueue,
        queue,
        registerController: (controller) => {
          controllerRef.current = controller;
        },
        onSessionCreated,
        onDelegationQueued: (delegationId) => {
          setQueuedDelegationIds((current) => current.includes(delegationId) ? current : [...current, delegationId]);
        },
        onRunningChange: setModelSelectionLocked,
      }),
    [
      queue,
      enqueue,
      onSessionCreated,
      knowledgeCollectionId,
      knowledgeQueryMode,
      useKnowledge,
      handleSkillUsed,
      selectedModelProfileId,
    ],
  );

  const initialMessages = useMemo(() => toThreadMessages(messages), [messages]);
  const options = useMemo(() => ({ initialMessages }), [initialMessages]);

  const runtime = useLocalRuntime(adapter, options);

  useEffect(() => {
    if (!queuedDelegationIds.length || !sessionIdRef.current) return;
    let disposed = false;
    const refreshCompletedDelegations = async () => {
      const records = await Promise.all(queuedDelegationIds.map(async (id) => ({ id, detail: await getDelegation(id) })));
      const completed = records.filter(({ detail }) => ["succeeded", "failed", "cancelled", "interrupted"].includes(detail.status));
      if (!completed.length || disposed) return;
      setQueuedDelegationIds((current) => current.filter((id) => !completed.some((item) => item.id === id)));
      const refreshedMessages = await onSessionRefreshed?.(sessionIdRef.current);
      if (!disposed && refreshedMessages) runtime.thread.reset(toThreadMessages(refreshedMessages));
    };
    void refreshCompletedDelegations();
    const timer = window.setInterval(() => { void refreshCompletedDelegations(); }, 2000);
    return () => { disposed = true; window.clearInterval(timer); };
  }, [onSessionRefreshed, queuedDelegationIds, runtime]);

  const regenerate = useCallback(async (userMessageId: string) => {
    const activeSessionId = sessionIdRef.current;
    const sourceMessage = messages.find((message) => message.id === userMessageId && message.role === "user");
    if (!activeSessionId || !sourceMessage || isRegenerating) return;

    setIsRegenerating(true);
    try {
      const toolsets = activeSkill?.allowed_toolsets?.length
        ? withOnlineSearch(activeSkill.allowed_toolsets, readOnlineSearchEnabled())
        : toolsetsForMode(readCapabilityMode(), readOnlineSearchEnabled());
      await streamChat(
        activeSessionId,
        sourceMessage.content,
        new AbortController().signal,
        () => undefined,
        sourceMessage.attachment_ids ?? [],
        knowledgeCollectionId || undefined,
        knowledgeQueryMode,
        useKnowledge,
        userMessageId,
        localStorage.getItem("iris_chat_response_mode") === "thinking" ? "thinking" : "fast",
        toolsets,
        activeSkill?.id,
      );
      const refreshedMessages = await onSessionRefreshed?.(activeSessionId);
      if (refreshedMessages) runtime.thread.reset(toThreadMessages(refreshedMessages));
    } finally {
      setIsRegenerating(false);
    }
  }, [activeSkill, isRegenerating, knowledgeCollectionId, knowledgeQueryMode, messages, onSessionRefreshed, runtime, useKnowledge]);

  const ctxValue = useMemo<IrisChatContextValue>(
    () => ({
      capabilityModeLocked: false,
      regenerate,
      isRegenerating,
      resolveApproval: async (callId: string, approved: boolean) => {
        await controllerRef.current?.resolveApproval(callId, approved);
      },
      modelProfiles,
      selectedModelProfileId,
      activeModelProfileId,
      modelSelectionLocked,
      knowledgeCollectionId,
      activeSkill,
      selectSkill,
      skillMenuOpen,
      availableSkills,
      skillsLoading,
      skillsError,
      toggleSkillMenu,
      closeSkillMenu,
      selectModelProfile: async (id: string | null) => {
        if (modelSelectionLocked) return;
        setSelectedModelProfileId(id);
        if (sessionIdRef.current) { await setSessionModelProfile(sessionIdRef.current, id); onModelProfileChanged?.(); }
      },
    }),
    [sessionId, modelProfiles, selectedModelProfileId, activeModelProfileId, modelSelectionLocked, knowledgeCollectionId, regenerate, isRegenerating, activeSkill, selectSkill, skillMenuOpen, availableSkills, skillsLoading, skillsError, toggleSkillMenu, closeSkillMenu],
  );

  return (
    <IrisChatContext.Provider value={ctxValue}>
      <AssistantRuntimeProvider runtime={runtime}>
        <Thread />
      </AssistantRuntimeProvider>
    </IrisChatContext.Provider>
  );
}
