import type { PendingAttachment } from '../types';

type Props = {
  attachment: PendingAttachment;
  onRemove: (clientId: string) => void;
};

const statusLabel = (attachment: PendingAttachment) => {
  if (attachment.status === 'uploading') return '上传中';
  if (attachment.status === 'error') {
    if (attachment.error && !/[A-Za-z]:[\\/]|(?:^|\s)\/[\w.-]/.test(attachment.error)) return attachment.error;
    return '上传失败';
  }
  return '已就绪';
};

export default function AttachmentChip({ attachment, onRemove }: Props) {
  return <span className={`attachment-chip ${attachment.status}`}>
    <span className="attachment-chip-name">{attachment.original_name}</span>
    <span className="attachment-chip-status">{statusLabel(attachment)}</span>
    <button type="button" className="attachment-chip-remove" aria-label={`移除 ${attachment.original_name}`} onClick={() => onRemove(attachment.client_id)}>×</button>
  </span>;
}
