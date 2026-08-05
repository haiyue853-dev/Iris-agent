import { afterEach, describe, expect, it, vi } from 'vitest';

import { ReportApiError, generateReport, listReports } from './reports';

const report = {
  date: '2026-08-05',
  source_notes: '记录',
  source_session_id: null,
  current_version: 1,
  current: {
    number: 1,
    kind: 'generated' as const,
    instruction: null,
    created_at: 1,
    sections: {
      completed: ['完成日报'],
      in_progress: [],
      problems: [],
      next_day: [],
      assistance: [],
    },
  },
  versions: [{ number: 1, kind: 'generated' as const, instruction: null, created_at: 1 }],
  created_at: 1,
  updated_at: 1,
};

describe('reports API', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('generates a report using the stable request contract', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(report), { status: 201, headers: { 'Content-Type': 'application/json' } }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const result = await generateReport({
      date: '2026-08-05',
      notes: '记录',
      include_chat: false,
      session_id: null,
      expected_version: null,
    });

    expect(result.current.sections.completed).toEqual(['完成日报']);
    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/api/reports/generate',
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('lists report summaries', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ reports: [{ date: '2026-08-05', summary: '完成日报', current_version: 1, updated_at: 1 }] }), { status: 200 }),
    ));

    await expect(listReports()).resolves.toHaveLength(1);
  });

  it('throws the backend stable error code', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: { code: 'report_version_conflict', message: '请刷新' } }), { status: 409 }),
    ));

    await expect(listReports()).rejects.toEqual(
      expect.objectContaining<Partial<ReportApiError>>({ code: 'report_version_conflict', message: '请刷新' }),
    );
  });
});
