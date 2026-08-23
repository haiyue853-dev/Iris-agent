import { describe, expect, it } from "vitest";
import { groupSourceParts, groupToolParts, toThreadMessages } from "./irisRuntime";

describe("toThreadMessages rich parts", () => {
  it("preserves reasoning and URL sources as typed assistant parts", () => {
    const [message] = toThreadMessages([
      {
        role: "assistant",
        content: "结论",
        reasoning: "正在分析",
        sources: [
          { id: "source-1", title: "参考资料", url: "https://example.com/doc" },
        ],
      },
    ]);

    expect(message.content).toEqual([
      expect.objectContaining({
        type: "tool-call",
        toolName: "iris_sources_group",
        result: { __irisKind: "sources-group", items: [{ id: "source-1", title: "参考资料", url: "https://example.com/doc" }] },
      }),
      { type: "reasoning", text: "正在分析" },
      { type: "text", text: "结论" },
    ]);
  });

  it("keeps legacy text-only messages unchanged", () => {
    const [message] = toThreadMessages([{ role: "user", content: "你好" }]);
    expect(message.content).toEqual([{ type: "text", text: "你好" }]);
  });
});

describe("tool part grouping", () => {
  it("combines ordinary calls while leaving approvals independent", () => {
    const grouped = groupToolParts([
      { type: "tool-call", toolCallId: "c1", toolName: "list_directory", args: { path: "." }, argsText: '{"path":"."}', result: { files: [] } },
      { type: "tool-call", toolCallId: "c2", toolName: "read_file", args: { path: "a" }, argsText: '{"path":"a"}' },
      { type: "tool-call", toolCallId: "c3", toolName: "write_file", args: {}, argsText: "{}", result: { __irisKind: "approval", call_id: "c3", title: "write_file", raw: {} } },
    ]);

    expect(grouped).toHaveLength(2);
    expect(grouped[0]).toMatchObject({ toolName: "iris_tool_group", result: { __irisKind: "tool-group", items: [
      { callId: "c1", name: "list_directory", state: "completed" },
      { callId: "c2", name: "read_file", state: "running" },
    ] } });
    expect(grouped[1]).toMatchObject({ toolCallId: "c3", toolName: "write_file" });
  });
});

describe("source part grouping", () => {
  it("groups URL sources into one synthetic part", () => {
    const grouped = groupSourceParts([
      { type: "source", sourceType: "url", id: "1", url: "https://react.dev", title: "React" },
      { type: "source", sourceType: "url", id: "2", url: "https://vite.dev", title: "Vite" },
      { type: "text", text: "正文" },
    ]);

    expect(grouped).toHaveLength(2);
    expect(grouped[0]).toMatchObject({
      type: "tool-call",
      toolName: "iris_sources_group",
      result: { __irisKind: "sources-group", items: [{ title: "React" }, { title: "Vite" }] },
    });
  });
});
