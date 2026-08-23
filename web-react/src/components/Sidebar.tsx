import React, { useState } from 'react';
import type { Session } from '../types';
import type { AppView } from '../App';
import ConfirmDialog from './ConfirmDialog';
import SettingsModal from './settings/SettingsModal';

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
  onNewChat: () => void;
  currentSessionId: string;
  sessions: Session[];
  onSessionSwitch: (sessionId: string) => void;
  onSessionDelete: (sessionId: string) => void;
  activeView: AppView;
  onViewChange: (view: AppView) => void;
}

const Sidebar: React.FC<SidebarProps> = ({
  collapsed,
  onToggle,
  onNewChat,
  currentSessionId,
  sessions,
  onSessionSwitch,
  onSessionDelete,
  activeView,
  onViewChange,
}) => {
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const handleDeleteRequest = (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    setDeleteTarget(sessionId);
  };

  const handleDeleteConfirm = () => {
    if (deleteTarget) {
      onSessionDelete(deleteTarget);
    }
    setDeleteTarget(null);
  };

  const formatTime = (ts: number) => {
    const now = Date.now() / 1000;
    const diff = now - ts;
    if (diff < 60) return '刚刚';
    if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
    if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
    if (diff < 172800) return '昨天';
    const d = new Date(ts * 1000);
    return `${d.getMonth() + 1}/${d.getDate()}`;
  };

  return (
    <>
      {/* Expand button when collapsed */}
      {collapsed && (
        <button className="sidebar-expand-btn" onClick={onToggle} title="展开侧边栏">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="3" />
            <path d="M15 3v18" />
            <path d="M9 9l3 3-3 3" />
          </svg>
        </button>
      )}

      <aside className={`sidebar iris-sidebar ${collapsed ? 'collapsed' : ''}`} data-collapsed={collapsed}>
        <div className="sidebar-inner">
          <div className="sidebar-header">
            <div className="sidebar-logo">Iris</div>
            <button className="sidebar-toggle" onClick={onToggle} title="收起侧边栏">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="3" width="18" height="18" rx="3" />
                <path d="M9 3v18" />
                <path d="M15 9l-3 3 3 3" />
              </svg>
            </button>
          </div>

          <button className="new-chat-btn" onClick={onNewChat}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 5v14M5 12h14" />
            </svg>
            <span className="btn-text">新建会话</span>
            <span className="shortcut">Ctrl K</span>
          </button>

          <nav className="sidebar-view-nav iris-primary-nav" aria-label="功能导航">
            <div
              className={`view-item ${activeView === 'chat' ? 'active' : ''}`}
              onClick={() => onViewChange('chat')}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
              </svg>
              <span className="view-label">聊天</span>
            </div>
            <button
              type="button"
              className={`view-item report-view-item ${activeView === 'reports' ? 'active' : ''}`}
              onClick={() => onViewChange('reports')}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M6 3h9l3 3v15H6z" />
                <path d="M15 3v4h4M9 12h6M9 16h4" />
              </svg>
              <span className="view-label">AI 日报</span>
            </button>
            <div
              className={`view-item ${activeView === 'aihot' ? 'active' : ''}`}
              onClick={() => onViewChange('aihot')}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16a2 2 0 0 1-4 0V9" />
                <path d="M18 14h-8" />
                <path d="M15 18h-5" />
                <path d="M10 6h8v4h-8V6z" />
              </svg>
              <span className="view-label">每日资讯</span>
            </div>
            <div
              className={`view-item ${activeView === 'uml' ? 'active' : ''}`}
              onClick={() => onViewChange('uml')}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="3" width="7" height="7" rx="1.5" />
                <rect x="14" y="3" width="7" height="7" rx="1.5" />
                <rect x="3" y="14" width="7" height="7" rx="1.5" />
                <rect x="14" y="14" width="7" height="7" rx="1.5" />
                <path d="M10 6.5h4M6.5 10v4M17.5 10v4M10 17.5h4" />
              </svg>
              <span className="view-label">流程图</span>
            </div>
            <button
              type="button"
              className={`view-item ${activeView === 'skills' ? 'active' : ''}`}
              onClick={() => onViewChange('skills')}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M4 20h16" />
                <path d="M6 20V9l6-5 6 5v11" />
                <path d="M9 20v-6h6v6" />
              </svg>
              <span className="view-label">Skills</span>
            </button>
            <button type="button" className={`view-item ${activeView === 'automation' ? 'active' : ''}`} onClick={() => onViewChange('automation')}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="12" cy="12" r="8" /><path d="M12 7v5l3 2" /></svg>
              <span className="view-label">自动化任务</span>
            </button>
            <button type="button" className={`view-item ${activeView === 'tasks' ? 'active' : ''}`} onClick={() => onViewChange('tasks')}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M5 4h14v16H5zM8 8h8M8 12h8M8 16h5" /></svg>
              <span className="view-label">任务中心</span>
            </button>
            <button type="button" className={`view-item ${activeView === 'memory' ? 'active' : ''}`} onClick={() => onViewChange('memory')}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3a3 3 0 0 0-3 3 3 3 0 0 0-2.4 5A3 3 0 0 0 9 16a3 3 0 0 0 6 0 3 3 0 0 0 2.4-5A3 3 0 0 0 15 6a3 3 0 0 0-3-3z" /><path d="M12 8v4l2.5 1.5" /></svg>
              <span className="view-label">记忆</span>
            </button>
            <button type="button" className={`view-item ${activeView === 'knowledge' ? 'active' : ''}`} onClick={() => onViewChange('knowledge')}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" /><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" /></svg>
              <span className="view-label">知识库</span>
            </button>
            <button type="button" className={`view-item ${activeView === 'curator' ? 'active' : ''}`} onClick={() => onViewChange('curator')}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3l7 4v5c0 4.4-3 7.6-7 9-4-1.4-7-4.6-7-9V7z" /><path d="M9 12l2 2 4-4" /></svg>
              <span className="view-label">审查</span>
            </button>
            <button type="button" className={`view-item ${activeView === 'mcp' ? 'active' : ''}`} onClick={() => onViewChange('mcp')}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M8 3v4m8-4v4M6 7h12v14H6zM9 11h6m-6 4h6" /></svg>
              <span className="view-label">MCP</span>
            </button>
          </nav>

          <nav className="sidebar-menu iris-session-nav" aria-label="历史对话">
            <div className="menu-section-title">对话</div>
            {sessions.map((session) => (
              <div
                key={session.id}
                className={`menu-item session-item ${session.id === currentSessionId ? 'active' : ''}`}
                onClick={() => {
                  onViewChange('chat');
                  onSessionSwitch(session.id);
                }}
                onMouseEnter={() => setHoveredId(session.id)}
                onMouseLeave={() => setHoveredId(null)}
              >
                <svg className="icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
                </svg>
                <span className="session-name">{session.name}</span>
                <span className="session-time">{formatTime(session.updated_at)}</span>
                {hoveredId === session.id && (
                  <button
                    className="session-delete-btn"
                    onClick={(e) => handleDeleteRequest(e, session.id)}
                    title="删除"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                    </svg>
                  </button>
                )}
              </div>
            ))}
          </nav>

          <div className="sidebar-footer">
            <button className="sidebar-settings-btn" onClick={() => setSettingsOpen(true)} title="设置">
              <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="3" />
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
              </svg>
              <span className="btn-text">设置</span>
            </button>
          </div>
        </div>
      </aside>

      {deleteTarget && (
        <ConfirmDialog
          title="确认删除"
          message="确定要删除这个会话吗？删除后无法恢复。"
          onConfirm={handleDeleteConfirm}
          onCancel={() => setDeleteTarget(null)}
        />
      )}

      {settingsOpen && <SettingsModal onClose={() => setSettingsOpen(false)} />}
    </>
  );
};

export default Sidebar;
