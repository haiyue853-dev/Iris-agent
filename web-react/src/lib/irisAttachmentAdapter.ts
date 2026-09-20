import type { Attachment, AttachmentAdapter, CompleteAttachment, PendingAttachment } from "@assistant-ui/react";
import type { ChatAttachment } from "@/types";

export const IRIS_ATTACHMENT_ACCEPT = [
  ".docx",
  ".pdf",
  ".md",
  ".txt",
  ".xlsx",
  ".xls",
  ".png",
  ".jpg",
  ".jpeg",
  ".webp",
].join(",");

type IrisAttachmentAdapterDeps = {
  ensureSession: (name: string) => Promise<string>;
  getSessionId: () => string;
  upload: (sessionId: string, file: File) => Promise<ChatAttachment>;
  remove: (sessionId: string, attachmentId: string) => Promise<void>;
};

type IrisAttachmentAdapter = AttachmentAdapter & {
  add(state: { file: File }): Promise<PendingAttachment>;
  send(attachment: PendingAttachment): Promise<CompleteAttachment>;
};

function attachmentType(mediaType: string): "image" | "document" {
  return mediaType.startsWith("image/") ? "image" : "document";
}

export function createIrisAttachmentAdapter(deps: IrisAttachmentAdapterDeps): IrisAttachmentAdapter {
  return {
    accept: IRIS_ATTACHMENT_ACCEPT,
    async add({ file }): Promise<PendingAttachment> {
      const sessionId = await deps.ensureSession(file.name);
      const uploaded = await deps.upload(sessionId, file);
      if (!uploaded.id) throw new Error("附件上传成功但未返回附件 ID");
      return {
        id: uploaded.id,
        type: attachmentType(uploaded.media_type || file.type),
        name: uploaded.original_name || file.name,
        contentType: uploaded.media_type || file.type,
        file,
        status: { type: "requires-action", reason: "composer-send" },
      };
    },
    async remove(attachment: Attachment): Promise<void> {
      const sessionId = deps.getSessionId();
      if (sessionId && attachment.id) await deps.remove(sessionId, attachment.id);
    },
    async send(attachment: PendingAttachment): Promise<CompleteAttachment> {
      return {
        ...attachment,
        status: { type: "complete" },
        content: [],
      };
    },
  };
}
