import React, { useEffect, useRef, useState } from 'react';
import MessageBubble from './MessageBubble';
import InputBox from './InputBox';
import ReactTrace from './ReactTrace';
import type { AgentEvent, Message } from '../types';

interface ChatContainerProps {
  messages: Message[];
  streamingContent: string;
  reactSteps: Extract<AgentEvent, { type: 'react_step' }>['data'][];
  isStreaming: boolean;
  inputValue: string;
  onInputChange: (value: string) => void;
  onSend: () => void;
  onStop: () => void;
  onCopy: (text: string) => void;
  onRegenerate: () => void;
  onEdit: (index: number, content: string) => void;
  pendingApproval?: Extract<AgentEvent, { type: 'tool_approval_requested' }>['data'] | null;
  onApproveTool?: (callId: string) => void;
  onRejectTool?: (callId: string) => void;
  currentTaskId?: string | null;
  onViewTask?: (taskId: string) => void;
}

const ChatContainer: React.FC<ChatContainerProps> = ({
  messages,
  streamingContent,
  reactSteps,
  isStreaming,
  inputValue,
  onInputChange,
  onSend,
  onStop,
  onCopy,
  onRegenerate,
  onEdit,
  pendingApproval,
  onApproveTool,
  onRejectTool,
  currentTaskId,
  onViewTask,
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
  }, [messages, streamingContent, reactSteps]);

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
        {currentTaskId && <button className="view-task-btn" onClick={() => onViewTask?.(currentTaskId)}>查看任务</button>}
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
        {(isStreaming || (pendingApproval && reactSteps.length > 0)) && (
          <>
            <ReactTrace steps={reactSteps} />
            <MessageBubble
              role="assistant"
              content={streamingContent}
              isStreaming={true}
              onCopy={onCopy}
            />
          </>
        )}
        {pendingApproval && (
          <section className="tool-approval-card" aria-label="Tool approval">
            <p className="tool-approval-eyebrow">需要确认工具操作</p>
            <h2>{pendingApproval.context?.tool_name || pendingApproval.name}</h2>
            {pendingApproval.context?.server_name && <p>来自 {pendingApproval.context.server_name}</p>}
            <pre>{JSON.stringify(pendingApproval.arguments, null, 2)}</pre>
            <div className="tool-approval-actions">
              <button className="skill-card-open" onClick={() => onApproveTool?.(pendingApproval.call_id)}>批准执行</button>
              <button className="skill-card-action" onClick={() => onRejectTool?.(pendingApproval.call_id)}>拒绝</button>
            </div>
          </section>
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
          disabled={isStreaming || Boolean(pendingApproval)}
        />
      </div>
    </div>
  );
};

export default ChatContainer;
