import { render, screen, waitFor } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import type { TaskPlan } from '../../api/taskPlanning';
import TaskPlansPage from './TaskPlansPage';

const mocks = vi.hoisted(() => ({
  listTaskPlans: vi.fn(),
  listSubagents: vi.fn(),
}));

const plan: TaskPlan = {
  id: 'plan-1',
  session_id: 'session-1',
  goal: '整理面试知识',
  status: 'completed',
  updated_at: 1,
  steps: [{
    id: 'step-1',
    title: '收集问题',
    instruction: '收集 Python 面试题。',
    status: 'completed',
    approval_call_id: null,
    error: null,
    events: [],
    result: '已收集 10 道问题。',
  }],
};

vi.mock('../../api/taskPlanning', async () => {
  const actual = await vi.importActual<typeof import('../../api/taskPlanning')>('../../api/taskPlanning');
  return {
    ...actual,
    listTaskPlans: mocks.listTaskPlans,
    listSubagents: mocks.listSubagents,
  };
});

test('displays a completed task step result', async () => {
  mocks.listTaskPlans.mockResolvedValue({ items: [plan] });
  mocks.listSubagents.mockResolvedValue({ items: [] });
  render(<TaskPlansPage sessionId="session-1" />);

  await waitFor(() => expect(screen.getByText('已收集 10 道问题。')).toBeInTheDocument());
});
