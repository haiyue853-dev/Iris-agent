import React, { useRef, useEffect } from 'react';
import AttachmentChip from './AttachmentChip';
import type { PendingAttachment } from '../types';

interface InputBoxProps {
  value: string;
  onChange: (value: string) => void;
  onSend: (text: string, attachmentIds: string[]) => void;
  onStop?: () => void;
  placeholder?: string;
  disabled?: boolean;
  autoFocus?: boolean;
  attachments?: PendingAttachment[];
  onFilesSelected?: (files: File[]) => void;
  onRemoveAttachment?: (clientId: string) => void;
}

const InputBox: React.FC<InputBoxProps> = ({
  value,
  onChange,
  onSend,
  onStop,
  placeholder = '输入消息...',
  disabled = false,
  autoFocus = false,
  attachments = [],
  onFilesSelected,
  onRemoveAttachment,
}) => {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (autoFocus && textareaRef.current) {
      textareaRef.current.focus();
    }
  }, [autoFocus]);

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    onChange(e.target.value);
    autoResize(e.target);
  };

  const autoResize = (el: HTMLTextAreaElement) => {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 160) + 'px';
  };

  const readyAttachmentIds = attachments.filter((attachment) => attachment.status === 'ready' && attachment.id).map((attachment) => attachment.id as string);
  const hasPendingUpload = attachments.some((attachment) => attachment.status === 'uploading');
  const canSend = !disabled && !hasPendingUpload && (value.trim().length > 0 || readyAttachmentIds.length > 0);
  const send = () => {
    if (canSend) onSend(value.trim(), readyAttachmentIds);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  const hasContent = value.trim().length > 0;

  return (
    <div className={`input-box ${hasContent ? 'has-content' : ''}`}>
      {attachments.length > 0 && <div className="attachment-chip-list" aria-label="已选附件">
        {attachments.map((attachment) => <AttachmentChip key={attachment.client_id} attachment={attachment} onRemove={onRemoveAttachment ?? (() => undefined)} />)}
      </div>}
      <textarea
        ref={textareaRef}
        className="input-textarea"
        value={value}
        onChange={handleInput}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        rows={1}
        disabled={disabled}
      />
      <div className="input-footer">
        <div className="input-actions">
          <input ref={fileInputRef} className="visually-hidden" aria-label="添加附件" type="file" multiple onChange={(event) => { onFilesSelected?.(Array.from(event.target.files ?? [])); event.currentTarget.value = ''; }} disabled={disabled} accept=".txt,.md,.pdf,.docx,.xlsx,.xls,.png,.jpg,.jpeg,.webp" />
          <button type="button" className="action-btn" title="添加附件" onClick={() => fileInputRef.current?.click()} disabled={disabled}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M12 5v14M5 12h14" />
            </svg>
          </button>
        </div>
        <div className="input-right">
          <span className="input-hint">Enter 发送 · Shift+Enter 换行</span>
          {onStop ? (
            <button
              className="send-btn stop"
              onClick={onStop}
              title="停止生成"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                <rect x="6" y="6" width="12" height="12" rx="2" />
              </svg>
            </button>
          ) : (
            <button
              className={`send-btn ${canSend ? 'active' : ''}`}
              onClick={send}
              disabled={!canSend}
              title="发送"
            >
              {/* 圆形按钮 + 向上箭头（简洁版） */}
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 19V5" />
                <path d="M5 12l7-7 7 7" />
              </svg>
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default InputBox;
