// Iris 业务侧边栏 —— 组合 components/ui/sidebar.tsx 原语
// 行为完全兼容旧 Sidebar.tsx, 但采用 shadcn 风格组合式 API + 300ms 缓动动画

import { useEffect, useState } from "react";
import type { CSSProperties } from "react";

import type { Session } from "../types";
import type { AppView } from "../App";
import ConfirmDialog from "./ConfirmDialog";
import SettingsModal from "./settings/SettingsModal";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarRail,
} from "./ui/sidebar";
import {
  BookIcon,
  BrainIcon,
  ChatIcon,
  ChannelsIcon,
  ClockIcon,
  DocumentIcon,
  DotsIcon,
  GridIcon,
  HomeIcon,
  NewspaperIcon,
  PlusIcon,
  ServerIcon,
  SettingsIcon,
  ShieldCheckIcon,
  SkillIcon,
  ToolIcon,
  TrashIcon,
} from "./sidebar-icons";

interface AppSidebarProps {
  /** 是否默认展开 (内部走 localStorage 持久化) */
  defaultOpen?: boolean;
  /** 受控: 强制指定 open 状态 */
  open?: boolean;
  /** 受控: open 变化回调 */
  onOpenChange?: (open: boolean) => void;
  onNewChat: () => void;
  currentSessionId: string;
  sessions: Session[];
  onSessionSwitch: (sessionId: string) => void;
  onSessionDelete: (sessionId: string) => void;
  activeView: AppView;
  onViewChange: (view: AppView) => void;
}

interface PrimaryItem {
  key: AppView;
  label: string;
  icon: (props: { className?: string }) => React.ReactElement;
  tooltip: string;
}

const PRIMARY_ITEMS: PrimaryItem[] = [
  { key: "chat", label: "聊天", icon: ChatIcon, tooltip: "聊天" },
  { key: "reports", label: "AI 日报", icon: DocumentIcon, tooltip: "AI 日报" },
  { key: "aihot", label: "每日资讯", icon: NewspaperIcon, tooltip: "每日资讯" },
  { key: "uml", label: "流程图", icon: GridIcon, tooltip: "流程图" },
  { key: "skills", label: "Skills", icon: SkillIcon, tooltip: "Skills" },
  { key: "automation", label: "自动化任务", icon: ClockIcon, tooltip: "自动化任务" },
];

interface MoreToolItem {
  key: AppView;
  label: string;
  icon: (props: { className?: string }) => React.ReactElement;
  tooltip: string;
}

const MORE_TOOL_ITEMS: MoreToolItem[] = [
  { key: "tools", label: "工具", icon: ToolIcon, tooltip: "工具" },
  { key: "tasks", label: "任务中心", icon: (p) => <ListIcon className={p.className} />, tooltip: "任务中心" },
  { key: "memory", label: "记忆", icon: BrainIcon, tooltip: "记忆" },
  { key: "knowledge", label: "知识库", icon: BookIcon, tooltip: "知识库" },
  { key: "curator", label: "审查", icon: ShieldCheckIcon, tooltip: "审查" },
  { key: "mcp", label: "MCP", icon: ServerIcon, tooltip: "MCP" },
  { key: "channels", label: "消息渠道", icon: ChannelsIcon, tooltip: "消息渠道" },
];

const SECONDARY_VIEWS: AppView[] = ["tools", "tasks", "memory", "knowledge", "curator", "mcp", "channels"];
const MORE_TOOLS_KEY = "iris_more_tools_expanded";

// 内联占位图标 (More Tools 中复用)
function ListIcon({ className }: { className?: string }) {
  return (
    <svg className={className} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M5 4h14v16H5zM8 8h8M8 12h8M8 16h5" />
    </svg>
  );
}

function formatTime(ts: number): string {
  const now = Date.now() / 1000;
  const diff = now - ts;
  if (diff < 60) return "刚刚";
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
  if (diff < 172800) return "昨天";
  const d = new Date(ts * 1000);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

export function AppSidebar({
  defaultOpen,
  open,
  onOpenChange,
  onNewChat,
  currentSessionId,
  sessions,
  onSessionSwitch,
  onSessionDelete,
  activeView,
  onViewChange,
}: AppSidebarProps) {
  const isSecondaryView = SECONDARY_VIEWS.includes(activeView);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [moreToolsExpanded, setMoreToolsExpanded] = useState<boolean>(() => {
    if (typeof window === "undefined") return isSecondaryView;
    return isSecondaryView || localStorage.getItem(MORE_TOOLS_KEY) === "true";
  });

  useEffect(() => {
    if (isSecondaryView) setMoreToolsExpanded(true);
  }, [isSecondaryView]);

  const toggleMoreTools = () => {
    setMoreToolsExpanded((expanded) => {
      const next = !expanded;
      try {
        localStorage.setItem(MORE_TOOLS_KEY, String(next));
      } catch {
        /* 忽略 */
      }
      return next;
    });
  };

  const handleDeleteRequest = (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    setDeleteTarget(sessionId);
  };

  const handleDeleteConfirm = () => {
    if (deleteTarget) onSessionDelete(deleteTarget);
    setDeleteTarget(null);
  };

  // provider props: 受控 vs 非受控
  const providerProps: { defaultOpen?: boolean; open?: boolean; onOpenChange?: (v: boolean) => void } = {};
  if (open !== undefined) providerProps.open = open;
  else if (defaultOpen !== undefined) providerProps.defaultOpen = defaultOpen;
  if (onOpenChange) providerProps.onOpenChange = onOpenChange;

  return (
    <SidebarProvider {...providerProps}>
      <Sidebar>
        <SidebarHeader>
          <div className="flex items-center justify-center" style={{ minHeight: 32 }}>
            <button
              type="button"
              data-slot="sidebar-home"
              data-active={activeView === "chat" ? "true" : undefined}
              onClick={() => onViewChange("chat")}
              aria-label="返回首页"
              title="首页"
              className="flex shrink-0 items-center justify-center gap-2 rounded-md p-1.5 text-left transition-colors hover:bg-[var(--sidebar-accent)] hover:text-[var(--sidebar-accent-foreground)]"
            >
              <HomeIcon className="sidebar-icon shrink-0" size={18} />
              <span className="sidebar-label text-base font-semibold tracking-tight">Iris</span>
            </button>
          </div>
        </SidebarHeader>

        <SidebarContent>
          {/* 新建会话 */}
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton onClick={onNewChat} tooltip="新建会话" shortcut="Ctrl K">
                <PlusIcon className="sidebar-icon" size={16} />
                <span className="sidebar-label">新建会话</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>

          {/* 主要功能导航 */}
          <nav aria-label="功能导航">
            <SidebarGroup>
              <SidebarGroupLabel className="sidebar-label">WORKSPACE</SidebarGroupLabel>
              <SidebarMenu>
                {PRIMARY_ITEMS.map((item) => {
                  const Icon = item.icon;
                  return (
                    <SidebarMenuItem key={item.key}>
                      <SidebarMenuButton
                        isActive={activeView === item.key}
                        onClick={() => onViewChange(item.key)}
                        tooltip={item.tooltip}
                      >
                        <Icon className="sidebar-icon" />
                        <span className="sidebar-label">{item.label}</span>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  );
                })}

                {/* 更多工具折叠触发 */}
                <SidebarMenuItem>
                  <SidebarMenuButton
                    onClick={toggleMoreTools}
                    aria-expanded={moreToolsExpanded}
                    aria-controls="sidebar-more-tools"
                    tooltip="更多工具"
                  >
                    <DotsIcon className="sidebar-icon" size={16} />
                    <span className="sidebar-label">更多工具</span>
                    <svg
                      className="sidebar-chevron ml-auto"
                      width="14"
                      height="14"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      aria-hidden
                      style={{
                        transform: moreToolsExpanded ? "rotate(90deg)" : undefined,
                        transition: "transform 200ms ease-out",
                      }}
                    >
                      <path d="m9 18 6-6-6-6" />
                    </svg>
                  </SidebarMenuButton>
                </SidebarMenuItem>

                {moreToolsExpanded &&
                  MORE_TOOL_ITEMS.map((item) => {
                    const Icon = item.icon;
                    return (
                      <SidebarMenuItem key={item.key} id="sidebar-more-tools">
                        <SidebarMenuButton
                          isActive={activeView === item.key}
                          onClick={() => onViewChange(item.key)}
                          tooltip={item.tooltip}
                        >
                          <Icon className="sidebar-icon" />
                          <span className="sidebar-label">{item.label}</span>
                        </SidebarMenuButton>
                      </SidebarMenuItem>
                    );
                  })}
              </SidebarMenu>
            </SidebarGroup>
          </nav>

          {/* 历史会话 */}
          <nav aria-label="历史对话">
            <SidebarGroupLabel className="sidebar-label">SESSIONS</SidebarGroupLabel>
            <SidebarGroup>
              <SidebarMenu>
                {sessions.map((session) => (
                  <SidebarMenuItem
                    key={session.id}
                    onMouseEnter={() => setHoveredId(session.id)}
                    onMouseLeave={() => setHoveredId(null)}
                  >
                    <SidebarMenuButton
                      isActive={session.id === currentSessionId}
                      onClick={() => {
                        onViewChange("chat");
                        onSessionSwitch(session.id);
                      }}
                      tooltip={session.name}
                    >
                      <ChatIcon className="sidebar-icon" size={16} />
                      <span className="sidebar-label flex-1 truncate">{session.name}</span>
                      <span className="sidebar-shortcut">{formatTime(session.updated_at)}</span>
                    </SidebarMenuButton>
                    <SidebarMenuAction
                      aria-label="删除会话"
                      title="删除"
                      onClick={(e) => handleDeleteRequest(e, session.id)}
                      style={{ opacity: hoveredId === session.id ? 1 : undefined } as CSSProperties}
                    >
                      <TrashIcon size={14} />
                    </SidebarMenuAction>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroup>
          </nav>
        </SidebarContent>

        <SidebarFooter>
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton onClick={() => setSettingsOpen(true)} tooltip="设置">
                <SettingsIcon className="sidebar-icon" size={16} />
                <span className="sidebar-label">设置</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarFooter>
        <SidebarRail />
      </Sidebar>

      {deleteTarget && (
        <ConfirmDialog
          title="确认删除"
          message="确定要删除这个会话吗？删除后无法恢复。"
          onConfirm={handleDeleteConfirm}
          onCancel={() => setDeleteTarget(null)}
        />
      )}

      {settingsOpen && <SettingsModal onClose={() => setSettingsOpen(false)} />}
    </SidebarProvider>
  );
}

export default AppSidebar;
