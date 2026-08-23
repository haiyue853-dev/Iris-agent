import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

describe("assistant attachment UI", () => {
  const source = readFileSync(
    resolve("src/components/assistant-ui/attachment.tsx"),
    "utf8",
  );

  it("shows attachment names and localized controls", () => {
    expect(source).toContain("aui-attachment-name");
    expect(source).toContain('tooltip="移除附件"');
    expect(source).toContain('tooltip="添加附件"');
    expect(source).toContain('aria-label="添加附件"');
  });

  it("hides attachment containers when empty", () => {
    expect(source).toContain("empty:hidden");
  });
});
