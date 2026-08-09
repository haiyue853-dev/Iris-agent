import { memo } from 'react';
import { Handle, Position, NodeResizer, type NodeProps } from '@xyflow/react';

export type FlowImageNodeData = {
  src: string;
  width: number;
  height: number;
  onResize?: (id: string, w: number, h: number) => void;
  onResizeEnd?: (id: string) => void;
};

/** 图片节点（拖入本地图片文件创建，draw.io 风格） */
function FlowImageNode({ id, data, selected }: NodeProps) {
  const { src, width, height, onResize, onResizeEnd } = data as FlowImageNodeData;
  return (
    <div
      className={`flow-image-node ${selected ? 'selected' : ''}`}
      style={{ width, height }}
      onDoubleClick={(e) => e.stopPropagation()}
    >
      <NodeResizer
        color="#7a5bcf"
        isVisible={selected}
        minWidth={48}
        minHeight={32}
        onResize={(_e, p) => {
          if (typeof p.width === 'number' && typeof p.height === 'number') {
            onResize?.(id, p.width, p.height);
          }
        }}
        onResizeEnd={() => onResizeEnd?.(id)}
      />
      <img src={src} width={width} height={height} alt="" draggable={false} className="flow-image-node-img" />
      <Handle type="target" position={Position.Top} style={{ opacity: 0 }} />
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0 }} />
    </div>
  );
}

export default memo(FlowImageNode);
