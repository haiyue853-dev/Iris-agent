import { createElement } from "react";
import { act, render, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  AUTO_FOLLOW_THRESHOLD,
  createChatAutoFollowController,
  useChatAutoFollow,
} from "../src/components/assistant-ui/use-chat-auto-follow";

type Viewport = Pick<HTMLElement, "clientHeight" | "scrollHeight" | "scrollTop">;

function createViewport(values: Viewport): HTMLElement {
  return values as HTMLElement;
}

describe("chat auto-follow controller", () => {
  it("scrolls to the new bottom when content grows while near the bottom", () => {
    const viewport = createViewport({
      clientHeight: 500,
      scrollHeight: 1_000,
      scrollTop: 500 - AUTO_FOLLOW_THRESHOLD,
    });
    const schedule = vi.fn((callback: () => void) => callback());
    const controller = createChatAutoFollowController(() => viewport, schedule);

    controller.onScroll();
    viewport.scrollHeight = 1_250;
    controller.onContentChange();

    expect(viewport.scrollTop).toBe(1_250);
    expect(schedule).toHaveBeenCalledOnce();
  });

  it("pauses after scrolling away and resume follows the latest bottom", () => {
    const viewport = createViewport({
      clientHeight: 500,
      scrollHeight: 1_000,
      scrollTop: 500 - AUTO_FOLLOW_THRESHOLD - 1,
    });
    const schedule = vi.fn((callback: () => void) => callback());
    const controller = createChatAutoFollowController(() => viewport, schedule);

    controller.onScroll();
    viewport.scrollHeight = 1_400;
    controller.onContentChange();

    expect(viewport.scrollTop).toBe(399);
    expect(schedule).not.toHaveBeenCalled();

    controller.resume();

    expect(viewport.scrollTop).toBe(1_400);
    expect(schedule).toHaveBeenCalledOnce();
  });

  it("coalesces repeated content changes into one scheduled frame", () => {
    const viewport = createViewport({
      clientHeight: 500,
      scrollHeight: 1_000,
      scrollTop: 500,
    });
    const callbacks: Array<() => void> = [];
    const schedule = vi.fn((callback: () => void) => callbacks.push(callback));
    const controller = createChatAutoFollowController(() => viewport, schedule);

    controller.onContentChange();
    controller.onContentChange();

    expect(schedule).toHaveBeenCalledOnce();
    callbacks[0]();
    expect(viewport.scrollTop).toBe(1_000);
  });

  it("keeps following during downward intermediate scroll events after resume", () => {
    const viewport = createViewport({
      clientHeight: 500,
      scrollHeight: 1_500,
      scrollTop: 700,
    });
    const callbacks: Array<() => void> = [];
    const schedule = vi.fn((callback: () => void) => callbacks.push(callback));
    const controller = createChatAutoFollowController(() => viewport, schedule);

    controller.onScroll();
    viewport.scrollTop = 500;
    controller.onScroll();
    controller.resume();
    controller.cancelPending();

    viewport.scrollTop = 600;
    controller.onScroll();
    controller.onContentChange();

    expect(schedule).toHaveBeenCalledTimes(2);
  });

  it("pauses following when the user genuinely scrolls upward", () => {
    const viewport = createViewport({
      clientHeight: 500,
      scrollHeight: 1_000,
      scrollTop: 500,
    });
    const schedule = vi.fn();
    const controller = createChatAutoFollowController(() => viewport, schedule);

    controller.onScroll();
    viewport.scrollTop = 350;
    controller.onScroll();
    controller.onContentChange();

    expect(schedule).not.toHaveBeenCalled();
  });

  it("stays paused when scrolling downward without reaching the threshold", () => {
    const viewport = createViewport({
      clientHeight: 500,
      scrollHeight: 1_000,
      scrollTop: 500,
    });
    const schedule = vi.fn();
    const controller = createChatAutoFollowController(() => viewport, schedule);

    controller.onScroll();
    viewport.scrollTop = 300;
    controller.onScroll();
    viewport.scrollTop = 350;
    controller.onScroll();
    controller.onContentChange();

    expect(schedule).not.toHaveBeenCalled();
  });
});

describe("useChatAutoFollow", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("does not observe or throw while its viewport ref is empty", () => {
    const observe = vi.fn();
    vi.stubGlobal(
      "MutationObserver",
      vi.fn(() => ({ observe, disconnect: vi.fn() })),
    );

    const { result } = renderHook(() => useChatAutoFollow());

    expect(result.current.viewportRef.current).toBeNull();
    expect(observe).not.toHaveBeenCalled();
  });

  it("observes content mutations and disconnects on unmount", () => {
    const observe = vi.fn();
    const disconnect = vi.fn();
    class MockMutationObserver {
      observe = observe;
      disconnect = disconnect;
    }
    vi.stubGlobal("MutationObserver", MockMutationObserver);
    vi.stubGlobal("requestAnimationFrame", vi.fn(() => 1));
    let hook: ReturnType<typeof useChatAutoFollow> | undefined;

    function Probe() {
      hook = useChatAutoFollow();
      return createElement("div", { ref: hook.viewportRef });
    }

    const view = render(createElement(Probe));

    expect(observe).toHaveBeenCalledWith(hook?.viewportRef.current, {
      childList: true,
      characterData: true,
      subtree: true,
    });

    view.unmount();
    expect(disconnect).toHaveBeenCalledOnce();
  });

  it("cancels a pending animation frame on unmount", () => {
    let mutationCallback: MutationCallback | undefined;
    class MockMutationObserver {
      observe = vi.fn();
      disconnect = vi.fn();

      constructor(callback: MutationCallback) {
        mutationCallback = callback;
      }
    }
    vi.stubGlobal("MutationObserver", MockMutationObserver);
    vi.stubGlobal("requestAnimationFrame", vi.fn(() => 42));
    const cancelAnimationFrame = vi.fn();
    vi.stubGlobal("cancelAnimationFrame", cancelAnimationFrame);

    function Probe() {
      const hook = useChatAutoFollow();
      return createElement("div", { ref: hook.viewportRef });
    }

    const view = render(createElement(Probe));
    act(() => mutationCallback?.([], {} as MutationObserver));
    view.unmount();

    expect(cancelAnimationFrame).toHaveBeenCalledWith(42);
  });
});
