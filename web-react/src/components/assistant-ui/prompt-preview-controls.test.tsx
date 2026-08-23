import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PromptPreviewControls } from "./prompt-preview-controls";

describe("PromptPreviewControls", () => {
  it("labels preview-only actions without sending anything", () => {
    render(<PromptPreviewControls />);
    fireEvent.click(screen.getByRole("button", { name: "联网搜索（暂未开放）" }));
    expect(screen.getByRole("status")).toHaveTextContent("联网搜索暂未开放");
  });
});
