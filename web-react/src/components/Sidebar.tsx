import React, { useState } from 'react';
import type { AppView, Session } from '../types';
import ConfirmDialog from './ConfirmDialog';

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

      <aside className={`sidebar ${collapsed ? 'collapsed' : ''}`}>
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

          <div className="primary-view-nav" aria-label="主要功能">
            <button
              className={`primary-view-btn ${activeView === 'chat' ? 'active' : ''}`}
              onClick={() => onViewChange('chat')}
            >
              聊天
            </button>
            <button
              className={`primary-view-btn ${activeView === 'reports' ? 'active' : ''}`}
              onClick={() => onViewChange('reports')}
            >
              日报
            </button>
          </div>

          <nav className="sidebar-menu">
            <div className="menu-section-title">对话</div>
            {sessions.map((session) => (
              <div
                key={session.id}
                className={`menu-item session-item ${session.id === currentSessionId ? 'active' : ''}`}
                onClick={() => onSessionSwitch(session.id)}
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
    </>
  );
};

export default Sidebar;
