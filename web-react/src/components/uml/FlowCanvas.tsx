import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  MarkerType,
  ConnectionLineType,
  type Node,
  type Edge,
  type EdgeMarker,
  type OnConnect,
  type OnNodesChange,
  type OnEdgesChange,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import FlowNode from './FlowNode';
import FlowImageNode from './FlowImageNode';
import FlowEdge from './FlowEdge';
import type { FlowShape } from './mermaidParser';

export type CtxTarget = 'node' | 'edge' | 'pane';

interface FlowCanvasProps {
  nodes: Node[];
  edges: Edge[];
  snapToGrid: boolean;
  /** 变化时自动适配视口（生成新图/恢复时由外层触发；拖入节点不触发，避免视图跳动） */
  fitSignal?: number;
  onNodesChange: OnNodesChange;
  onEdgesChange: OnEdgesChange;
  onConnect: OnConnect;
  onNodesDelete: (deleted: Node[]) => void;
  onEdgesDelete: (deleted: Edge[]) => void;
  onSelectionChange: (nodes: Node[], edges: Edge[]) => void;
  onNodeDragStop: () => void;
  onDropShape: (shape: FlowShape, position: { x: number; y: number }) => void;
  onDropImage: (dataUrl: string, position: { x: number; y: number }) => void;
  onContextMenuRequest: (target: CtxTarget, id: string | null, x: number, y: number) => void;
  onEdgeLabelEdit: (edgeId: string, label: string) => void;
  onEdgePathChange: (edgeId: string, pts: { x: number; y: number }[]) => void;
  onEdgePathEditStart: (edgeId: string) => void;
  onEdgePathEditEnd: (edgeId: string) => void;
}

const SNAP = 6; // 对齐吸附阈值（flow 单位）

export default function FlowCanvas(props: FlowCanvasProps) {
  return (
    <ReactFlowProvider>
      <FlowCanvasInner {...props} />
    </ReactFlowProvider>
  );
}

function FlowCanvasInner({
  nodes,
  edges,
  snapToGrid,
  fitSignal,
  onNodesChange,
  onEdgesChange,
  onConnect,
  onNodesDelete,
  onEdgesDelete,
  onSelectionChange,
  onNodeDragStop,
  onDropShape,
  onDropImage,
  onContextMenuRequest,
  onEdgeLabelEdit,
  onEdgePathChange,
  onEdgePathEditStart,
  onEdgePathEditEnd,
}: FlowCanvasProps) {
  const { screenToFlowPosition, flowToScreenPosition, fitView } = useReactFlow();
  const nodeTypes = useMemo(() => ({ flow: FlowNode, image: FlowImageNode }), []);
  // 注入连线交互回调（不持久化到 data，运行时注入）
  const edgeTypes = useMemo(
    () => ({
      step: (p: React.ComponentProps<typeof FlowEdge>) => (
        <FlowEdge
          {...p}
          data={{
            ...(p.data as object),
            onLabelEdit: onEdgeLabelEdit,
            onPathChange: onEdgePathChange,
            onPathEditStart: onEdgePathEditStart,
            onPathEditEnd: onEdgePathEditEnd,
          }}
        />
      ),
    }),
    [onEdgeLabelEdit, onEdgePathChange, onEdgePathEditStart, onEdgePathEditEnd]
  );

  // 对齐辅助线（flow 坐标）
  const [guides, setGuides] = useState<{ x?: number; y?: number }>({});
  const nodesRef = useRef(nodes);
  useEffect(() => {
    nodesRef.current = nodes;
  }, [nodes]);

  // 仅在 fitSignal 变化时适配视口（生成/恢复），拖入节点不触发
  useEffect(() => {
    if (fitSignal === undefined) return;
    const t = setTimeout(() => fitView({ padding: 0.3, maxZoom: 1.2 }), 60);
    return () => clearTimeout(t);
  }, [fitSignal, fitView]);

  // ---------- 拖拽对齐辅助线 ----------
  const handleNodeDrag = useCallback(
    (_: unknown, dragging: Node) => {
      const others = nodesRef.current.filter((n) => n.id !== dragging.id);
      if (others.length === 0) return;
      const gw = dragging.measured?.width ?? 100;
      const gh = dragging.measured?.height ?? 40;
      const dx = dragging.position.x;
      const dy = dragging.position.y;
      const dLeft = dx;
      const dRight = dx + gw;
      const dCx = dx + gw / 2;
      const dTop = dy;
      const dBottom = dy + gh;
      const dCy = dy + gh / 2;

      let gx: number | undefined;
      let gy: number | undefined;
      let nx = dx;
      let ny = dy;

      for (const o of others) {
        const ow = o.measured?.width ?? 100;
        const oh = o.measured?.height ?? 40;
        const ox = o.position.x;
        const oy = o.position.y;
        const oLeft = ox;
        const oRight = ox + ow;
        const oCx = ox + ow / 2;
        const oTop = oy;
        const oBottom = oy + oh;
        const oCy = oy + oh / 2;

        const xPairs: [number, number][] = [
          [dLeft, oLeft],
          [dCx, oCx],
          [dRight, oRight],
          [dLeft, oRight],
          [dRight, oLeft],
        ];
        for (const [dv, ov] of xPairs) {
          if (Math.abs(dv - ov) < SNAP) {
            nx = dx + (ov - dv);
            gx = ov;
          }
        }
        const yPairs: [number, number][] = [
          [dTop, oTop],
          [dCy, oCy],
          [dBottom, oBottom],
          [dTop, oBottom],
          [dBottom, oTop],
        ];
        for (const [dv, ov] of yPairs) {
          if (Math.abs(dv - ov) < SNAP) {
            ny = dy + (ov - dv);
            gy = ov;
          }
        }
      }

      if (nx !== dx || ny !== dy) {
        onNodesChange([{ type: 'position', id: dragging.id, position: { x: nx, y: ny } }]);
      }
      setGuides({ x: gx, y: gy });
    },
    [onNodesChange]
  );

  const clearGuides = useCallback(() => setGuides({}), []);

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      const file = files[0];
      if (file.type.startsWith('image/')) {
        const position = screenToFlowPosition({ x: e.clientX, y: e.clientY });
        const reader = new FileReader();
        reader.onload = () => {
          if (typeof reader.result === 'string') onDropImage(reader.result, position);
        };
        reader.readAsDataURL(file);
      }
      return;
    }
    const shape = e.dataTransfer.getData('application/flow-shape') as FlowShape;
    if (!shape) return;
    const position = screenToFlowPosition({ x: e.clientX, y: e.clientY });
    onDropShape(shape, position);
  };

  // 参考线屏幕坐标
  const guideSX = guides.x !== undefined ? flowToScreenPosition({ x: guides.x, y: 0 }).x : null;
  const guideSY = guides.y !== undefined ? flowToScreenPosition({ x: 0, y: guides.y }).y : null;

  return (
    <div
      className="fl-canvas"
      onDrop={onDrop}
      onDragOver={(e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
      }}
      onMouseDown={() => setGuides({})}
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodesDelete={onNodesDelete}
        onEdgesDelete={onEdgesDelete}
        onSelectionChange={(params) => onSelectionChange(params.nodes, params.edges)}
        onNodeDrag={handleNodeDrag}
        onNodeDragStop={() => {
          clearGuides();
          onNodeDragStop();
        }}
        onNodeContextMenu={(e, node) => {
          e.preventDefault();
          onContextMenuRequest('node', node.id, e.clientX, e.clientY);
        }}
        onEdgeContextMenu={(e, edge) => {
          e.preventDefault();
          onContextMenuRequest('edge', edge.id, e.clientX, e.clientY);
        }}
        onPaneContextMenu={(e) => {
          e.preventDefault();
          onContextMenuRequest('pane', null, e.clientX, e.clientY);
        }}
        snapToGrid={snapToGrid}
        snapGrid={[16, 16]}
        fitView
        fitViewOptions={{ padding: 0.3, maxZoom: 1.2 }}
        minZoom={0.2}
        maxZoom={2.5}
        deleteKeyCode={['Backspace', 'Delete']}
        selectionOnDrag={false}
        connectionLineType={ConnectionLineType.Step}
        connectionLineStyle={{ stroke: '#8a8a92', strokeWidth: 1.6 }}
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={22} size={1.2} color="#d9d9de" />
        <Controls position="bottom-right" showInteractive={false} />
        <MiniMap
          pannable
          zoomable
          nodeColor="#b9c0ea"
          maskColor="rgba(247, 247, 248, 0.72)"
          style={{ background: '#fff', border: '1px solid #e8e8ea', borderRadius: 10 }}
        />
      </ReactFlow>

      {/* 对齐参考线 */}
      {guideSX !== null && <div className="fl-guide fl-guide-v" style={{ left: guideSX }} />}
      {guideSY !== null && <div className="fl-guide fl-guide-h" style={{ top: guideSY }} />}

      <div className="fl-hint">双击节点改字 · 从节点圆点拖出连线 · 选中后 Delete 删除 · 右键菜单 · Ctrl+Z 撤销</div>
    </div>
  );
}

/** 创建带箭头的边（step 直角折线，流程图中线必须是直的） */
export function makeEdge(conn: { source: string; target: string; sourceHandle?: string | null; targetHandle?: string | null }, label?: string): Edge {
  return {
    id: `e-${conn.source}-${conn.target}-${Date.now()}`,
    source: conn.source,
    target: conn.target,
    sourceHandle: conn.sourceHandle ?? undefined,
    targetHandle: conn.targetHandle ?? undefined,
    label,
    type: 'step',
    animated: false,
    markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18, color: '#8a8a92' },
    style: { stroke: '#8a8a92', strokeWidth: 1.6 },
    labelStyle: { fill: '#6e6e73', fontSize: 12 },
    labelBgStyle: { fill: '#ffffff', fillOpacity: 0.85 },
    labelBgPadding: [6, 3] as [number, number],
    labelBgBorderRadius: 4,
  };
}

/** 更新边的视觉样式（arrowType: closed 实心 / open 空心 / none 无箭头） */
export function styleEdge(
  edge: Edge,
  patch: { label?: string; lineStyle?: string; color?: string; arrow?: boolean; arrowType?: 'closed' | 'open' | 'none'; width?: number }
): Edge {
  const next = { ...edge };
  if (patch.label !== undefined) next.label = patch.label || undefined;
  if (patch.lineStyle !== undefined) {
    next.style = {
      ...(next.style || {}),
      strokeDasharray: patch.lineStyle === 'dashed' ? '8 5' : patch.lineStyle === 'dotted' ? '2 4' : 'none',
    };
  }
  if (patch.color !== undefined) {
    next.style = { ...(next.style || {}), stroke: patch.color };
    if (next.markerEnd) {
      const cur = next.markerEnd as EdgeMarker;
      next.markerEnd = { type: cur.type, width: cur.width, height: cur.height, color: patch.color };
    }
    next.labelStyle = { ...(next.labelStyle || {}), fill: patch.color };
  }
  if (patch.width !== undefined) {
    next.style = { ...(next.style || {}), strokeWidth: patch.width };
  }
  if (patch.arrow !== undefined || patch.arrowType !== undefined) {
    const at = patch.arrowType ?? (patch.arrow ? 'closed' : 'none');
    const color = (next.style as { stroke?: string })?.stroke || '#8a8a92';
    if (at === 'none') {
      delete next.markerEnd;
    } else {
      next.markerEnd = {
        type: at === 'open' ? MarkerType.Arrow : MarkerType.ArrowClosed,
        width: at === 'open' ? 20 : 18,
        height: at === 'open' ? 20 : 18,
        color,
      };
    }
  }
  return next;
}
