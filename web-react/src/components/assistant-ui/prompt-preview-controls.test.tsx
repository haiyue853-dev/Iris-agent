import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { PromptPreviewControls } from "./prompt-preview-controls";
import { IrisChatContext } from "./iris-chat-context";

describe("PromptPreviewControls", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("renders the online switch as an interactive control", () => {
    render(<PromptPreviewControls />);
    expect(screen.getByRole("button", { name: "联网搜索" })).toHaveAttribute("aria-pressed", "false");
  });

  it("uses the active style when a knowledge base is selected", () => {
    localStorage.setItem("iris_chat_use_knowledge", "true");
    render(<PromptPreviewControls />);
    const knowledge = screen.getByRole("button", { name: "选择知识库" });

    expect(knowledge).toHaveClass("is-online");
    expect(knowledge).toHaveAttribute("aria-pressed", "true");
  });

  it("closes knowledge and model menus when clicking outside", () => {
    render(<PromptPreviewControls />);

    fireEvent.click(screen.getByRole("button", { name: "选择知识库" }));
    expect(screen.getByRole("button", { name: "不开启知识库" })).toBeVisible();
    expect(screen.getByRole("button", { name: "不开启知识库" }).parentElement).not.toHaveClass("rounded-md");
    fireEvent.pointerDown(document.body);
    expect(screen.queryByRole("button", { name: "不开启知识库" })).not.toBeInTheDocument();

    const model = screen.getByRole("button", { name: "选择模型" });
    expect(model.querySelector(".lucide-chevron-down")).not.toHaveClass("rotate-180");
    fireEvent.click(model);
    expect(model).toHaveAttribute("aria-expanded", "true");
    expect(model.querySelector(".lucide-chevron-down")).toHaveClass("rotate-180");
    expect(screen.queryByRole("button", { name: "当前模型" })).not.toBeInTheDocument();
    fireEvent.pointerDown(document.body);
    expect(model).toHaveAttribute("aria-expanded", "false");
  });

  it("shows model identifiers without profile names", () => {
    render(
      <IrisChatContext.Provider value={{
        capabilityModeLocked: false,
        resolveApproval: async () => undefined,
        regenerate: async () => undefined,
        isRegenerating: false,
        modelProfiles: [{ id: "profile-1", name: "我的工作模型", model: "qwen-max" }],
        selectedModelProfileId: "profile-1",
        activeModelProfileId: "profile-1",
        selectModelProfile: async () => undefined,
        modelSelectionLocked: false,
        activeSkill: null,
        selectSkill: () => undefined,
        skillMenuOpen: false,
        availableSkills: null,
        skillsLoading: false,
        skillsError: "",
        toggleSkillMenu: async () => undefined,
        closeSkillMenu: () => undefined,
      }}>
        <PromptPreviewControls />
      </IrisChatContext.Provider>,
    );

    expect(screen.getByText("qwen-max")).toBeVisible();
    expect(screen.queryByText("我的工作模型")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "选择模型" }));
    expect(screen.getAllByText("qwen-max")).toHaveLength(2);
  });
});
