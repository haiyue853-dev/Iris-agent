import { createContext, useContext } from "react";
import type { SkillInfo } from "@/types";

export type IrisChatContextValue = {
  resolveApproval: (callId: string, approved: boolean) => Promise<void>;
  regenerate: (userMessageId: string) => Promise<void>;
  isRegenerating: boolean;
  capabilityModeLocked: boolean;
  modelProfiles: Array<{ id: string; name: string; model: string }>;
  selectedModelProfileId: string | null;
  activeModelProfileId: string | null;
  selectModelProfile: (id: string | null) => Promise<void>;
  modelSelectionLocked: boolean;
  knowledgeCollectionId?: string;
  activeSkill: SkillInfo | null;
  selectSkill: (skill: SkillInfo | null) => void;
  skillMenuOpen: boolean;
  availableSkills: SkillInfo[] | null;
  skillsLoading: boolean;
  skillsError: string;
  toggleSkillMenu: () => Promise<void>;
  closeSkillMenu: () => void;
};

export const IrisChatContext = createContext<IrisChatContextValue | null>(null);

export function useIrisChat(): IrisChatContextValue {
  const ctx = useContext(IrisChatContext);
  return ctx ?? {
    capabilityModeLocked: false,
    resolveApproval: async () => undefined,
    regenerate: async () => undefined,
    isRegenerating: false,
    modelProfiles: [],
    selectedModelProfileId: null,
    activeModelProfileId: null,
    selectModelProfile: async () => undefined,
    modelSelectionLocked: false,
    knowledgeCollectionId: undefined,
    activeSkill: null,
    selectSkill: () => undefined,
    skillMenuOpen: false,
    availableSkills: null,
    skillsLoading: false,
    skillsError: "",
    toggleSkillMenu: async () => undefined,
    closeSkillMenu: () => undefined,
  };
}
