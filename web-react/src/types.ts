export type Message = { role: 'user' | 'assistant'; content: string };
export type Session = { id: string; name: string; created_at: number; updated_at: number };
export type AppView = 'chat' | 'reports';

export type ReportSections = {
  completed: string[];
  in_progress: string[];
  problems: string[];
  next_day: string[];
  assistance: string[];
};

export type ReportVersionKind = 'generated' | 'manual' | 'ai_revision' | 'restored';

export type ReportVersionSummary = {
  number: number;
  kind: ReportVersionKind;
  instruction: string | null;
  created_at: number;
};

export type ReportVersion = ReportVersionSummary & { sections: ReportSections };

export type DailyReport = {
  date: string;
  source_notes: string;
  source_session_id: string | null;
  current_version: number;
  current: ReportVersion;
  versions: ReportVersionSummary[];
  created_at: number;
  updated_at: number;
};

export type ReportSummary = {
  date: string;
  summary: string;
  current_version: number;
  updated_at: number;
};

export type GenerateReportInput = {
  date: string;
  notes: string;
  include_chat: boolean;
  session_id: string | null;
  expected_version: number | null;
};

export type AgentEvent =
  | { type: 'text_delta'; data: { content: string } }
  | { type: 'tool_started'; data: { call_id: string; name: string; arguments: Record<string, unknown> } }
  | { type: 'tool_finished'; data: { call_id: string; name: string; ok: boolean; result?: unknown; error_message?: string } }
  | { type: 'message_completed'; data: { content: string } }
  | { type: 'error'; data: { code: string; message: string } };
