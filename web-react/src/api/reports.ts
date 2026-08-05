import type {
  DailyReport,
  GenerateReportInput,
  ReportSections,
  ReportSummary,
  ReportVersion,
} from '../types';

const API_BASE = 'http://localhost:8000';

export class ReportApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(
    code: string,
    message: string,
    status: number,
  ) {
    super(message);
    this.name = 'ReportApiError';
    this.code = code;
    this.status = status;
  }
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ReportApiError(
      body.detail?.code || 'report_request_failed',
      body.detail?.message || `请求失败 (${response.status})`,
      response.status,
    );
  }
  return response.json() as Promise<T>;
}

const jsonRequest = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

export async function listReports(): Promise<ReportSummary[]> {
  const result = await requestJson<{ reports: ReportSummary[] }>('/api/reports');
  return result.reports;
}

export function getReport(reportDate: string): Promise<DailyReport> {
  return requestJson(`/api/reports/${encodeURIComponent(reportDate)}`);
}

export function getReportVersion(reportDate: string, version: number): Promise<ReportVersion> {
  return requestJson(`/api/reports/${encodeURIComponent(reportDate)}/versions/${version}`);
}

export function generateReport(input: GenerateReportInput): Promise<DailyReport> {
  return requestJson('/api/reports/generate', jsonRequest('POST', input));
}

export function saveReport(
  reportDate: string,
  sections: ReportSections,
  expectedVersion: number,
): Promise<DailyReport> {
  return requestJson(
    `/api/reports/${encodeURIComponent(reportDate)}`,
    jsonRequest('PUT', { sections, expected_version: expectedVersion }),
  );
}

export function reviseReport(
  reportDate: string,
  instruction: string,
  expectedVersion: number,
): Promise<DailyReport> {
  return requestJson(
    `/api/reports/${encodeURIComponent(reportDate)}/revise`,
    jsonRequest('POST', { instruction, expected_version: expectedVersion }),
  );
}

export function restoreReport(
  reportDate: string,
  version: number,
  expectedVersion: number,
): Promise<DailyReport> {
  return requestJson(
    `/api/reports/${encodeURIComponent(reportDate)}/versions/${version}/restore`,
    jsonRequest('POST', { expected_version: expectedVersion }),
  );
}

export function downloadReportUrl(reportDate: string, version?: number): string {
  const query = version === undefined ? '' : `?version=${version}`;
  return `${API_BASE}/api/reports/${encodeURIComponent(reportDate)}/download${query}`;
}
