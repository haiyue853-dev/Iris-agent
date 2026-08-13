import type { AgentEvent } from '../types';

type ReactStep = Extract<AgentEvent, { type: 'react_step' }>['data'];

const phaseLabel: Record<ReactStep['phase'], string> = {
  thought: '计划',
  action: '行动',
  observation: '观察',
  final: '完成',
};

function summary(step: ReactStep): string {
  if (step.phase === 'thought' || step.phase === 'final') return step.content ?? '';
  if (step.phase === 'action') return step.name ? `调用 ${step.name}` : '调用工具';
  if (step.ok) return step.name ? `${step.name} 已返回结果` : '工具已返回结果';
  return step.error_message ?? '工具执行失败';
}

export default function ReactTrace({ steps }: { steps: ReactStep[] }) {
  const visibleSteps = steps.filter((step) => step.phase !== 'final');
  if (!visibleSteps.length) return null;

  return <section className="react-trace" aria-label="智能体执行轨迹">
    <header><span>ReAct 执行中</span><small>{visibleSteps.length} 个步骤</small></header>
    <ol>
      {visibleSteps.map((step, index) => <li key={`${step.phase}-${step.call_id ?? index}`} className={`react-trace-${step.phase}`}>
        <strong>{phaseLabel[step.phase]}</strong>
        <span>{summary(step)}</span>
      </li>)}
    </ol>
  </section>;
}
