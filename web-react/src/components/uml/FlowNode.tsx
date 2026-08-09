import { memo, useEffect, useRef, useState } from 'react';
import { Handle, Position, NodeResizer, type NodeProps } from '@xyflow/react';
import type { FlowShape, NodeStyle } from './mermaidParser';

export type FlowNodeData = {
  label: string;
  shape: FlowShape;
  direction: 'TD' | 'LR' | 'BT' | 'RL';
  style?: NodeStyle;
  onLabelChange: (id: string, label: string) => void;
  onResize?: (id: string, width: number, height: number) => void;
  onResizeEnd?: (id: string) => void;
};

const SHAPE_CLASS: Record<FlowShape, string> = {
  rect: 'fl-n-rect',
  round: 'fl-n-round',
  diamond: 'fl-n-diamond',
  circle: 'fl-n-circle',
  subroutine: 'fl-n-sub',
  cylinder: 'fl-n-cyl',
  parallelogram: 'fl-n-para',
  note: 'fl-n-note',
  actor: 'fl-n-actor',
};

function FlowNode({ id, data, selected }: NodeProps) {
  const { label, shape, direction, style, onLabelChange, onResize, onResizeEnd } = data as FlowNodeData;
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(label);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (editing) {
      setDraft(label);
      setTimeout(() => {
        inputRef.current?.focus();
        inputRef.current?.select();
      }, 0);
    }
  }, [editing, label]);

  const commit = () => {
    const v = draft.trim();
    if (v && v !== label) onLabelChange(id, v);
    setEditing(false);
  };

  const vertical = direction === 'TD' || direction === 'BT';

  return (
    <div
      className={`flow-node ${SHAPE_CLASS[shape] || 'fl-n-rect'} ${selected ? 'selected' : ''}`}
      style={{
        background: style?.fill || undefined,
        borderColor: style?.border || undefined,
        color: style?.textColor || undefined,
        fontSize: style?.fontSize || undefined,
        borderStyle: style?.borderStyle || undefined,
        width: style?.width ? `${style.width}px` : undefined,
        height: style?.height ? `${style.height}px` : undefined,
      }}
      onDoubleClick={() => setEditing(true)}
    >
      <NodeResizer
        color="#7a5bcf"
        isVisible={selected}
        minWidth={64}
        minHeight={36}
        onResize={(_e, params) => {
          if (typeof params.width === 'number' && typeof params.height === 'number') {
            onResize?.(id, params.width, params.height);
          }
        }}
        onResizeEnd={() => onResizeEnd?.(id)}
      />
      {editing ? (
        <input
          ref={inputRef}
          className="flow-node-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === 'Enter') commit();
            if (e.key === 'Escape') setEditing(false);
          }}
        />
      ) : (
        <span className="flow-node-label">{label}</span>
      )}
      {vertical ? (
        <>
          <Handle type="target" position={Position.Top} />
          <Handle type="source" position={Position.Bottom} />
        </>
      ) : (
        <>
          <Handle type="target" position={Position.Left} />
          <Handle type="source" position={Position.Right} />
        </>
      )}
    </div>
  );
}

export default memo(FlowNode);
