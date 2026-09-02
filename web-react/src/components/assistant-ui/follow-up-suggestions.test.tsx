import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { FollowUpSuggestions } from "./follow-up-suggestions";

describe("FollowUpSuggestions", () => {
  it("dispatches the selected follow-up question to the composer", () => {
    const listener = vi.fn();
    window.addEventListener("iris:use-follow-up", listener);
    render(<FollowUpSuggestions items={["请展开说明分块策略。"]} />);

    fireEvent.click(screen.getByRole("button", { name: "请展开说明分块策略。" }));

    expect(listener).toHaveBeenCalledOnce();
    expect(listener.mock.calls[0][0].detail).toEqual({ text: "请展开说明分块策略。" });
    window.removeEventListener("iris:use-follow-up", listener);
  });
});
