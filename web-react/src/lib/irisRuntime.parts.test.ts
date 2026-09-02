import { describe, expect, it } from "vitest";
import { groupSourceParts, groupToolParts, toThreadMessages, type IrisToolGroupResult } from "./irisRuntime";

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

  it("renders persisted knowledge drafts as editable tool parts", () => {
    const messages = toThreadMessages([
      { role: "tool", name: "add_knowledge", tool_call_id: "call-1", content: JSON.stringify({ __irisKind: "knowledge-draft", title: "面试题", content: "答案", category: "面经" }) } as unknown as import("../types").Message,
    ]);

    expect(messages[0]).toMatchObject({
      role: "assistant",
      content: [{ type: "tool-call", toolName: "add_knowledge", result: { __irisKind: "knowledge-draft", title: "面试题" } }],
    });
  });

  it("renders persisted knowledge citations as a citation panel", () => {
    const [message] = toThreadMessages([{
      role: "assistant",
      content: "答案 [1]",
      citations: [{ index: 1, document_id: "doc-1", chunk_id: "chunk-1", title: "启动", content: "npm run dev" }],
    }]);

    expect(message.content).toEqual(expect.arrayContaining([
      expect.objectContaining({
        type: "tool-call",
        toolName: "iris_knowledge_citations",
        result: { __irisKind: "knowledge-citations", items: [{ index: 1, document_id: "doc-1", chunk_id: "chunk-1", title: "启动", content: "npm run dev" }] },
      }),
    ]));
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

  it("updates the already-rendered tool group when pending tools are cancelled", () => {
    const parts = [
      { type: "tool-call" as const, toolCallId: "c1", toolName: "delegate_tasks", args: {}, argsText: "{}" },
    ];
    const firstGroup = groupToolParts(parts);
    const priorResult = firstGroup[0].result as IrisToolGroupResult;

    const cancelledGroup = groupToolParts(parts, true, priorResult);

    expect(cancelledGroup[0].result).toBe(priorResult);
    expect(cancelledGroup[0]).toMatchObject({
      result: { items: [{ callId: "c1", state: "cancelled" }] },
    });
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
