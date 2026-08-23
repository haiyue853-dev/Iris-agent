import { useCallback, useEffect, useState } from 'react';
import Sidebar from './components/Sidebar';
import { AssistantChat } from './components/AssistantChat';
import AihotDailyPage from './components/aihot/AihotDailyPage';
import UmlFlowPage from './components/uml/UmlFlowPage';
import DailyReportPage from './components/reports/DailyReportPage';
import SkillsPage from './components/skills/SkillsPage';
import McpPage from './components/mcp/McpPage';
import AutomationPage from './components/automation/AutomationPage';
import TaskCenterPage from './components/tasks/TaskCenterPage';
import MemoryPage from './components/memory/MemoryPage';
import KnowledgePage from './components/knowledge/KnowledgePage';
import CuratorPage from './components/curator/CuratorPage';
import { useChat } from './hooks/useChat';
import './App.css';

export type AppView = 'chat' | 'aihot' | 'uml' | 'reports' | 'skills' | 'automation' | 'radar' | 'mcp' | 'tasks' | 'memory' | 'knowledge' | 'curator';

const VALID_VIEWS: AppView[] = ['chat', 'aihot', 'uml', 'reports', 'skills', 'automation', 'radar', 'mcp', 'tasks', 'memory', 'knowledge', 'curator'];

function App() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(
    () => window.innerWidth <= 720,
  );
  const [activeView, setActiveView] = useState<AppView>(() => {
    const saved = localStorage.getItem('iris_active_view');
    return VALID_VIEWS.includes(saved as AppView) ? (saved as AppView) : 'chat';
  });
  const [umlVisited, setUmlVisited] = useState(() => activeView === 'uml');

  const {
    messages,
    toast,
    currentSessionId,
    sessions,
    handleSwitchSession,
    handleDeleteSession,
    handleNewChat,
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

  const handleNewChatFromSidebar = () => {
    setActiveView('chat');
    handleNewChat();
  };

  const handleSessionCreated = useCallback((id: string) => {
    void handleSwitchSession(id);
  }, [handleSwitchSession]);

  return (
    <div className="iris-app-shell">
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

      <main className="main-content iris-main-surface" aria-label={activeView === 'reports' ? 'AI 日报工作台' : activeView === 'skills' ? 'Skills 中心' : activeView === 'automation' ? '自动化任务' : undefined}>
        {umlVisited && (
          <div hidden={activeView !== 'uml'}>
            <UmlFlowPage />
          </div>
        )}
        {activeView === 'uml' ? null : activeView === 'tasks' ? (
          <TaskCenterPage selectedTaskId={null} />
        ) : activeView === 'memory' ? (
          <MemoryPage />
        ) : activeView === 'knowledge' ? (
          <KnowledgePage />
        ) : activeView === 'curator' ? (
          <CuratorPage />
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
        ) : (
          <AssistantChat
            key={currentSessionId || "__new__"}
            sessionId={currentSessionId}
            messages={messages}
            onSessionCreated={handleSessionCreated}
          />
        )}
      </main>

      {toast && <div className="copy-toast show">{toast}</div>}
    </div>
  );
}

export default App;
