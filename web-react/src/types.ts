export type Message = { role: 'user' | 'assistant'; content: string };
export type Session = { id: string; name: string; created_at: number; updated_at: number };

export type AgentEvent =
  | { type: 'text_delta'; data: { content: string } }
  | { type: 'tool_started'; data: { call_id: string; name: string; arguments: Record<string, unknown> } }
  | { type: 'tool_finished'; data: { call_id: string; name: string; ok: boolean; result?: unknown; error_message?: string } }
  | { type: 'message_completed'; data: { content: string } }
  | { type: 'error'; data: { code: string; message: string } };
