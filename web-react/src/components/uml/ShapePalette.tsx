import type { FlowShape } from './mermaidParser';
import { SHAPE_NAMES } from './mermaidParser';

const SHAPES: FlowShape[] = [
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

function ShapeIcon({ shape }: { shape: FlowShape }) {
  const p = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.5 };
  switch (shape) {
    case 'rect':
      return (
        <svg width="22" height="22" viewBox="0 0 24 24" {...p}>
          <rect x="4" y="7" width="16" height="10" rx="1.5" />
        </svg>
      );
    case 'round':
      return (
        <svg width="22" height="22" viewBox="0 0 24 24" {...p}>
          <rect x="4" y="7" width="16" height="10" rx="5" />
        </svg>
      );
    case 'diamond':
      return (
        <svg width="22" height="22" viewBox="0 0 24 24" {...p}>
          <path d="M12 4 20 12 12 20 4 12Z" />
        </svg>
      );
    case 'circle':
      return (
        <svg width="22" height="22" viewBox="0 0 24 24" {...p}>
          <ellipse cx="12" cy="12" rx="8" ry="5.5" />
        </svg>
      );
    case 'parallelogram':
      return (
        <svg width="22" height="22" viewBox="0 0 24 24" {...p}>
          <path d="M6.5 7h13L17.5 17h-13Z" />
        </svg>
      );
    case 'subroutine':
      return (
        <svg width="22" height="22" viewBox="0 0 24 24" {...p}>
          <rect x="4" y="7" width="16" height="10" rx="1.5" />
          <path d="M7.5 7v10M16.5 7v10" />
        </svg>
      );
    case 'cylinder':
      return (
        <svg width="22" height="22" viewBox="0 0 24 24" {...p}>
          <ellipse cx="12" cy="8" rx="7" ry="2.8" />
          <path d="M5 8v8c0 1.6 3.1 2.8 7 2.8s7-1.2 7-2.8V8" />
        </svg>
      );
    case 'note':
      return (
        <svg width="22" height="22" viewBox="0 0 24 24" {...p}>
          <path d="M5 4h14v12l-4 4H5z" />
          <path d="M15 20v-4h4" />
        </svg>
      );
    case 'actor':
      return (
        <svg width="22" height="22" viewBox="0 0 24 24" {...p}>
          <circle cx="12" cy="6.5" r="2.5" />
          <path d="M5 20c0-3.9 3.1-6.2 7-6.2s7 2.3 7 6.2" />
        </svg>
      );
  }
}

interface ShapePaletteProps {
  onAdd: (shape: FlowShape) => void;
}

export default function ShapePalette({ onAdd }: ShapePaletteProps) {
  return (
    <div className="sp-panel">
      <div className="sp-title">形状库</div>
      <div className="sp-list">
        {SHAPES.map((s) => (
          <div
            key={s}
            className="sp-item"
            draggable
            onDragStart={(e) => {
              e.dataTransfer.setData('application/flow-shape', s);
              e.dataTransfer.effectAllowed = 'move';
            }}
            onClick={() => onAdd(s)}
            title={`${SHAPE_NAMES[s]} · 点击添加或拖入画布`}
          >
            <span className="sp-icon">
              <ShapeIcon shape={s} />
            </span>
            <span className="sp-name">{SHAPE_NAMES[s]}</span>
          </div>
        ))}
      </div>
      <div className="sp-tip">点击添加 · 拖入画布</div>
    </div>
  );
}
