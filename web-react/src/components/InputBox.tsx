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
    <div className="input-box">
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
          <button className="action-btn" title="添加">+</button>
        </div>
        <div className="input-right">
          <span className="mode-selector">
            快速 进阶
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />
            </svg>
          </span>
          {onStop ? (
            <button
              className="send-btn stop"
              onClick={onStop}
              title="停止生成"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
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
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 19V5M5 12l7-7 7 7" />
              </svg>
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default InputBox;
