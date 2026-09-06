import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ApprovalCard } from "./approval-card";

describe("ApprovalCard", () => {
  it("uses Chinese yes/no labels and straight-edged surfaces by default", () => {
    render(<ApprovalCard id="approval-1" title="是否继续？" onConfirm={vi.fn()} onCancel={vi.fn()} />);

    expect(screen.getByRole("button", { name: "是" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "否" })).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toHaveClass("rounded-none");
    expect(screen.getByRole("button", { name: "是" })).toHaveClass("rounded-none");
  });
});
