import { useState, useEffect } from 'react';
import Sidebar from './components/Sidebar';
import WelcomePage from './components/WelcomePage';
import ChatContainer from './components/ChatContainer';
import AihotDailyPage from './components/aihot/AihotDailyPage';
import UmlFlowPage from './components/uml/UmlFlowPage';
import DailyReportPage from './components/reports/DailyReportPage';
import { useChat } from './hooks/useChat';
import './App.css';

export type AppView = 'chat' | 'aihot' | 'uml' | 'reports';

function App() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [welcomeInput, setWelcomeInput] = useState('');
  const [chatInput, setChatInput] = useState('');
  const [activeView, setActiveView] = useState<AppView>(() => {
    const saved = localStorage.getItem('iris_active_view');
    return saved === 'aihot' || saved === 'uml' || saved === 'reports' ? saved : 'chat';
  });

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

  useEffect(() => {
    localStorage.setItem('iris_active_view', activeView);
  }, [activeView]);

  // Ctrl+K shortcut
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        if (messages.length > 0) {
          if (confirm('确定要新建会话吗？')) {
            setActiveView('chat');
            handleNewChat();
          }
        } else {
          setActiveView('chat');
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

  const handleNewChatFromSidebar = () => {
    setActiveView('chat');
    handleNewChat();
  };

  const hasMessages = messages.length > 0;

  return (
    <>
      <Sidebar
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
        onNewChat={handleNewChatFromSidebar}
        currentSessionId={currentSessionId}
        sessions={sessions}
        onSessionSwitch={handleSwitchSession}
        onSessionDelete={handleDeleteSession}
        activeView={activeView}
        onViewChange={setActiveView}
      />

      <main className="main-content" aria-label={activeView === 'reports' ? 'AI 日报工作台' : undefined}>
        {activeView === 'reports' ? (
          <DailyReportPage currentSessionId={currentSessionId} />
        ) : activeView === 'aihot' ? (
          <AihotDailyPage />
        ) : activeView === 'uml' ? (
          <UmlFlowPage />
        ) : !hasMessages ? (
          <WelcomePage
            inputValue={welcomeInput}
            onInputChange={setWelcomeInput}
            onSend={handleWelcomeSend}
            onNavigate={setActiveView}
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
