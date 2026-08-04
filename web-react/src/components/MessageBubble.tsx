import React from 'react';
import { marked } from 'marked';

interface MessageBubbleProps {
  role: 'user' | 'assistant';
  content: string;
  isStreaming?: boolean;
  onCopy: (text: string) => void;
  onRegenerate?: (text: string) => void;
  onEdit?: () => void;
}

const MessageBubble: React.FC<MessageBubbleProps> = ({
  role,
  content,
  isStreaming = false,
  onCopy,
  onRegenerate,
  onEdit,
}) => {
  const renderContent = () => {
    if (isStreaming && !content) {
      return (
        <div className="loading-dots">
          <span></span>
          <span></span>
          <span></span>
        </div>
      );
    }

    if (role === 'user') {
      return <>{content}</>;
    }

    return (
      <>
        <div className="model-badge">
          <span className="dot"></span> Iris
        </div>
        <div
          className="message-content"
          dangerouslySetInnerHTML={{ __html: marked.parse(content) as string }}
        />
      </>
    );
  };

  return (
    <div className={`message ${role}`}>
      <div className={`message-content-wrapper ${role}`}>
        {renderContent()}
        {!isStreaming && (
          <div className="message-actions">
            <button
              className="msg-action-btn"
              onClick={() => onCopy(content)}
              title="复制"
            >
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M15.666 3.888A2.25 2.25 0 0 0 13.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 0 1-.75.75H9.75a.75.75 0 0 1-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 0 1-2.25 2.25H6.75A2.25 2.25 0 0 1 4.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 0 1 1.927-.184" />
              </svg>
            </button>
            {role === 'assistant' && onRegenerate && (
              <button
                className="msg-action-btn"
                onClick={() => onRegenerate(content)}
                title="重新生成"
              >
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.992 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182" />
                </svg>
              </button>
            )}
            {role === 'user' && onEdit && (
              <button
                className="msg-action-btn"
                onClick={onEdit}
                title="编辑"
              >
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0 1 15.75 21H5.25A2.25 2.25 0 0 1 3 18.75V8.25A2.25 2.25 0 0 1 5.25 6H10" />
                </svg>
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default MessageBubble;
