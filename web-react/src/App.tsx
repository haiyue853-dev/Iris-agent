import { useState, useEffect } from 'react';
import Sidebar from './components/Sidebar';
import WelcomePage from './components/WelcomePage';
import ChatContainer from './components/ChatContainer';
import { useChat } from './hooks/useChat';
import './App.css';

function App() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [welcomeInput, setWelcomeInput] = useState('');
  const [chatInput, setChatInput] = useState('');

  const {
    messages,
    isStreaming,
    streamingContent,
    toast,
    currentSessionId,
    sessions,
    handleSendWithSession,
    handleRegenerate,
    handleStop,
    handleNewChat,
    handleCopy,
    handleEditMessage,
    handleSwitchSession,
    handleDeleteSession,
  } = useChat();

  // Ctrl+K shortcut
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        if (messages.length > 0) {
          if (confirm('确定要新建会话吗？')) {
            handleNewChat();
          }
        } else {
          handleNewChat();
        }
      }
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [handleNewChat, messages.length]);

  const handleWelcomeSend = () => {
    const msg = welcomeInput.trim();
    if (!msg) return;
    setWelcomeInput('');
    handleSendWithSession(msg);
  };

  const handleChatSend = () => {
    const msg = chatInput.trim();
    if (!msg) return;
    setChatInput('');
    handleSendWithSession(msg);
  };

  const hasMessages = messages.length > 0;

  return (
    <>
      <Sidebar
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
        onNewChat={handleNewChat}
        currentSessionId={currentSessionId}
        sessions={sessions}
        onSessionSwitch={handleSwitchSession}
        onSessionDelete={handleDeleteSession}
      />

      <main className="main-content">
        {!hasMessages ? (
          <WelcomePage
            inputValue={welcomeInput}
            onInputChange={setWelcomeInput}
            onSend={handleWelcomeSend}
          />
        ) : (
          <ChatContainer
            messages={messages}
            streamingContent={streamingContent}
            isStreaming={isStreaming}
            inputValue={chatInput}
            onInputChange={setChatInput}
            onSend={handleChatSend}
            onStop={handleStop}
            onCopy={handleCopy}
            onRegenerate={handleRegenerate}
            onEdit={handleEditMessage}
          />
        )}
      </main>

      {toast && <div className="copy-toast show">{toast}</div>}
    </>
  );
}

export default App;
