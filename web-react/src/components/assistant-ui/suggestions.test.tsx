import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Suggestions } from "./suggestions";

describe("Suggestions", () => {
  it("returns the selected prompt without submitting it", () => {
    const onSelect = vi.fn();
    render(<Suggestions items={["分析项目", "运行测试"]} onSelect={onSelect} />);
    fireEvent.click(screen.getByRole("button", { name: "分析项目" }));
    expect(onSelect).toHaveBeenCalledWith("分析项目");
  });
});
