const API_BASE = "http://localhost:8000";

export type TtsStatus = {
  status: "idle" | "starting" | "ready" | "failed";
  detail: string;
  emotion: "enabled" | "disabled";
};

export async function getTtsStatus(signal?: AbortSignal): Promise<TtsStatus> {
  const response = await fetch(
    `${API_BASE}/api/tts/status`,
    signal ? { signal } : undefined,
  );
  if (!response.ok) throw new Error("无法读取语音模型状态");
  return response.json() as Promise<TtsStatus>;
}

export async function synthesizeMessageSpeech(
  sessionId: string,
  messageId: string,
  signal?: AbortSignal,
): Promise<Blob> {
  const options: RequestInit = { method: "POST" };
  if (signal) options.signal = signal;
  const response = await fetch(
    `${API_BASE}/api/tts/sessions/${encodeURIComponent(sessionId)}/messages/${encodeURIComponent(messageId)}`,
    options,
  );
  if (!response.ok) {
    let message = `语音生成失败（HTTP ${response.status}）`;
    try {
      const payload = await response.json() as { detail?: { message?: string } };
      if (payload.detail?.message) message = payload.detail.message;
    } catch {
      // Keep the status-based fallback for non-JSON upstream failures.
    }
    throw new Error(message);
  }
  return response.blob();
}

export function streamMessageSpeechUrl(sessionId: string, messageId: string): string {
  return `${API_BASE}/api/tts/sessions/${encodeURIComponent(sessionId)}/messages/${encodeURIComponent(messageId)}/stream`;
}
