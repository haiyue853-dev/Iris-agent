import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { IrisChatContext, type IrisChatContextValue } from "./iris-chat-context";
import { SkillPicker } from "./skill-picker";

describe("SkillPicker", () => {
  it("closes the menu when clicking outside", () => {
    const closeSkillMenu = vi.fn();
    const contextValue = {
      capabilityModeLocked: false,
      resolveApproval: async () => undefined,
      regenerate: async () => undefined,
      isRegenerating: false,
      modelProfiles: [],
      selectedModelProfileId: null,
      activeModelProfileId: null,
      selectModelProfile: async () => undefined,
      modelSelectionLocked: false,
      activeSkill: null,
      selectSkill: () => undefined,
      skillMenuOpen: true,
      availableSkills: [],
      skillsLoading: false,
      skillsError: "",
      toggleSkillMenu: async () => undefined,
      closeSkillMenu,
    } as IrisChatContextValue & { closeSkillMenu: () => void };

    render(
      <IrisChatContext.Provider value={contextValue}>
        <SkillPicker />
      </IrisChatContext.Provider>,
    );

    expect(screen.getByLabelText("Skill 列表")).toBeInTheDocument();
    fireEvent.pointerDown(document.body);
    expect(closeSkillMenu).toHaveBeenCalledTimes(1);
  });
});
