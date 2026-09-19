import { render, screen, waitFor } from "@testing-library/react";
import { StrictMode } from "react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { synthesizeMessageSpeech, getTtsStatus } = vi.hoisted(() => ({
  synthesizeMessageSpeech: vi.fn(),
  getTtsStatus: vi.fn(),
}));

vi.mock("@/api/tts", () => ({ synthesizeMessageSpeech, getTtsStatus }));

import { VoiceReadButton, hasSpeakableText, playWithTimeout } from "./voice-read-button";


class FakeAudio extends EventTarget {
  paused = true;
  ended = false;
  currentTime = 0;
  play = vi.fn(() => playbackPromise ?? Promise.resolve().then(() => { this.paused = false; }));
  pause = vi.fn(() => { this.paused = true; });
}

let playbackPromise: Promise<void> | null = null;


describe("VoiceReadButton", () => {
  beforeEach(() => {
    synthesizeMessageSpeech.mockReset();
    getTtsStatus.mockReset();
    getTtsStatus.mockResolvedValue({ status: "ready", detail: "", emotion: "enabled" });
    playbackPromise = null;
    vi.stubGlobal("Audio", FakeAudio);
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: vi.fn(() => "blob:tomori") });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
  });

  it("generates on first click and supports pause and resume", async () => {
    let finish!: (blob: Blob) => void;
    synthesizeMessageSpeech.mockReturnValue(new Promise<Blob>((resolve) => { finish = resolve; }));
    const user = userEvent.setup();
    render(<VoiceReadButton sessionId="session_1" messageId="message_1" />);

    await user.click(screen.getByRole("button", { name: "语音朗读" }));
    expect(screen.getByRole("button", { name: "正在生成语音" })).toBeDisabled();

    finish(new Blob(["wav"], { type: "audio/wav" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "正在朗读" })).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "正在朗读" }));
    expect(screen.getByRole("button", { name: "继续朗读" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "继续朗读" }));
    expect(screen.getByRole("button", { name: "正在朗读" })).toBeInTheDocument();
    expect(synthesizeMessageSpeech).toHaveBeenCalledOnce();
  });

  it("times out when playback never starts", async () => {
    vi.useFakeTimers();
    try {
      playbackPromise = new Promise<void>(() => {});
      const pending = playWithTimeout(new FakeAudio() as unknown as HTMLAudioElement, 10);
      const assertion = expect(pending).rejects.toThrow("浏览器未开始播放");
      await vi.advanceTimersByTimeAsync(10);
      await assertion;
    } finally {
      vi.useRealTimers();
    }
  });

  it("leaves loading before a pending playback promise settles", async () => {
    playbackPromise = new Promise<void>(() => {});
    synthesizeMessageSpeech.mockResolvedValue(new Blob(["wav"], { type: "audio/wav" }));
    const user = userEvent.setup();
    render(<VoiceReadButton sessionId="session_1" messageId="message_1" />);

    void user.click(screen.getByRole("button", { name: "语音朗读" }));

    await waitFor(() => expect(screen.getByRole("button", { name: "继续朗读" })).toBeInTheDocument());
  });

  it("updates playback state under StrictMode", async () => {
    synthesizeMessageSpeech.mockResolvedValue(new Blob(["wav"], { type: "audio/wav" }));
    const user = userEvent.setup();
    render(
      <StrictMode>
        <VoiceReadButton sessionId="session_1" messageId="message_1" />
      </StrictMode>,
    );

    await user.click(screen.getByRole("button", { name: "语音朗读" }));

    await waitFor(() => expect(screen.getByRole("button", { name: "正在朗读" })).toBeInTheDocument());
  });

  it("shows when the voice model is still warming up", async () => {
    getTtsStatus.mockResolvedValue({ status: "starting", detail: "", emotion: "enabled" });
    synthesizeMessageSpeech.mockReturnValue(new Promise<Blob>(() => {}));
    const user = userEvent.setup();
    render(<VoiceReadButton sessionId="session_1" messageId="message_1" />);

    await user.click(screen.getByRole("button", { name: "语音朗读" }));

    await waitFor(() => expect(
      screen.getByRole("button", { name: "正在启动语音模型" }),
    ).toBeDisabled());
  });
});

describe("hasSpeakableText", () => {
  it("rejects markdown that becomes empty after speech cleanup", () => {
    expect(hasSpeakableText("```ts\nconst value = 1;\n```" )).toBe(false);
    expect(hasSpeakableText("<span></span>" )).toBe(false);
    expect(hasSpeakableText("**你好**" )).toBe(true);
  });
});
