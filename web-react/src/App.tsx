import { useState, useEffect } from 'react';
import Sidebar from './components/Sidebar';
import WelcomePage from './components/WelcomePage';
import ChatContainer from './components/ChatContainer';
import AihotDailyPage from './components/aihot/AihotDailyPage';
import UmlFlowPage from './components/uml/UmlFlowPage';
import DailyReportPage from './components/reports/DailyReportPage';
import SkillsPage from './components/skills/SkillsPage';
import McpPage from './components/mcp/McpPage';
import AutomationPage from './components/automation/AutomationPage';
import TaskCenterPage from './components/tasks/TaskCenterPage';
import { useChat } from './hooks/useChat';
import './App.css';

export type AppView = 'chat' | 'aihot' | 'uml' | 'reports' | 'skills' | 'automation' | 'radar' | 'mcp' | 'tasks';

const VALID_VIEWS: AppView[] = ['chat', 'aihot', 'uml', 'reports', 'skills', 'automation', 'radar', 'mcp', 'tasks'];

function App() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [welcomeInput, setWelcomeInput] = useState('');
  const [chatInput, setChatInput] = useState('');
  const [activeView, setActiveView] = useState<AppView>(() => {
    const saved = localStorage.getItem('iris_active_view');
    return VALID_VIEWS.includes(saved as AppView) ? (saved as AppView) : 'chat';
  });
  const [umlVisited, setUmlVisited] = useState(() => activeView === 'uml');
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);

  const {
    messages,
    isStreaming,
    streamingContent,
    toast,
    pendingApproval,
    currentSessionId,
    currentTaskId,
    currentTaskStatus,
    queuePosition,
    approvalCallId,
    sessions,
    handleSendWithSession,
    resolvePendingApproval,
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
    if (activeView === 'uml') setUmlVisited(true);
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

      <main className="main-content" aria-label={activeView === 'reports' ? 'AI 日报工作台' : activeView === 'skills' ? 'Skills 中心' : activeView === 'automation' ? '自动化任务' : undefined}>
        {umlVisited && (
          <div hidden={activeView !== 'uml'}>
            <UmlFlowPage />
          </div>
        )}
        {activeView === 'uml' ? null : activeView === 'tasks' ? (
          <TaskCenterPage selectedTaskId={selectedTaskId} />
        ) : activeView === 'reports' ? (
          <DailyReportPage currentSessionId={currentSessionId} />
        ) : activeView === 'skills' ? (
          <SkillsPage onNavigate={setActiveView} />
        ) : activeView === 'mcp' ? (
          <McpPage />
        ) : activeView === 'automation' || activeView === 'radar' ? (
          <AutomationPage />
        ) : activeView === 'aihot' ? (
          <AihotDailyPage />
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
            pendingApproval={pendingApproval}
            onApproveTool={(callId) => void resolvePendingApproval(callId, true)}
            onRejectTool={(callId) => void resolvePendingApproval(callId, false)}
            currentTaskId={currentTaskId}
            currentTaskStatus={currentTaskStatus}
            queuePosition={queuePosition}
            approvalCallId={approvalCallId}
            onViewTask={(taskId) => { setSelectedTaskId(taskId); setActiveView('tasks'); }}
          />
        )}
      </main>

      {toast && <div className="copy-toast show">{toast}</div>}
    </>
  );
}

export default App;
