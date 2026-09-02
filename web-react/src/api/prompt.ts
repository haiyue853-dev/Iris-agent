const API_BASE = "http://localhost:8000";

export async function optimizePrompt(prompt: string): Promise<string> {
  const response = await fetch(`${API_BASE}/api/prompt/optimize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as { detail?: { message?: unknown } };
    throw new Error(typeof body.detail?.message === "string" ? body.detail.message : "提示词优化失败");
  }
  const data = await response.json() as { prompt?: unknown };
  if (typeof data.prompt !== "string" || !data.prompt.trim()) throw new Error("提示词优化失败");
  return data.prompt;
}
