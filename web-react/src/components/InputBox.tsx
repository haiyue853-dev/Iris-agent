import React, { useRef, useEffect } from 'react';

interface InputBoxProps {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  onStop?: () => void;
  placeholder?: string;
  disabled?: boolean;
  autoFocus?: boolean;
}

const InputBox: React.FC<InputBoxProps> = ({
  value,
  onChange,
  onSend,
  onStop,
  placeholder = '输入消息...',
  disabled = false,
  autoFocus = false,
}) => {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

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

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  };

  const hasContent = value.trim().length > 0;

  return (
    <div className={`input-box ${hasContent ? 'has-content' : ''}`}>
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
          <button className="action-btn" title="添加">
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
              className={`send-btn ${hasContent ? 'active' : ''}`}
              onClick={onSend}
              disabled={!hasContent || disabled}
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
