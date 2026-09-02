// shadcn 风格 Sidebar primitives (单文件, 集中导出)
// 受 shadcn/ui aria-nova 实现的 API 启发, 适配 Iris-agent 业务
// 设计要点: data-slot + data-state 属性驱动 CSS 动效, 不依赖 framer-motion

"use client";

import * as React from "react";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import * as Tooltip from "@radix-ui/react-tooltip";

import { cn } from "@/lib/utils";

const SIDEBAR_KEYBOARD_SHORTCUT = "b";
const SIDEBAR_COOKIE_NAME = "iris_sidebar_open";

type SidebarState = "expanded" | "collapsed";

interface SidebarContextValue {
  state: SidebarState;
  open: boolean;
  setOpen: (open: boolean) => void;
  isMobile: boolean;
  openMobile: boolean;
  setOpenMobile: (open: boolean) => void;
  toggleSidebar: () => void;
}

const SidebarContext = createContext<SidebarContextValue | null>(null);

function useSidebar(): SidebarContextValue {
  const ctx = useContext(SidebarContext);
  if (!ctx) throw new Error("useSidebar must be used within a SidebarProvider");
  return ctx;
}

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

interface SidebarProviderProps {
  defaultOpen?: boolean;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  className?: string;
  style?: React.CSSProperties;
  children: React.ReactNode;
}

const SidebarProvider = React.forwardRef<HTMLDivElement, SidebarProviderProps>(
  ({ defaultOpen = true, open: openProp, onOpenChange, className, style, children }, ref) => {
    // 受控 / 非受控
    const [_open, _setOpen] = useState<boolean>(() => {
      if (typeof window !== "undefined") {
        const stored = localStorage.getItem(SIDEBAR_COOKIE_NAME);
        if (stored !== null) return stored === "true";
      }
      return defaultOpen;
    });
    const open = openProp ?? _open;

    const setOpen = useCallback(
      (value: boolean | ((value: boolean) => boolean)) => {
        const next = typeof value === "function" ? value(open) : value;
        if (onOpenChange) onOpenChange(next);
        else _setOpen(next);
        try {
          localStorage.setItem(SIDEBAR_COOKIE_NAME, String(next));
        } catch {
          /* localStorage 不可用时忽略 */
        }
      },
      [onOpenChange, open],
    );

    // 移动端 (本期固定 false, 预留 API)
    const isMobile = false;
    const [openMobile, setOpenMobile] = useState(false);

    const toggleSidebar = useCallback(() => {
      return isMobile ? setOpenMobile((v) => !v) : setOpen((v) => !v);
    }, [isMobile, setOpen]);

    // 键盘快捷键 Ctrl/Cmd + B
    useEffect(() => {
      const handler = (event: KeyboardEvent) => {
        if (
          event.key === SIDEBAR_KEYBOARD_SHORTCUT &&
          (event.metaKey || event.ctrlKey) &&
          !event.shiftKey &&
          !event.altKey
        ) {
          event.preventDefault();
          toggleSidebar();
        }
      };
      window.addEventListener("keydown", handler);
      return () => window.removeEventListener("keydown", handler);
    }, [toggleSidebar]);

    const state: SidebarState = open ? "expanded" : "collapsed";

    const value = useMemo<SidebarContextValue>(
      () => ({ state, open, setOpen, isMobile, openMobile, setOpenMobile, toggleSidebar }),
      [state, open, setOpen, isMobile, openMobile, toggleSidebar],
    );

    return (
      <SidebarContext.Provider value={value}>
        <Tooltip.Provider delayDuration={200} skipDelayDuration={300}>
          <div
            ref={ref}
            data-slot="sidebar-provider"
            style={style}
            className={cn("flex min-h-svh shrink-0", className)}
          >
            {children}
          </div>
        </Tooltip.Provider>
      </SidebarContext.Provider>
    );
  },
);
SidebarProvider.displayName = "SidebarProvider";

// ---------------------------------------------------------------------------
// Sidebar 外壳
// ---------------------------------------------------------------------------

interface SidebarProps extends React.ComponentProps<"div"> {
  side?: "left" | "right";
  variant?: "sidebar" | "floating" | "inset";
  collapsible?: "offcanvas" | "icon" | "none";
}

const Sidebar = React.forwardRef<HTMLDivElement, SidebarProps>(
  ({ side = "left", variant = "sidebar", collapsible = "icon", className, children, ...props }, ref) => {
    const { state } = useSidebar();

    if (collapsible === "none") {
      return (
        <div
          ref={ref}
          data-slot="sidebar"
          data-state={state}
          data-side={side}
          data-variant={variant}
          className={cn("h-screen", className)}
          {...props}
        >
          {children}
        </div>
      );
    }

    return (
      <div
        ref={ref}
        data-slot="sidebar"
        data-state={state}
        data-side={side}
        data-variant={variant}
        data-collapsible={state === "collapsed" ? collapsible : ""}
        className={cn(className)}
        {...props}
      >
        {children}
      </div>
    );
  },
);
Sidebar.displayName = "Sidebar";

// ---------------------------------------------------------------------------
// 基础分段 (Header / Content / Footer)
// ---------------------------------------------------------------------------

const SidebarHeader = React.forwardRef<HTMLDivElement, React.ComponentProps<"div">>(
  ({ className, ...props }, ref) => (
    <div ref={ref} data-slot="sidebar-header" className={className} {...props} />
  ),
);
SidebarHeader.displayName = "SidebarHeader";

const SidebarContent = React.forwardRef<HTMLDivElement, React.ComponentProps<"div">>(
  ({ className, ...props }, ref) => (
    <div ref={ref} data-slot="sidebar-content" className={className} {...props} />
  ),
);
SidebarContent.displayName = "SidebarContent";

const SidebarFooter = React.forwardRef<HTMLDivElement, React.ComponentProps<"div">>(
  ({ className, ...props }, ref) => (
    <div ref={ref} data-slot="sidebar-footer" className={className} {...props} />
  ),
);
SidebarFooter.displayName = "SidebarFooter";

// ---------------------------------------------------------------------------
// 分组
// ---------------------------------------------------------------------------

const SidebarGroup = React.forwardRef<HTMLDivElement, React.ComponentProps<"div">>(
  ({ className, ...props }, ref) => (
    <div ref={ref} data-slot="sidebar-group" className={className} {...props} />
  ),
);
SidebarGroup.displayName = "SidebarGroup";

const SidebarGroupLabel = React.forwardRef<HTMLDivElement, React.ComponentProps<"div">>(
  ({ className, ...props }, ref) => (
    <div ref={ref} data-slot="sidebar-group-label" className={className} {...props} />
  ),
);
SidebarGroupLabel.displayName = "SidebarGroupLabel";

// ---------------------------------------------------------------------------
// 菜单
// ---------------------------------------------------------------------------

const SidebarMenu = React.forwardRef<HTMLUListElement, React.ComponentProps<"ul">>(
  ({ className, ...props }, ref) => (
    <ul ref={ref} data-slot="sidebar-menu" className={className} {...props} />
  ),
);
SidebarMenu.displayName = "SidebarMenu";

const SidebarMenuItem = React.forwardRef<HTMLLIElement, React.ComponentProps<"li">>(
  ({ className, ...props }, ref) => (
    <li ref={ref} data-slot="sidebar-menu-item" className={className} {...props} />
  ),
);
SidebarMenuItem.displayName = "SidebarMenuItem";

interface SidebarMenuButtonProps extends React.ComponentProps<"button"> {
  asChild?: boolean;
  isActive?: boolean;
  tooltip?: string;
  shortcut?: string;
}

const SidebarMenuButton = React.forwardRef<HTMLButtonElement, SidebarMenuButtonProps>(
  ({ asChild = false, isActive = false, tooltip, shortcut, className, children, ...props }, ref) => {
    const { state } = useSidebar();

    const inner = (
      <button
        ref={ref}
        data-slot="sidebar-menu-button"
        data-active={isActive ? "true" : undefined}
        className={cn(className)}
        {...props}
      >
        {children}
        {shortcut ? <span className="sidebar-shortcut">{shortcut}</span> : null}
      </button>
    );

    const buttonNode = asChild ? inner : inner;

    if (!tooltip || state === "expanded") {
      return buttonNode;
    }

    return (
      <Tooltip.Root>
        <Tooltip.Trigger asChild>{buttonNode}</Tooltip.Trigger>
        <Tooltip.Portal>
          <Tooltip.Content
            side="right"
            align="center"
            sideOffset={6}
            className="z-50 rounded-md bg-zinc-900 px-2 py-1 text-xs text-zinc-50 shadow-md dark:bg-zinc-50 dark:text-zinc-900"
          >
            {tooltip}
          </Tooltip.Content>
        </Tooltip.Portal>
      </Tooltip.Root>
    );
  },
);
SidebarMenuButton.displayName = "SidebarMenuButton";

interface SidebarMenuActionProps extends React.ComponentProps<"button"> {
  asChild?: boolean;
}

const SidebarMenuAction = React.forwardRef<HTMLButtonElement, SidebarMenuActionProps>(
  ({ asChild = false, className, ...props }, ref) => (
    <button
      ref={ref}
      data-slot="sidebar-menu-action"
      className={cn(className)}
      {...props}
    />
  ),
);
SidebarMenuAction.displayName = "SidebarMenuAction";

// ---------------------------------------------------------------------------
// 切换按钮 (结合 chevron 方向)
// ---------------------------------------------------------------------------

interface SidebarTriggerProps extends React.ComponentProps<"button"> {
  children?: React.ReactNode;
}

const SidebarTrigger = React.forwardRef<HTMLButtonElement, SidebarTriggerProps>(
  ({ className, children, onClick, ...props }, ref) => {
    const { toggleSidebar, state } = useSidebar();
    return (
      <button
        ref={ref}
        type="button"
        data-slot="sidebar-trigger"
        aria-label="Toggle Sidebar"
        onClick={(event) => {
          onClick?.(event);
          if (!event.defaultPrevented) toggleSidebar();
        }}
        className={cn(className)}
        {...props}
      >
        {children ?? (
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
            style={{ transform: state === "collapsed" ? "rotate(180deg)" : undefined, transition: "transform 200ms ease-out" }}
          >
            <path d="m15 18-6-6 6-6" />
          </svg>
        )}
      </button>
    );
  },
);
SidebarTrigger.displayName = "SidebarTrigger";

// ---------------------------------------------------------------------------
// SidebarRail: 浮在侧边栏右边缘的圆形切换按钮 (shadcn 标准做法)
// 案例里 trigger 是浮在 sidebar 右边的圆形按钮,header 干净不挤
// ---------------------------------------------------------------------------

interface SidebarRailProps extends React.ComponentProps<"button"> {}

const SidebarRail = React.forwardRef<HTMLButtonElement, SidebarRailProps>(
  ({ className, ...props }, ref) => {
    const { toggleSidebar, state } = useSidebar();
    return (
      <button
        ref={ref}
        type="button"
        data-slot="sidebar-rail"
        aria-label="Toggle Sidebar"
        onClick={toggleSidebar}
        title={state === "expanded" ? "收起侧边栏" : "展开侧边栏"}
        className={cn(
          "absolute -right-3 top-1/2 z-30 -translate-y-1/2",
          "flex h-7 w-7 items-center justify-center rounded-full",
          "border border-[var(--sidebar-border)] bg-[var(--sidebar-background)]",
          "text-[var(--sidebar-foreground)] shadow-sm",
          "transition-all duration-200 ease-out",
          "hover:scale-110 hover:bg-[var(--sidebar-accent)] hover:text-[var(--sidebar-accent-foreground)]",
          className,
        )}
        {...props}
      >
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
          style={{
            transform: state === "collapsed" ? "rotate(180deg)" : undefined,
            transition: "transform 200ms ease-out",
          }}
        >
          <path d="m15 18-6-6 6-6" />
        </svg>
      </button>
    );
  },
);
SidebarRail.displayName = "SidebarRail";

// ---------------------------------------------------------------------------
// 导出
// ---------------------------------------------------------------------------

export {
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
  SidebarTrigger,
  useSidebar,
  type SidebarContextValue,
  type SidebarMenuButtonProps,
  type SidebarMenuActionProps,
  type SidebarProps,
  type SidebarProviderProps,
  type SidebarRailProps,
  type SidebarState,
  type SidebarTriggerProps,
};
