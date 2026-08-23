import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Reasoning } from "./reasoning";

describe("Reasoning", () => {
  it("keeps completed reasoning collapsed by default", () => {
    render(<Reasoning type="reasoning" text="分析项目结构" status={{ type: "complete" }} />);
    const trigger = screen.getByRole("button", { name: "思考过程" });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(trigger);
    expect(screen.getByText("分析项目结构")).toBeVisible();
  });
});
