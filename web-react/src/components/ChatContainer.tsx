import React, { useEffect, useRef, useState } from 'react';
import MessageBubble from './MessageBubble';
import InputBox from './InputBox';
import type { Message } from '../types';

interface ChatContainerProps {
  messages: Message[];
  streamingContent: string;
  isStreaming: boolean;
  inputValue: string;
  onInputChange: (value: string) => void;
  onSend: () => void;
  onStop: () => void;
  onCopy: (text: string) => void;
  onRegenerate: () => void;
  onEdit: (index: number, content: string) => void;
}

const ChatContainer: React.FC<ChatContainerProps> = ({
  messages,
  streamingContent,
  isStreaming,
  inputValue,
  onInputChange,
  onSend,
  onStop,
  onCopy,
  onRegenerate,
  onEdit,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [showScrollBtn, setShowScrollBtn] = useState(false);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [editContent, setEditContent] = useState('');

  // Auto scroll when new messages arrive
  useEffect(() => {
    if (containerRef.current) {
      const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
      const isNearBottom = scrollHeight - scrollTop - clientHeight < 100;
      if (isNearBottom) {
        containerRef.current.scrollTop = scrollHeight;
      }
    }
  }, [messages, streamingContent]);

  const handleScroll = () => {
    if (containerRef.current) {
      const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
      const isNearBottom = scrollHeight - scrollTop - clientHeight < 100;
      setShowScrollBtn(!isNearBottom);
    }
  };

  const scrollToBottom = () => {
    if (containerRef.current) {
      containerRef.current.scrollTo({
        top: containerRef.current.scrollHeight,
        behavior: 'smooth',
      });
    }
  };

  const handleEditClick = (index: number, content: string) => {
    setEditingIndex(index);
    setEditContent(content);
  };

  const handleEditSave = () => {
    if (editingIndex !== null && editContent.trim()) {
      onEdit(editingIndex, editContent.trim());
      setEditingIndex(null);
      setEditContent('');
    }
  };

  const handleEditCancel = () => {
    setEditingIndex(null);
    setEditContent('');
  };

  return (
    <div className="chat-layout">
      <div className="chat-container" ref={containerRef} onScroll={handleScroll}>
        {messages.map((msg, index) => (
          <React.Fragment key={index}>
            {editingIndex === index ? (
              <div className="message user">
                <div className="message-content-wrapper user edit-mode">
                  <textarea
                    className="edit-textarea"
                    value={editContent}
                    onChange={(e) => setEditContent(e.target.value)}
                    autoFocus
                  />
                  <div className="edit-actions">
                    <button className="edit-btn save" onClick={handleEditSave}>
                      保存
                    </button>
                    <button className="edit-btn cancel" onClick={handleEditCancel}>
                      取消
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <MessageBubble
                role={msg.role}
                content={msg.content}
                onCopy={onCopy}
                onRegenerate={msg.role === 'assistant' ? onRegenerate : undefined}
                onEdit={msg.role === 'user' ? () => handleEditClick(index, msg.content) : undefined}
              />
            )}
          </React.Fragment>
        ))}
        {isStreaming && (
          <MessageBubble
            role="assistant"
            content={streamingContent}
            isStreaming={true}
            onCopy={onCopy}
          />
        )}
      </div>

      {showScrollBtn && (
        <button className="scroll-to-bottom" onClick={scrollToBottom}>
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 13.5 12 21m0 0-7.5-7.5M12 21V3" />
          </svg>
        </button>
      )}

      <div className="chat-input-bar">
        <InputBox
          value={inputValue}
          onChange={onInputChange}
          onSend={onSend}
          onStop={isStreaming ? onStop : undefined}
          placeholder="输入消息..."
          disabled={isStreaming}
        />
      </div>
    </div>
  );
};

export default ChatContainer;
