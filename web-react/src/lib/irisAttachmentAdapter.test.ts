import { describe, expect, it, vi } from "vitest";
import type { PendingAttachment } from "@assistant-ui/react";
import { createIrisAttachmentAdapter } from "./irisAttachmentAdapter";

describe("Iris attachment adapter", () => {
  it("uploads a selected or dropped file before it can be sent", async () => {
    const upload = vi.fn().mockResolvedValue({
      id: "attachment-1",
      original_name: "notes.txt",
      media_type: "text/plain",
    });
    const adapter = createIrisAttachmentAdapter({
      ensureSession: vi.fn().mockResolvedValue("session-1"),
      getSessionId: () => "session-1",
      upload,
      remove: vi.fn(),
    });
    const file = new File(["memo"], "notes.txt", { type: "text/plain" });

    const pending = await adapter.add({ file });

    expect(upload).toHaveBeenCalledWith("session-1", file);
    expect(pending).toMatchObject({
      id: "attachment-1",
      name: "notes.txt",
      contentType: "text/plain",
      status: { type: "requires-action", reason: "composer-send" },
    });
    await expect(adapter.send(pending as PendingAttachment)).resolves.toMatchObject({ id: "attachment-1", status: { type: "complete" } });
  });
});
