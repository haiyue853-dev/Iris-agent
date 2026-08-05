import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import * as reportsApi from '../../api/reports';
import type { DailyReport } from '../../types';
import DailyReportPage from './DailyReportPage';

vi.mock('../../api/reports', async () => {
  const actual = await vi.importActual<typeof import('../../api/reports')>('../../api/reports');
  return {
    ...actual,
    listReports: vi.fn(),
    getReport: vi.fn(),
    generateReport: vi.fn(),
    saveReport: vi.fn(),
    reviseReport: vi.fn(),
    restoreReport: vi.fn(),
  };
});

const generated: DailyReport = {
  date: new Date().toLocaleDateString('en-CA'),
  source_notes: '完成日报页面',
  source_session_id: 'session_1',
  current_version: 1,
  current: {
    number: 1,
    kind: 'generated',
    instruction: null,
    created_at: 1,
    sections: {
      completed: ['完成日报页面'],
      in_progress: [],
      problems: [],
      next_day: ['接入预览'],
      assistance: [],
    },
  },
  versions: [{ number: 1, kind: 'generated', instruction: null, created_at: 1 }],
  created_at: 1,
  updated_at: 1,
};

describe('DailyReportPage', () => {
  beforeEach(() => {
    vi.mocked(reportsApi.listReports).mockResolvedValue([]);
    vi.mocked(reportsApi.generateReport).mockResolvedValue(generated);
  });

  it('generates a report and exposes copy, download, and revision controls', async () => {
    render(<DailyReportPage currentSessionId="session_1" />);
    await userEvent.type(screen.getByLabelText('今日工作记录'), '完成日报页面');
    await userEvent.click(screen.getByLabelText('导入当前对话'));
    await userEvent.click(screen.getByRole('button', { name: '生成汇报版日报' }));

    expect(await screen.findByLabelText('今日完成')).toHaveValue('完成日报页面');
    expect(screen.getByRole('button', { name: '复制' })).toBeEnabled();
    expect(screen.getByRole('link', { name: '下载 .md' })).toHaveAttribute('href');
    expect(screen.getByLabelText('AI 修改要求')).toBeInTheDocument();
  });
});
