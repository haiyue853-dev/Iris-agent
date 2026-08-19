import React from 'react';
import InputBox from './InputBox';
import type { PendingAttachment } from '../types';

interface WelcomePageProps {
  inputValue: string;
  onInputChange: (value: string) => void;
  onSend: (text: string, attachmentIds: string[]) => void;
  onNavigate?: (view: 'chat' | 'aihot') => void;
  attachments?: PendingAttachment[];
  onFilesSelected?: (files: File[]) => void;
  onRemoveAttachment?: (clientId: string) => void;
}

const WelcomePage: React.FC<WelcomePageProps> = ({
  inputValue,
  onInputChange,
  onSend,
  onNavigate,
  attachments,
  onFilesSelected,
  onRemoveAttachment,
}) => {
  return (
    <div className="welcome-container">
      <div className="welcome-inner">
        <h1 className="welcome-title">Iris 能为你做什么？</h1>
        <p className="welcome-subtitle">智能助手 · 每日资讯 · 日报，随时待命</p>

        {onNavigate && (
          <button className="welcome-news-entry" onClick={() => onNavigate('aihot')}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16a2 2 0 0 1-4 0V9" />
              <path d="M18 14h-8" />
              <path d="M15 18h-5" />
              <path d="M10 6h8v4h-8V6z" />
            </svg>
            了解资讯
            <svg className="entry-arrow" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9 18l6-6-6-6" />
            </svg>
          </button>
        )}

        <div className="input-wrapper">
          <InputBox
            value={inputValue}
            onChange={onInputChange}
            onSend={onSend}
            placeholder="输入消息..."
            autoFocus={true}
            attachments={attachments}
            onFilesSelected={onFilesSelected}
            onRemoveAttachment={onRemoveAttachment}
          />
        </div>
        <p className="welcome-hint">Iris 由 AI 驱动，回答可能不准确，请甄别使用</p>
      </div>
    </div>
  );
};

export default WelcomePage;
