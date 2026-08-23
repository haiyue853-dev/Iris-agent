import { useCallback, useMemo, useRef } from "react";
import { AssistantRuntimeProvider, useLocalRuntime } from "@assistant-ui/react";
import { Thread } from "@/components/assistant-ui/thread";
import { IrisChatContext, type IrisChatContextValue } from "@/components/assistant-ui/iris-chat-context";
import {
  createIrisAdapter,
  createEventQueue,
  toThreadMessages,
  type IrisAdapterController,
} from "@/lib/irisRuntime";
import type { AgentEvent, Message } from "@/types";
import { createSession } from "@/api/chat";

type AssistantChatProps = {
  sessionId: string;
  messages: Message[];
  onEvent?: (event: AgentEvent) => void;
  onSessionCreated?: (sessionId: string) => void;
};

export function AssistantChat({ sessionId, messages, onEvent, onSessionCreated }: AssistantChatProps) {
  // Tracks the active session across the lifecycle of this chat view.
  const sessionIdRef = useRef(sessionId);
  sessionIdRef.current = sessionId;

  const controllerRef = useRef<IrisAdapterController | null>(null);
  const queue = useMemo(() => createEventQueue(), []);

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
        ensureSession: async (text: string) => {
          if (sessionIdRef.current) return sessionIdRef.current;
          const session = await createSession(text.slice(0, 30) || "新会话");
          sessionIdRef.current = session.id;
          return session.id;
        },
        enqueue,
        queue,
        registerController: (controller) => {
          controllerRef.current = controller;
        },
        onSessionCreated,
      }),
    [queue, enqueue, onSessionCreated],
  );

  const initialMessages = useMemo(() => toThreadMessages(messages), [messages]);
  const options = useMemo(() => ({ initialMessages }), [initialMessages]);

  const runtime = useLocalRuntime(adapter, options);

  const ctxValue = useMemo<IrisChatContextValue>(
    () => ({
      resolveApproval: async (callId: string, approved: boolean) => {
        await controllerRef.current?.resolveApproval(callId, approved);
      },
    }),
    [],
  );

  return (
    <IrisChatContext.Provider value={ctxValue}>
      <AssistantRuntimeProvider runtime={runtime}>
        <Thread />
      </AssistantRuntimeProvider>
    </IrisChatContext.Provider>
  );
}
