import { useCallback, useEffect, useRef } from "react";

export const AUTO_FOLLOW_THRESHOLD = 100;

type Viewport = Pick<HTMLElement, "clientHeight" | "scrollHeight" | "scrollTop">;
type Schedule = (callback: () => void) => unknown;
type Cancel = (handle: unknown) => void;

export function createChatAutoFollowController(
  getViewport: () => Viewport | null,
  schedule: Schedule,
  cancel: Cancel = () => undefined,
) {
  let following = true;
  let lastScrollTop: number | null = null;
  let framePending = false;
  let frameHandle: unknown;

  const scrollToBottom = () => {
    if (framePending) return;

    framePending = true;
    const handle = schedule(() => {
      framePending = false;
      frameHandle = undefined;
      if (!following) return;

      const viewport = getViewport();
      if (viewport) viewport.scrollTop = viewport.scrollHeight;
    });
    if (framePending) frameHandle = handle;
  };

  return {
    onScroll() {
      const viewport = getViewport();
      if (!viewport) return;

      const distanceFromBottom =
        viewport.scrollHeight - viewport.clientHeight - viewport.scrollTop;
      if (distanceFromBottom <= AUTO_FOLLOW_THRESHOLD) {
        following = true;
      } else if (
        lastScrollTop === null ||
        viewport.scrollTop < lastScrollTop
      ) {
        following = false;
      }
      lastScrollTop = viewport.scrollTop;
    },
    onContentChange() {
      if (following) scrollToBottom();
    },
    resume() {
      following = true;
      lastScrollTop = getViewport()?.scrollTop ?? null;
      scrollToBottom();
    },
    cancelPending() {
      if (framePending) cancel(frameHandle);
      framePending = false;
      frameHandle = undefined;
    },
  };
}

export function useChatAutoFollow() {
  const viewportRef = useRef<HTMLDivElement>(null);
  const controllerRef = useRef<ReturnType<
    typeof createChatAutoFollowController
  > | null>(null);

  if (!controllerRef.current) {
    controllerRef.current = createChatAutoFollowController(
      () => viewportRef.current,
      (callback) => requestAnimationFrame(callback),
      (handle) => cancelAnimationFrame(handle as number),
    );
  }

  const onScroll = useCallback(() => {
    controllerRef.current?.onScroll();
  }, []);

  const resume = useCallback(() => {
    controllerRef.current?.resume();
  }, []);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;

    const observer = new MutationObserver(() => {
      controllerRef.current?.onContentChange();
    });
    observer.observe(viewport, {
      childList: true,
      characterData: true,
      subtree: true,
    });

    return () => {
      observer.disconnect();
      controllerRef.current?.cancelPending();
    };
  }, []);

  return { viewportRef, onScroll, resume };
}
