import { useCallback, useEffect, useState } from 'react';
import AppSidebar from './components/app-sidebar';
import { AssistantChat } from './components/AssistantChat';
import AihotDailyPage from './components/aihot/AihotDailyPage';
import UmlFlowPage from './components/uml/UmlFlowPage';
import DailyReportPage from './components/reports/DailyReportPage';
import SkillsPage from './components/skills/SkillsPage';
import type { UserSkillContent } from './api/skills';
import McpPage from './components/mcp/McpPage';
import AutomationPage from './components/automation/AutomationPage';
import TaskCenterPage from './components/tasks/TaskCenterPage';
import MemoryPage from './components/memory/MemoryPage';
import KnowledgePage from './components/knowledge/KnowledgePage';
import { listKnowledgeCollections, type KnowledgeCollection } from './api/knowledge';
import CuratorPage from './components/curator/CuratorPage';
import MessageChannelsPage from './components/channels/MessageChannelsPage';
import ToolsPage from './components/tools/ToolsPage';
import { useChat } from './hooks/useChat';
import './App.css';

export type AppView = 'chat' | 'aihot' | 'uml' | 'reports' | 'skills' | 'automation' | 'radar' | 'mcp' | 'tasks' | 'memory' | 'knowledge' | 'curator' | 'channels' | 'tools';

const VALID_VIEWS: AppView[] = ['chat', 'aihot', 'uml', 'reports', 'skills', 'automation', 'radar', 'mcp', 'tasks', 'memory', 'knowledge', 'curator', 'channels', 'tools'];

function App() {
  const [activeView, setActiveView] = useState<AppView>(() => {
    const saved = localStorage.getItem('iris_active_view');
    return VALID_VIEWS.includes(saved as AppView) ? (saved as AppView) : 'chat';
  });
  const [umlVisited, setUmlVisited] = useState(() => activeView === 'uml');
  const [knowledgeCollections, setKnowledgeCollections] = useState<KnowledgeCollection[]>([]);
  const [chatKnowledgeCollectionId, setChatKnowledgeCollectionId] = useState(() => localStorage.getItem('iris_chat_knowledge_collection') || '');
  const [chatUseKnowledge, setChatUseKnowledge] = useState(() => localStorage.getItem('iris_chat_use_knowledge') === 'true');
  const [chatKnowledgeQueryMode] = useState<'precise' | 'global' | 'mix'>(() => (localStorage.getItem('iris_chat_knowledge_mode') as 'precise' | 'global' | 'mix') || 'mix');
  const [knowledgeOpenDocumentId, setKnowledgeOpenDocumentId] = useState<string | null>(null);
  const [knowledgeOpenChunkId, setKnowledgeOpenChunkId] = useState<string | null>(null);
  const [activeSkill, setActiveSkill] = useState<UserSkillContent | null>(null);

  const {
    messages,
    toast,
    currentSessionId,
    sessions,
    handleSwitchSession,
    handleDeleteSession,
    handleNewChat,
    handleRefreshSession,
  } = useChat();

  useEffect(() => {
    localStorage.setItem('iris_active_view', activeView);
    if (activeView === 'uml') setUmlVisited(true);
  }, [activeView]);
  useEffect(() => { void listKnowledgeCollections().then(setKnowledgeCollections).catch(() => setKnowledgeCollections([])); }, []);
  useEffect(() => { window.dispatchEvent(new CustomEvent('iris:knowledge-collections', { detail: knowledgeCollections })); }, [knowledgeCollections]);
  useEffect(() => { localStorage.setItem('iris_chat_knowledge_collection', chatKnowledgeCollectionId); }, [chatKnowledgeCollectionId]);
  useEffect(() => { localStorage.setItem('iris_chat_use_knowledge', String(chatUseKnowledge)); window.dispatchEvent(new CustomEvent('iris:knowledge-state', { detail: { enabled: chatUseKnowledge } })); }, [chatUseKnowledge]);
  useEffect(() => { const toggle = () => setChatUseKnowledge((enabled) => !enabled); window.addEventListener('iris:toggle-knowledge', toggle); return () => window.removeEventListener('iris:toggle-knowledge', toggle); }, []);
  useEffect(() => { const choose = (event: Event) => { const id = (event as CustomEvent<{ id: string }>).detail?.id || ''; setChatKnowledgeCollectionId(id); setChatUseKnowledge(true); }; window.addEventListener('iris:select-knowledge', choose); return () => window.removeEventListener('iris:select-knowledge', choose); }, []);
  useEffect(() => { const disable = () => setChatUseKnowledge(false); window.addEventListener('iris:disable-knowledge', disable); return () => window.removeEventListener('iris:disable-knowledge', disable); }, []);
  useEffect(() => { localStorage.setItem('iris_chat_knowledge_mode', chatKnowledgeQueryMode); }, [chatKnowledgeQueryMode]);
  useEffect(() => {
    const openKnowledge = (event: Event) => {
      const { documentId, chunkId } = (event as CustomEvent<{ documentId?: string; chunkId?: string }>).detail || {};
      if (documentId) { setKnowledgeOpenDocumentId(documentId); setKnowledgeOpenChunkId(chunkId || null); setActiveView('knowledge'); }
    };
    window.addEventListener('iris:open-knowledge', openKnowledge);
    return () => window.removeEventListener('iris:open-knowledge', openKnowledge);
  }, []);

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
      <AppSidebar
        onNewChat={handleNewChatFromSidebar}
        currentSessionId={currentSessionId}
        sessions={sessions}
        onSessionSwitch={handleSwitchSession}
        onSessionDelete={handleDeleteSession}
        activeView={activeView}
        onViewChange={setActiveView}
      />

      <main className={`main-content iris-main-surface ${activeView === 'channels' ? 'channels-main' : ''}`} aria-label={activeView === 'reports' ? 'AI 日报工作台' : activeView === 'skills' ? 'Skills 中心' : activeView === 'automation' ? '自动化任务' : undefined}>
        {umlVisited && (
          <div className="view-shell" hidden={activeView !== 'uml'}>
            <UmlFlowPage />
          </div>
        )}
        {activeView === 'uml' ? null : activeView === 'tasks' ? (
          <TaskCenterPage selectedTaskId={null} />
        ) : activeView === 'memory' ? (
          <MemoryPage />
        ) : activeView === 'knowledge' ? (
          <KnowledgePage openDocumentId={knowledgeOpenDocumentId} openChunkId={knowledgeOpenChunkId} />
        ) : activeView === 'curator' ? (
          <CuratorPage />
        ) : activeView === 'channels' ? (
          <MessageChannelsPage />
        ) : activeView === 'tools' ? (
          <ToolsPage />
        ) : activeView === 'reports' ? (
          <DailyReportPage currentSessionId={currentSessionId} />
        ) : activeView === 'skills' ? (
          <SkillsPage onNavigate={setActiveView} onActivateSkill={(skill) => { handleNewChat(); setActiveSkill(skill); }} />
        ) : activeView === 'mcp' ? (
          <McpPage />
        ) : activeView === 'automation' || activeView === 'radar' ? (
          <AutomationPage />
        ) : activeView === 'aihot' ? (
          <AihotDailyPage />
        ) : (
          <><AssistantChat
            key={currentSessionId || "__new__"}
            sessionId={currentSessionId}
            sessionModelProfileId={sessions.find((item) => item.id === currentSessionId)?.model_profile_id}
            messages={messages}
            knowledgeCollectionId={chatKnowledgeCollectionId}
            knowledgeQueryMode={chatKnowledgeQueryMode}
            useKnowledge={chatUseKnowledge}
            initialSkill={activeSkill}
            onSkillUsed={() => setActiveSkill(null)}
            onSessionCreated={handleSessionCreated}
            onSessionRefreshed={handleRefreshSession}
          /></>
        )}
      </main>

      {toast && <div className="copy-toast show">{toast}</div>}
    </div>
  );
}

export default App;
