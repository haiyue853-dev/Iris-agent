import type { FlowShape, NodeStyle } from './mermaidParser';
import { SHAPE_NAMES } from './mermaidParser';

const PRESET_COLORS = ['#ffffff', '#e8f0fe', '#e6f4ea', '#fef7e0', '#fce8e6', '#f3e8fd', '#e0f7fa', '#f2f2f3'];
const SHAPE_OPTIONS: FlowShape[] = [
  'rect',
  'round',
  'diamond',
  'circle',
  'parallelogram',
  'subroutine',
  'cylinder',
  'note',
  'actor',
];

export type NodePanelData = { id: string; label: string; shape: FlowShape; style?: NodeStyle };
export type EdgePanelData = {
  id: string;
  label?: string;
  lineStyle: 'solid' | 'dashed' | 'dotted';
  color: string;
  arrowType: 'closed' | 'open' | 'none';
  width: number;
};

interface PropertiesPanelProps {
  target: 'node' | 'edge' | null;
  node?: NodePanelData | null;
  edge?: EdgePanelData | null;
  onChangeNode: (patch: Partial<{ label: string; shape: FlowShape; style: NodeStyle }>) => void;
  onChangeEdge: (patch: Partial<{ label?: string; lineStyle: string; color: string; arrowType: 'closed' | 'open' | 'none'; width: number }>) => void;
  onDelete: () => void;
  onClose: () => void;
}

export default function PropertiesPanel({ target, node, edge, onChangeNode, onChangeEdge, onDelete, onClose }: PropertiesPanelProps) {
  return (
    <div className="pp-panel">
      <div className="pp-head">
        <span className="pp-title">{target === 'node' ? '节点属性' : '连线属性'}</span>
        <button className="pp-close" onClick={onClose} title="关闭面板">
          ×
        </button>
      </div>

      {target === 'node' && node && (
        <div className="pp-body">
          <label className="pp-field">
            <span className="pp-label">文字</span>
            <textarea
              className="pp-input pp-area"
              value={node.label}
              rows={2}
              onChange={(e) => onChangeNode({ label: e.target.value })}
            />
          </label>

          <label className="pp-field">
            <span className="pp-label">形状</span>
            <select className="pp-input" value={node.shape} onChange={(e) => onChangeNode({ shape: e.target.value as FlowShape })}>
              {SHAPE_OPTIONS.map((s) => (
                <option key={s} value={s}>
                  {SHAPE_NAMES[s]}
                </option>
              ))}
            </select>
          </label>

          <div className="pp-field">
            <span className="pp-label">填充色</span>
            <div className="pp-colors">
              {PRESET_COLORS.map((c) => (
                <button
                  key={c}
                  className={`pp-color ${(node.style?.fill || '#ffffff').toLowerCase() === c ? 'active' : ''}`}
                  style={{ background: c }}
                  onClick={() => onChangeNode({ style: { ...node.style, fill: c } })}
                  title={c}
                />
              ))}
              <input
                type="color"
                className="pp-color-picker"
                value={node.style?.fill || '#ffffff'}
                onChange={(e) => onChangeNode({ style: { ...node.style, fill: e.target.value } })}
                title="自定义颜色"
              />
            </div>
          </div>

          <label className="pp-field">
            <span className="pp-label">边框色</span>
            <input
              type="color"
              className="pp-color-picker"
              value={node.style?.border || '#d5d5dc'}
              onChange={(e) => onChangeNode({ style: { ...node.style, border: e.target.value } })}
            />
            <span className="pp-inline">
              文字色
              <input
                type="color"
                className="pp-color-picker"
                value={node.style?.textColor || '#1d1c23'}
                onChange={(e) => onChangeNode({ style: { ...node.style, textColor: e.target.value } })}
              />
            </span>
          </label>

          <label className="pp-field">
            <span className="pp-label">边框样式</span>
            <select
              className="pp-input"
              value={node.style?.borderStyle ?? 'solid'}
              onChange={(e) => onChangeNode({ style: { ...node.style, borderStyle: e.target.value as 'solid' | 'dashed' } })}
            >
              <option value="solid">实线</option>
              <option value="dashed">虚线</option>
            </select>
          </label>

          <label className="pp-field">
            <span className="pp-label">字号</span>
            <input
              type="number"
              className="pp-input pp-num"
              min={10}
              max={32}
              value={node.style?.fontSize ?? 13.5}
              onChange={(e) => onChangeNode({ style: { ...node.style, fontSize: Number(e.target.value) || 13.5 } })}
            />
            <span className="pp-unit">px</span>
          </label>
        </div>
      )}

      {target === 'edge' && edge && (
        <div className="pp-body">
          <label className="pp-field">
            <span className="pp-label">连线标签</span>
            <div className="pp-row">
              <input
                className="pp-input"
                value={edge.label ?? ''}
                placeholder="如：成功 / 失败（留空删除）"
                onChange={(e) => onChangeEdge({ label: e.target.value || undefined })}
              />
            </div>
          </label>

          <label className="pp-field">
            <span className="pp-label">线型</span>
            <select
              className="pp-input"
              value={edge.lineStyle}
              onChange={(e) => onChangeEdge({ lineStyle: e.target.value as 'solid' | 'dashed' | 'dotted' })}
            >
              <option value="solid">实线</option>
              <option value="dashed">虚线</option>
              <option value="dotted">点线</option>
            </select>
          </label>

          <div className="pp-field">
            <span className="pp-label">颜色</span>
            <div className="pp-colors">
              {PRESET_COLORS.slice(0, 7).map((c) => (
                <button
                  key={c}
                  className={`pp-color ${edge.color.toLowerCase() === c ? 'active' : ''}`}
                  style={{ background: c }}
                  onClick={() => onChangeEdge({ color: c })}
                />
              ))}
              <input
                type="color"
                className="pp-color-picker"
                value={edge.color}
                onChange={(e) => onChangeEdge({ color: e.target.value })}
              />
            </div>
          </div>

          <label className="pp-field pp-check-row">
            <span className="pp-label-inline">箭头</span>
            <select
              className="pp-input"
              value={edge.arrowType}
              onChange={(e) => onChangeEdge({ arrowType: e.target.value as 'closed' | 'open' | 'none' })}
            >
              <option value="closed">实心箭头</option>
              <option value="open">空心箭头</option>
              <option value="none">无箭头</option>
            </select>
          </label>

          <label className="pp-field">
            <span className="pp-label">线宽</span>
            <input
              type="number"
              className="pp-input pp-num"
              min={1}
              max={5}
              value={edge.width}
              onChange={(e) => onChangeEdge({ width: Number(e.target.value) || 1 })}
            />
            <span className="pp-unit">px</span>
          </label>
        </div>
      )}

      <div className="pp-foot">
        <button className="pp-delete" onClick={onDelete}>
          删除{target === 'node' ? '节点' : '连线'}
        </button>
      </div>
    </div>
  );
}
