import { afterEach, describe, expect, it, vi } from "vitest";
import { getTtsStatus, synthesizeMessageSpeech } from "./tts";


describe("synthesizeMessageSpeech", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("posts to the message speech endpoint and returns the audio blob", async () => {
    const audio = new Blob(["wav"], { type: "audio/wav" });
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      blob: async () => audio,
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await synthesizeMessageSpeech("session 1", "message/1");

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/tts/sessions/session%201/messages/message%2F1",
      { method: "POST" },
    );
    expect(result.type).toBe("audio/wav");
  });

  it("surfaces the backend error message", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      detail: { code: "tts_unavailable", message: "缺少语音文件" },
    }), { status: 503, headers: { "Content-Type": "application/json" } })));

    await expect(synthesizeMessageSpeech("session", "message")).rejects.toThrow("缺少语音文件");
  });

  it("reads the model warmup status", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      status: "starting", detail: "", emotion: "enabled",
    }), { status: 200, headers: { "Content-Type": "application/json" } })));

    await expect(getTtsStatus()).resolves.toEqual({
      status: "starting", detail: "", emotion: "enabled",
    });
  });

  it("passes cancellation to the model status request", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      status: "ready", detail: "", emotion: "enabled",
    }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();

    await getTtsStatus(controller.signal);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/tts/status",
      { signal: controller.signal },
    );
  });
});
