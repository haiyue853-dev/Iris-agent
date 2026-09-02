import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(join(process.cwd(), "src", "index.css"), "utf8");

describe("collapsed sidebar layout", () => {
  it("lets the edge rail escape the sidebar shell", () => {
    expect(css).toMatch(/\[data-slot="sidebar"\]\s*\{[^}]*overflow:\s*visible/s);
  });

  it("removes hidden labels and session history from icon layout", () => {
    expect(css).toMatch(/data-state="collapsed"[^}]*\.sidebar-label[^}]*display:\s*none/s);
    expect(css).toMatch(/data-state="collapsed"[^}]*nav\[aria-label="历史对话"\][^}]*display:\s*none/s);
  });
});
