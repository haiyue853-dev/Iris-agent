import { useState } from 'react';
import type { AppView } from '../../App';
import type { SkillInfo } from '../../types';
import { useSkills } from '../../hooks/useSkills';
import ConfirmDialog from '../ConfirmDialog';
import SkillCard from './SkillCard';
import UserSkillEditor, { type UserSkillEditorValue } from './UserSkillEditor';
import type { UserSkillContent } from '../../api/skills';

interface SkillsPageProps {
  onNavigate: (view: AppView) => void;
  onActivateSkill?: (skill: UserSkillContent) => void;
}

const ENTRY_VIEWS = new Set<AppView>(['chat', 'aihot', 'uml', 'reports', 'radar', 'automation']);

function isEntryView(view: string): view is AppView {
  return ENTRY_VIEWS.has(view as AppView);
}

export default function SkillsPage({ onNavigate, onActivateSkill }: SkillsPageProps) {
  const {
    skills,
    loading,
    error,
    reload,
    toggleEnabled,
    saveUserSkill,
    loadUserSkillContent,
    removeUserSkill,
    togglingIds,
    processingIds,
  } = useSkills();
  const [editorValue, setEditorValue] = useState<UserSkillEditorValue | null>(null);
  const [deletingSkill, setDeletingSkill] = useState<SkillInfo | null>(null);

  const handleOpen = async (skill: SkillInfo) => {
    if (skill.source === 'user' && skill.entry_view === 'chat') {
      try {
        const content = await loadUserSkillContent(skill.id);
        onActivateSkill?.(content);
        onNavigate('chat');
      } catch {}
      return;
    }
    if (skill.enabled && isEntryView(skill.entry_view)) {
      onNavigate(skill.entry_view);
    }
  };

  const bundledSkills = skills.filter((skill) => skill.source !== 'user');
  const userSkills = skills.filter((skill) => skill.source === 'user');

  const handleEdit = async (skill: SkillInfo) => {
    try {
      const content = await loadUserSkillContent(skill.id);
      setEditorValue({ id: content.id, name: content.name, description: content.description, content: content.content, allowed_toolsets: content.allowed_toolsets ?? [] });
    } catch {}
  };

  const handleSave = async (draft: UserSkillEditorValue) => {
    await saveUserSkill(draft);
    setEditorValue(null);
  };

  const handleDelete = async () => {
    if (!deletingSkill) return;
    try {
      await removeUserSkill(deletingSkill.id);
      setDeletingSkill(null);
    } catch {}
  };

  return (
    <div className="skills-page">
      <div className="skills-page-head">
        <h1 className="skills-page-title">Skills 中心</h1>
        <p className="skills-page-desc">管理内置和自定义 Skill；自定义 Skill 可在聊天中直接使用。</p>
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
        <>
          <section className="skills-section" aria-labelledby="bundled-skills-title">
            <div className="skills-section-head">
              <div><span>BUILT IN</span><h2 id="bundled-skills-title">内置 Skills</h2></div>
            </div>
            <div className="skills-grid">
              {bundledSkills.map((skill) => (
                <SkillCard key={skill.id} skill={skill} toggling={togglingIds.has(skill.id)} processing={processingIds.has(skill.id)} onToggle={(id, enabled) => void toggleEnabled(id, enabled)} onOpen={(item) => void handleOpen(item)} />
              ))}
            </div>
          </section>
          <section className="skills-section" aria-labelledby="user-skills-title">
            <div className="skills-section-head">
              <div><span>MY SKILLS</span><h2 id="user-skills-title">我的 Skills</h2></div>
              <button type="button" onClick={() => setEditorValue({ name: '', description: '', content: '', allowed_toolsets: [] })}>新建 Skill</button>
            </div>
            {userSkills.length ? (
              <div className="skills-grid">
                {userSkills.map((skill) => (
                  <SkillCard key={skill.id} skill={skill} toggling={togglingIds.has(skill.id)} processing={processingIds.has(skill.id)} onToggle={(id, enabled) => void toggleEnabled(id, enabled)} onOpen={(item) => void handleOpen(item)} onEdit={(item) => void handleEdit(item)} onDelete={setDeletingSkill} />
                ))}
              </div>
            ) : !editorValue && <p className="skills-empty">还没有自定义 Skill，创建一个以复用你的提示词。</p>}
          </section>
        </>
      )}
      {editorValue && (
        <div className="user-skill-editor-overlay" onMouseDown={() => setEditorValue(null)}>
          <div className="user-skill-editor-dialog" role="dialog" aria-modal="true" aria-labelledby="user-skill-editor-title" onMouseDown={(event) => event.stopPropagation()}>
            <UserSkillEditor initialValue={editorValue} onSave={handleSave} onCancel={() => setEditorValue(null)} />
          </div>
        </div>
      )}
      {deletingSkill && <ConfirmDialog title="删除自定义 Skill" message={`确定删除“${deletingSkill.name}”吗？此操作不可恢复。`} onConfirm={() => void handleDelete()} onCancel={() => setDeletingSkill(null)} />}
    </div>
  );
}
