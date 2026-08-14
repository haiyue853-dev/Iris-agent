import type { AppView } from '../../App';
import type { SkillInfo } from '../../types';
import { useSkills } from '../../hooks/useSkills';
import SkillCard from './SkillCard';

interface SkillsPageProps {
  onNavigate: (view: AppView) => void;
  onActivateChatSkill?: (skillId: string) => void;
}

const ENTRY_VIEWS = new Set<AppView>(['chat', 'aihot', 'uml', 'reports', 'radar', 'automation']);

function isEntryView(view: string): view is AppView {
  return ENTRY_VIEWS.has(view as AppView);
}

export default function SkillsPage({ onNavigate, onActivateChatSkill }: SkillsPageProps) {
  const { skills, loading, error, reload, toggleEnabled, togglingIds, processingIds } = useSkills();

  const handleOpen = (skill: SkillInfo) => {
    if (skill.enabled && skill.entry_view === 'chat') {
      onActivateChatSkill?.(skill.id);
      onNavigate('chat');
    } else if (skill.enabled && isEntryView(skill.entry_view)) {
      onNavigate(skill.entry_view);
    }
  };

  return (
    <div className="skills-page">
      <div className="skills-page-head">
        <h1 className="skills-page-title">Skills 中心</h1>
        <p className="skills-page-desc">管理内置技能：启用后可通过“打开”进入对应工作台</p>
      </div>

      {error && (
        <div className="skills-error" role="alert">
          <span>{error}</span>
          <button
            type="button"
            className="skills-error-retry"
            onClick={() => void reload()}
            aria-label="重试加载 Skills"
          >
            重试
          </button>
        </div>
      )}

      {loading ? (
        <div className="skills-loading" role="status" aria-live="polite" aria-label="正在加载 Skills">
          正在加载技能…
        </div>
      ) : (
        <div className="skills-grid">
          {skills.map((skill) => (
            <SkillCard
              key={skill.id}
              skill={skill}
              toggling={togglingIds.has(skill.id)}
              processing={processingIds.has(skill.id)}
              onToggle={(id, enabled) => void toggleEnabled(id, enabled)}
              onOpen={handleOpen}
            />
          ))}
        </div>
      )}
    </div>
  );
}
