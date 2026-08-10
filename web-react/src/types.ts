export type Message = { role: 'user' | 'assistant'; content: string };
export type Session = { id: string; name: string; created_at: number; updated_at: number };

// ---------- AI HOT 每日资讯日报 ----------
export type AihotDailyItem = {
  no: number;
  title: string;
  summary: string;
  source: string;
  url_original: string;
  url_aihot: string;
  section: string;
};

export type AihotDailySection = {
  label: string;
  count: number;
  items: AihotDailyItem[];
};

export type AihotDailyReport = {
  date: string;
  date_human: string;
  generated_at: string;
  total: number;
  is_fallback: boolean;
  fallback_from: string;
  daily_url: string;
  sections: AihotDailySection[];
};

// ---------- 世界时政热点 ----------
export type WorldNewsItem = {
  title: string;
  url: string;
  time: string; // YYYY-MM-DD，可能为空
  source: string;
  summary: string; // 约 200 字正文摘要，可能为空
};

// ---------- 计算机行业新闻 ----------
export type TechNewsItem = WorldNewsItem;

// ---------- AI 配置设置 ----------
export type SettingsState = {
  model: string;
  base_url: string;
  api_key_set: boolean;
  api_key_masked: string;
};

// ---------- UML 流程图生成 ----------
export type UmlAnalyzeResult = {
  mermaid: string;
  raw: string;
};

export type UmlDiagramType =
  | 'flowchart'
  | 'activity'
  | 'usecase'
  | 'sequenceDiagram'
  | 'classDiagram'
  | 'erDiagram';

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
  revision: number;
  current: ReportVersion;
  versions: ReportVersionSummary[];
  created_at: number;
  updated_at: number;
  attachments?: ReportAttachment[];
};

export type ReportAttachment = {
  id: string;
  original_name: string;
  media_type: string;
  size_bytes: number;
  preserve: boolean;
  status: 'temporary' | 'preserved';
  extraction_status?: string;
  extraction_message?: string | null;
  created_at: number;
};

export type ReportSuggestion = {
  id: string;
  reply: string;
  sections: ReportSections;
  attachment_ids: string[];
  applied: boolean;
};

export type ReportChatResponse = {
  reply: string;
  suggestion: ReportSuggestion;
};

export type ReportChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
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
  expected_revision: number | null;
  expected_version?: number | null;
};

export type AgentEvent =
  | { type: 'text_delta'; data: { content: string } }
  | { type: 'tool_started'; data: { call_id: string; name: string; arguments: Record<string, unknown> } }
  | { type: 'tool_finished'; data: { call_id: string; name: string; ok: boolean; result?: unknown; error_message?: string } }
  | { type: 'message_completed'; data: { content: string } }
  | { type: 'error'; data: { code: string; message: string } };

// ---------- Skills 中心 ----------
export type SkillInfo = {
  id: string;
  name: string;
  description: string;
  icon: string;
  category: string;
  entry_view: string;
  version: number;
  enabled: boolean;
};
