import type { SkillInfo } from '../../types';

interface SkillCardProps {
  skill: SkillInfo;
  toggling: boolean;
  processing: boolean;
  onToggle: (id: string, enabled: boolean) => void;
  onOpen: (skill: SkillInfo) => void;
}

function SkillIcon({ name }: { name: string }) {
  const common = {
    width: 22,
    height: 22,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.5,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    'aria-hidden': true,
  };

  switch (name) {
    case 'calendar':
      return (
        <svg {...common}>
          <rect x="3" y="4" width="18" height="17" rx="2" />
          <path d="M8 2v4M16 2v4M3 9h18" />
        </svg>
      );
    case 'diagram':
      return (
        <svg {...common}>
          <rect x="3" y="3" width="7" height="7" rx="1.5" />
          <rect x="14" y="14" width="7" height="7" rx="1.5" />
          <path d="M6.5 10v4a3.5 3.5 0 0 0 3.5 3.5h4" />
          <path d="M17.5 3v4" />
        </svg>
      );
    case 'file-text':
      return (
        <svg {...common}>
          <path d="M6 3h9l3 3v15H6z" />
          <path d="M15 3v4h4M9 12h6M9 16h4" />
        </svg>
      );
    case 'radar':
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="8" />
          <circle cx="12" cy="12" r="4" />
          <path d="M12 4v4M12 16v4M4 12h4M16 12h4" />
        </svg>
      );
    default:
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="8" />
        </svg>
      );
  }
}

const CATEGORY_NAMES: Record<string, string> = {
  productivity: '效率',
  development: '开发',
  news: '资讯',
};

export default function SkillCard({ skill, toggling, processing, onToggle, onOpen }: SkillCardProps) {
  const disabled = !skill.enabled;
  const action = disabled ? '启用' : '停用';
  const actionInProgress = disabled ? '正在启用' : '正在停用';

  return (
    <article className={`skill-card ${disabled ? 'disabled' : ''}`} aria-labelledby={`skill-${skill.id}-name`}>
      <div className="skill-card-icon">
        <SkillIcon name={skill.icon} />
      </div>
      <div className="skill-card-body">
        <div className="skill-card-head">
          <h2 id={`skill-${skill.id}-name`} className="skill-card-name">
            {skill.name}
          </h2>
          <span className="skill-card-cat">{CATEGORY_NAMES[skill.category] ?? skill.category}</span>
        </div>
        <p className="skill-card-desc">{skill.description}</p>
        <div className="skill-card-foot">
          {disabled && <span className="skill-card-disabled-tag">已停用</span>}
          <div className="skill-card-actions">
            <button
              type="button"
              className="skill-card-open"
              onClick={() => onOpen(skill)}
              disabled={disabled || toggling}
              aria-label={`打开 ${skill.name}`}
            >
              打开
            </button>
            <button
              type="button"
              className="skill-card-action"
              onClick={() => onToggle(skill.id, disabled)}
              disabled={toggling}
              aria-label={`${processing ? actionInProgress : action} ${skill.name}`}
              aria-busy={processing || undefined}
            >
              {processing ? '处理中…' : action}
            </button>
          </div>
        </div>
      </div>
    </article>
  );
}
