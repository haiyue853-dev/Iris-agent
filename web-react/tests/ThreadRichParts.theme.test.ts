import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

describe("assistant rich message part registration", () => {
  const threadSource = readFileSync(
    resolve("src/components/assistant-ui/thread.tsx"),
    "utf8",
  );
  const toolSource = readFileSync(
    resolve("src/components/assistant-ui/tool-fallback.tsx"),
    "utf8",
  );
  const toolGroupSource = readFileSync(
    resolve("src/components/assistant-ui/tool-group.tsx"),
    "utf8",
  );
  const appCss = readFileSync(resolve("src/App.css"), "utf8");

  it("registers dedicated reasoning and source renderers", () => {
    expect(threadSource).toContain("Reasoning: Reasoning");
    expect(threadSource).toContain("Source: Source");
  });

  it("uses localized labels for core message actions", () => {
    expect(threadSource).toContain('tooltip="复制"');
    expect(threadSource).toContain('tooltip="重新生成"');
    expect(threadSource).toContain('placeholder="输入消息…"');
  });

  it("presents running, completed, cancelled and failed tool states", () => {
    expect(toolSource).toContain('"工具运行中"');
    expect(toolSource).toContain('"工具已完成"');
    expect(toolSource).toContain('"工具已停止"');
    expect(toolSource).toContain('"工具执行失败"');
    expect(toolGroupSource).toContain('item.state === "cancelled"');
    expect(toolGroupSource).toContain("已停止");
  });

  it("keeps the grouped tool disclosure compact", () => {
    expect(appCss).toMatch(/\.iris-tool-group-toggle\s*\{[\s\S]*?padding:\s*\.45rem\s+\.7rem[\s\S]*?font-size:\s*\.75rem/);
    expect(appCss).toMatch(/\.iris-tool-item summary\s*\{[\s\S]*?padding:\s*\.4rem\s+\.7rem[\s\S]*?font-size:\s*\.72rem/);
  });
});
