import { useEffect, useState } from 'react';

import type { UserSkillDraft } from '../../api/skills';

export type UserSkillEditorValue = UserSkillDraft & { id?: string };

const TOOLSET_OPTIONS: Array<{ id: UserSkillDraft['allowed_toolsets'][number]; label: string }> = [
  { id: 'safe', label: '基础读取' },
  { id: 'research', label: '联网检索' },
  { id: 'coding', label: '文件与命令' },
  { id: 'knowledge', label: '知识库' },
  { id: 'skills', label: '技能与记忆' },
  { id: 'delegation', label: '子代理' },
];

interface UserSkillEditorProps {
  initialValue: UserSkillEditorValue;
  onSave: (draft: UserSkillDraft) => Promise<void>;
  onCancel: () => void;
}

export default function UserSkillEditor({ initialValue, onSave, onCancel }: UserSkillEditorProps) {
  const [draft, setDraft] = useState<UserSkillEditorValue>(initialValue);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setDraft(initialValue);
  }, [initialValue]);

  const canSave = Boolean(draft.name.trim() && draft.description.trim() && draft.content.trim());

  const save = async () => {
    if (!canSave || saving) return;
    setSaving(true);
    try {
      await onSave({ name: draft.name, description: draft.description, content: draft.content, allowed_toolsets: draft.allowed_toolsets });
    } catch {
      return;
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className="user-skill-editor" onSubmit={(event) => { event.preventDefault(); void save(); }}>
      <div className="user-skill-editor-head">
        <h3 id="user-skill-editor-title">{initialValue.id ? '编辑 Skill' : '新建 Skill'}</h3>
        <p>使用 Markdown 写下这个 Skill 在聊天中应遵循的提示词。</p>
      </div>
      <div className="user-skill-field">
        <label htmlFor="user-skill-name">Skill 名称</label>
        <input id="user-skill-name" value={draft.name} onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))} />
      </div>
      <div className="user-skill-field">
        <label htmlFor="user-skill-description">用途说明</label>
        <input id="user-skill-description" value={draft.description} onChange={(event) => setDraft((current) => ({ ...current, description: event.target.value }))} />
      </div>
      <div className="user-skill-field">
        <label htmlFor="user-skill-content">Skill 正文</label>
        <textarea id="user-skill-content" value={draft.content} maxLength={4000} rows={9} onChange={(event) => setDraft((current) => ({ ...current, content: event.target.value }))} />
        <small>{draft.content.length} / 4000</small>
      </div>
      <fieldset className="user-skill-toolsets">
        <legend>允许使用的工具</legend>
        <div>
          {TOOLSET_OPTIONS.map((option) => (
            <label key={option.id}>
              <input type="checkbox" checked={draft.allowed_toolsets.includes(option.id)} onChange={() => setDraft((current) => ({
                ...current,
                allowed_toolsets: current.allowed_toolsets.includes(option.id)
                  ? current.allowed_toolsets.filter((item) => item !== option.id)
                  : [...current.allowed_toolsets, option.id],
              }))} />
              {option.label}
            </label>
          ))}
        </div>
      </fieldset>
      <div className="user-skill-editor-actions">
        <button type="button" onClick={onCancel} disabled={saving}>取消</button>
        <button type="submit" disabled={!canSave || saving}>{saving ? '正在保存…' : '保存 Skill'}</button>
      </div>
    </form>
  );
}
