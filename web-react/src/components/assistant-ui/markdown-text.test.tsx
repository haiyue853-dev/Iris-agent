import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MarkdownLink, remarkCitationLinks } from "./markdown-text";

describe("MarkdownLink", () => {
  it("opens external links in a new tab without exposing the opener", () => {
    render(<MarkdownLink href="https://notes.example.com/rag">查看原文</MarkdownLink>);

    const link = screen.getByRole("link", { name: "查看原文" });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("dispatches a local citation event instead of navigating", () => {
    const listener = vi.fn();
    window.addEventListener("iris:open-knowledge-citation", listener);
    render(<MarkdownLink href="#iris-citation-2">[2]</MarkdownLink>);

    fireEvent.click(screen.getByRole("button", { name: "查看引用 [2]" }));

    expect(listener).toHaveBeenCalledOnce();
    expect(listener.mock.calls[0][0].detail).toEqual({ index: 2 });
    window.removeEventListener("iris:open-knowledge-citation", listener);
  });

  it("converts bracketed citation markers into local links", () => {
    const tree = { type: "root", children: [{ type: "paragraph", children: [{ type: "text", value: "结论见 [1] 和 [12]。" }] }] };

    remarkCitationLinks()(tree);

    expect(tree.children[0].children.map((node: { type: string; url?: string }) => [node.type, node.url])).toEqual([
      ["text", undefined],
      ["link", "#iris-citation-1"],
      ["text", undefined],
      ["link", "#iris-citation-12"],
      ["text", undefined],
    ]);
  });
});
