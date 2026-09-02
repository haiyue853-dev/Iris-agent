import { SparklesIcon, XIcon } from "lucide-react";
import { useEffect, useRef } from "react";

import { useIrisChat } from "@/components/assistant-ui/iris-chat-context";
import type { SkillInfo } from "@/types";

export function ActiveSkillChip() {
  const { activeSkill, selectSkill } = useIrisChat();
  if (!activeSkill) return null;
  return (
    <div
      className="iris-skill-chip"
      aria-label={`已激活 Skill：${activeSkill.name}`}
    >
      <SparklesIcon className="size-4" aria-hidden="true" />
      <span className="font-medium">{activeSkill.name}</span>
      <button type="button" className="iris-skill-chip-remove" aria-label={`取消 Skill：${activeSkill.name}`} onClick={() => selectSkill(null)}>
        <XIcon className="size-3.5" aria-hidden="true" />
      </button>
    </div>
  );
}

export function SkillPicker() {
  const { activeSkill, selectSkill, skillMenuOpen, availableSkills, skillsLoading, skillsError, toggleSkillMenu, closeSkillMenu } = useIrisChat();
  const pickerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!skillMenuOpen) return;
    const closeOnOutsidePointer = (event: PointerEvent) => {
      const target = event.target;
      if (target instanceof Node && !pickerRef.current?.contains(target)) closeSkillMenu();
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeSkillMenu();
    };
    document.addEventListener("pointerdown", closeOnOutsidePointer);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOnOutsidePointer);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [closeSkillMenu, skillMenuOpen]);

  const choose = (skill: SkillInfo) => {
    selectSkill(skill);
  };

  return (
    <div ref={pickerRef} className="relative">
      <button type="button" className={`iris-prompt-tool ${activeSkill ? "is-active" : ""}`} aria-label="选择 Skill" aria-expanded={skillMenuOpen} onClick={() => void toggleSkillMenu()}>
        <SparklesIcon className="size-4" aria-hidden="true" />
        <span>Skill</span>
      </button>
      {skillMenuOpen && (
        <div className="iris-skill-menu" aria-label="Skill 列表">
          {skillsLoading && <p className="px-2 py-3 text-sm text-muted-foreground">正在加载…</p>}
          {skillsError && <p className="px-2 py-3 text-sm text-destructive">{skillsError}</p>}
          {!skillsLoading && !skillsError && availableSkills?.length === 0 && <p className="px-2 py-3 text-sm text-muted-foreground">暂无可用 Skill</p>}
          {availableSkills?.map((skill) => (
            <button key={skill.id} type="button" className="iris-skill-menu-item" aria-label={`使用 Skill：${skill.name}`} onClick={() => choose(skill)}>
              <span className="iris-skill-icon"><SparklesIcon className="size-4" aria-hidden="true" /></span>
              <span className="font-medium">{skill.name}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
