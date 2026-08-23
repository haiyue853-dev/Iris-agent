import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SourcesGroup } from "./sources-group";

describe("SourcesGroup", () => {
  it("collapses sources and renders only safe links", () => {
    render(<SourcesGroup items={[
      { id: "1", url: "https://react.dev", title: "React" },
      { id: "2", url: "javascript:alert(1)", title: "Unsafe" },
    ]} />);

    const trigger = screen.getByRole("button", { name: "共 2 个来源" });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(trigger);
    expect(screen.getByRole("link", { name: /React/ })).toBeVisible();
    expect(screen.queryByRole("link", { name: /Unsafe/ })).not.toBeInTheDocument();
  });
});
