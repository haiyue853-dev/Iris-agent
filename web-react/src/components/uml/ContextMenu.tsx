import type { FlowShape } from './mermaidParser';

export type CtxMenuState = {
  target: 'node' | 'edge' | 'pane';
  id: string | null;
  x: number;
  y: number;
} | null;

export interface CtxMenuAction {
  label: string;
  danger?: boolean;
  onClick: () => void;
}

interface ContextMenuProps {
  state: CtxMenuState;
  actions: CtxMenuAction[];
  onClose: () => void;
}

/** 画布右键菜单（draw.io 风格），带点击外部关闭遮罩 */
export default function ContextMenu({ state, actions, onClose }: ContextMenuProps) {
  if (!state) return null;
  return (
    <>
      <div className="fl-ctx-mask" onClick={onClose} />
      <div className="fl-ctx" style={{ left: state.x, top: state.y }} onClick={onClose}>
        {actions.map((a) => (
          <button
            key={a.label}
            className={`fl-ctx-item ${a.danger ? 'danger' : ''}`}
            onClick={(e) => {
              e.stopPropagation();
              a.onClick();
              onClose();
            }}
          >
            {a.label}
          </button>
        ))}
      </div>
    </>
  );
}

export type { FlowShape };
