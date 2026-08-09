import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react';
import mermaid from 'mermaid';
import { useNodesState, useEdgesState, addEdge, type Node, type Edge, type EdgeMarkerType, type Connection } from '@xyflow/react';
import { analyzeUml } from '../../api/uml';
import { buildDiagramSvg } from './exportDiagram';
import type { UmlDiagramType } from '../../types';
import FlowCanvas, { makeEdge, styleEdge, type CtxTarget } from './FlowCanvas';
import ShapePalette from './ShapePalette';
import PropertiesPanel, { type NodePanelData, type EdgePanelData } from './PropertiesPanel';
import ContextMenu, { type CtxMenuState, type CtxMenuAction } from './ContextMenu';
import type { FlowNodeData } from './FlowNode';
import type { FlowImageNodeData } from './FlowImageNode';
import {
  parseMermaidFlowchart,
  layoutFlowchart,
  serializeFlowchart,
  SHAPE_NAMES,
  type FlowDirection,
  type FlowShape,
  type NodeStyle,
} from './mermaidParser';

// Mermaid 初始化（仅非 flowchart 类型渲染用）
mermaid.initialize({
  startOnLoad: false,
  theme: 'base',
  securityLevel: 'loose',
  fontFamily: '"PingFang SC", "Microsoft YaHei", "Segoe UI", sans-serif',
  themeVariables: {
    primaryColor: '#f2f2f3',
    primaryTextColor: '#1d1c23',
    primaryBorderColor: '#e8e8ea',
    lineColor: '#6e6e73',
    fontSize: '14px',
  },
});

const DIAGRAM_OPTIONS: { value: UmlDiagramType; label: string }[] = [
  { value: 'flowchart', label: '流程图 flowchart' },
  { value: 'activity', label: '活动图 activity' },
  { value: 'usecase', label: '用例图 usecase' },
  { value: 'sequenceDiagram', label: '时序图 sequenceDiagram' },
  { value: 'classDiagram', label: '类图 classDiagram' },
  { value: 'erDiagram', label: 'ER 图 erDiagram' },
];

/** 可用画板编辑的类型（flowchart 语法：流程图/活动图/用例图） */
const BOARD_TYPES: UmlDiagramType[] = ['flowchart', 'activity', 'usecase'];

const EXAMPLES: { label: string; text: string }[] = [
  { label: '登录流程', text: '用户登录流程：输入账号密码，校验通过进入首页，失败提示重试，连续失败 5 次锁定账号 30 分钟。' },
  { label: '订单处理', text: '电商下单流程：用户提交订单，系统校验库存，库存充足则扣减库存并创建支付单，支付成功通知仓库发货；库存不足则提示缺货并允许预约。' },
];

const BOARD_STORAGE_KEY = 'iris_uml_board_v1';

type SavedBoard = {
  prompt: string;
  diagramType: UmlDiagramType;
  direction: FlowDirection;
  mermaidCode: string;
  nodes: { id: string; position: { x: number; y: number }; data: Record<string, unknown> }[];
  edges: {
    id: string;
    source: string;
    target: string;
    label?: string;
    style?: object;
    markerEnd?: EdgeMarkerType;
    points?: { x: number; y: number }[];
  }[];
  savedAt: number;
};

function saveBoardToStorage(data: SavedBoard) {
  try {
    localStorage.setItem(BOARD_STORAGE_KEY, JSON.stringify(data));
  } catch {
    /* 存储不可用时静默 */
  }
}

function loadBoardFromStorage(): SavedBoard | null {
  try {
    const raw = localStorage.getItem(BOARD_STORAGE_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw);
    if (!Array.isArray(data.nodes)) return null;
    return data as SavedBoard;
  } catch {
    return null;
  }
}

function mkNode(
  id: string,
  shape: FlowShape,
  pos: { x: number; y: number },
  direction: FlowDirection,
  onLabelChange: (id: string, label: string) => void,
  onResize?: (id: string, w: number, h: number) => void,
  onResizeEnd?: (id: string) => void
): Node {
  const label = shape === 'note' ? '备注' : SHAPE_NAMES[shape];
  return {
    id,
    type: 'flow',
    position: pos,
    data: { label, shape, direction, onLabelChange, onResize, onResizeEnd } as FlowNodeData,
  };
}

function buildFlowNodes(
  fc: ReturnType<typeof layoutFlowchart>,
  direction: FlowDirection,
  onLabelChange: (id: string, label: string) => void,
  onResize?: (id: string, w: number, h: number) => void,
  onResizeEnd?: (id: string) => void
): Node[] {
  return fc.map((n) => ({
    id: n.id,
    type: 'flow',
    position: { x: n.x, y: n.y },
    data: { label: n.label, shape: n.shape, direction, onLabelChange, onResize, onResizeEnd } as FlowNodeData,
  }));
}

/**
 * 克隆节点/边（用于历史快照与复制粘贴）。
 * 注意：不能使用 structuredClone——node.data 里含函数引用（onLabelChange 等），
 * structuredClone 遇函数会抛 DataCloneError 导致操作中断。
 */
function cloneNode(n: Node): Node {
  const d = n.data as FlowNodeData;
  return {
    ...n,
    position: { ...n.position },
    style: n.style ? { ...n.style } : undefined,
    data: { ...d, style: d.style ? { ...d.style } : undefined },
  };
}

function cloneEdge(e: Edge): Edge {
  return { ...e, style: e.style ? { ...e.style } : undefined };
}

/** 图片节点构造（拖入本地图片创建） */
function mkImageNode(
  id: string,
  src: string,
  pos: { x: number; y: number },
  width: number,
  height: number,
  onResize?: (id: string, w: number, h: number) => void,
  onResizeEnd?: (id: string) => void
): Node {
  return { id, type: 'image', position: pos, data: { src, width, height, onResize, onResizeEnd } as FlowImageNodeData };
}

type AlignMode = 'left' | 'centerX' | 'right' | 'top' | 'centerY' | 'bottom';
type DistMode = 'X' | 'Y';

export default function UmlFlowPage() {
  const [prompt, setPrompt] = useState('');
  const [diagramType, setDiagramType] = useState<UmlDiagramType>('flowchart');
  const [generating, setGenerating] = useState(false);
  const [apiError, setApiError] = useState('');
  const [mermaidCode, setMermaidCode] = useState('');
  const [svg, setSvg] = useState('');
  const [renderError, setRenderError] = useState('');
  const renderSeq = useRef(0);
  const resultRef = useRef<HTMLDivElement | null>(null);

  // 画板状态
  const [flowNodes, setFlowNodes, onFlowNodesChange] = useNodesState<Node>([]);
  const [flowEdges, setFlowEdges, onFlowEdgesChange] = useEdgesState<Edge>([]);
  const [direction, setDirection] = useState<FlowDirection>('TD');
  const [snapToGrid, setSnapToGrid] = useState(true);
  const [fitSignal, setFitSignal] = useState(0);
  const [selNodeId, setSelNodeId] = useState<string | null>(null);
  const [selEdgeId, setSelEdgeId] = useState<string | null>(null);
  const [selectedNodes, setSelectedNodes] = useState<Node[]>([]);
  const selectedNodesRef = useRef<Node[]>([]);
  const [ctxMenu, setCtxMenu] = useState<CtxMenuState>(null);
  const boardRef = useRef<HTMLDivElement | null>(null);
  const boardActionRef = useRef(false);

  const nodesRef = useRef(flowNodes);
  const edgesRef = useRef(flowEdges);
  useEffect(() => {
    nodesRef.current = flowNodes;
  }, [flowNodes]);
  useEffect(() => {
    edgesRef.current = flowEdges;
  }, [flowEdges]);

  const isBoardMode = BOARD_TYPES.includes(diagramType);

  // ---------- 历史栈 ----------
  const historyRef = useRef<{ n: Node[]; e: Edge[] }[]>([]);
  const histIdx = useRef(-1);

  const snapshot = useCallback(() => {
    historyRef.current = historyRef.current.slice(0, histIdx.current + 1);
    historyRef.current.push({ n: nodesRef.current.map(cloneNode), e: edgesRef.current.map(cloneEdge) });
    if (historyRef.current.length > 60) historyRef.current.shift();
    histIdx.current = historyRef.current.length - 1;
  }, []);

  // ---------- 自动保存（操作完成时写入 localStorage） ----------
  const saveBoard = useCallback(() => {
    if (!isBoardMode) return;
    // 仅序列化图形节点（图片节点不进入 mermaid 源码，但存入 localStorage 以便恢复）
    const flowNodesOnly = nodesRef.current.filter((n) => (n.data as { src?: string }).src === undefined);
    const code = serializeFlowchart(
      flowNodesOnly.map((n) => {
        const d = n.data as FlowNodeData;
        return { id: n.id, label: d.label, shape: d.shape, style: d.style };
      }),
      edgesRef.current.map((e) => ({ source: e.source, target: e.target, label: typeof e.label === 'string' ? e.label : undefined })),
      direction
    );
    saveBoardToStorage({
      prompt,
      diagramType,
      direction,
      mermaidCode: code,
      nodes: nodesRef.current.map((n) => {
        const img = n.data as FlowImageNodeData;
        if (img.src) {
          return { id: n.id, position: n.position, data: { src: img.src, width: img.width, height: img.height } };
        }
        const d = n.data as FlowNodeData;
        return { id: n.id, position: n.position, data: { label: d.label, shape: d.shape, style: d.style } };
      }),
      edges: edgesRef.current.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        label: typeof e.label === 'string' ? e.label : undefined,
        style: e.style,
        markerEnd: e.markerEnd,
        points: (e.data as { points?: { x: number; y: number }[] } | undefined)?.points,
      })),
      savedAt: Date.now(),
    });
  }, [isBoardMode, direction, prompt, diagramType]);

  const undo = useCallback(() => {
    if (histIdx.current <= 0) return;
    histIdx.current--;
    const s = historyRef.current[histIdx.current];
    boardActionRef.current = true;
    setFlowNodes(s.n);
    setFlowEdges(s.e);
    setSelNodeId(null);
    setSelEdgeId(null);
    saveBoard();
  }, [setFlowEdges, setFlowNodes, saveBoard]);

  const redo = useCallback(() => {
    if (histIdx.current >= historyRef.current.length - 1) return;
    histIdx.current++;
    const s = historyRef.current[histIdx.current];
    boardActionRef.current = true;
    setFlowNodes(s.n);
    setFlowEdges(s.e);
    setSelNodeId(null);
    setSelEdgeId(null);
    saveBoard();
  }, [setFlowEdges, setFlowNodes, saveBoard]);

  // ---------- 复制 / 粘贴 ----------
  const copyBufRef = useRef<{ n: Node[]; e: Edge[] } | null>(null);

  const handleCopy = useCallback(() => {
    const ns = selectedNodesRef.current;
    if (ns.length === 0) return;
    const ids = new Set(ns.map((n) => n.id));
    copyBufRef.current = {
      n: ns.map(cloneNode),
      e: edgesRef.current.filter((e) => ids.has(e.source) && ids.has(e.target)).map(cloneEdge),
    };
  }, []);

  const handleCopyNode = useCallback((id: string) => {
    const n = nodesRef.current.find((x) => x.id === id);
    if (!n) return;
    copyBufRef.current = { n: [cloneNode(n)], e: [] };
  }, []);

  const handlePaste = useCallback(() => {
    const buf = copyBufRef.current;
    if (!buf || buf.n.length === 0) return;
    boardActionRef.current = true;
    snapshot();
    const idMap = new Map<string, string>();
    const newNodes: Node[] = buf.n.map((n) => {
      const id = `${n.id}-c${Date.now()}`;
      idMap.set(n.id, id);
      return { ...cloneNode(n), id, position: { x: n.position.x + 40, y: n.position.y + 40 } };
    });
    const newEdges: Edge[] = buf.e.map((e) => ({
      ...cloneEdge(e),
      id: `${e.id}-c${Date.now()}`,
      source: idMap.get(e.source) || e.source,
      target: idMap.get(e.target) || e.target,
    }));
    setFlowNodes((ns) => [...ns, ...newNodes]);
    setFlowEdges((es) => [...es, ...newEdges]);
    saveBoard();
  }, [setFlowEdges, setFlowNodes, snapshot, saveBoard]);

  // ---------- 快捷键 ----------
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t && (t.tagName === 'TEXTAREA' || t.tagName === 'INPUT' || t.isContentEditable)) return;
      if (!isBoardMode) return;
      const mod = e.ctrlKey || e.metaKey;
      if (mod && e.key.toLowerCase() === 'z' && !e.shiftKey) {
        e.preventDefault();
        undo();
      } else if (mod && (e.key.toLowerCase() === 'y' || (e.key.toLowerCase() === 'z' && e.shiftKey))) {
        e.preventDefault();
        redo();
      } else if (mod && e.key.toLowerCase() === 'c') {
        handleCopy();
      } else if (mod && e.key.toLowerCase() === 'v') {
        e.preventDefault();
        handlePaste();
      } else if (mod && e.key.toLowerCase() === 'a') {
        e.preventDefault();
        setFlowNodes((ns) => ns.map((n) => ({ ...n, selected: true })));
      }
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [isBoardMode, undo, redo, handleCopy, handlePaste, setFlowNodes]);

  // ---------- Mermaid 渲染（非 flowchart） ----------
  const renderDiagram = useCallback(async (code: string) => {
    if (!code.trim()) {
      setSvg('');
      setRenderError('');
      return;
    }
    const seq = ++renderSeq.current;
    try {
      const id = `uml-${Date.now()}-${seq}`;
      const { svg: out } = await mermaid.render(id, code);
      if (seq !== renderSeq.current) return;
      setSvg(out);
      setRenderError('');
    } catch (err) {
      if (seq !== renderSeq.current) return;
      setRenderError(err instanceof Error ? err.message : '图表渲染失败，请检查 Mermaid 语法');
    }
  }, []);

  // ---------- 节点文字修改（双击） ----------
  const handleLabelChange = useCallback(
    (id: string, label: string) => {
      boardActionRef.current = true;
      snapshot();
      setFlowNodes((ns) => ns.map((n) => (n.id === id ? { ...n, data: { ...n.data, label } } : n)));
      saveBoard();
    },
    [setFlowNodes, snapshot, saveBoard]
  );

  // ---------- 节点尺寸调整（拖拽手柄） ----------
  const handleResize = useCallback(
    (id: string, width: number, height: number) => {
      boardActionRef.current = true;
      setFlowNodes((ns) =>
        ns.map((n) => {
          if (n.id !== id) return n;
          const cur = n.data as FlowNodeData;
          return { ...n, data: { ...cur, style: { ...(cur.style || {}), width, height } } };
        })
      );
    },
    [setFlowNodes]
  );
  const handleResizeEnd = useCallback(
    (id: string) => {
      snapshot();
      saveBoard();
      setSelNodeId(id);
    },
    [snapshot, saveBoard]
  );

  // ---------- 图片节点（拖入本地图片） ----------
  const handleImageResize = useCallback(
    (id: string, width: number, height: number) => {
      boardActionRef.current = true;
      setFlowNodes((ns) =>
        ns.map((n) => {
          if (n.id !== id) return n;
          const cur = n.data as FlowImageNodeData;
          return { ...n, data: { ...cur, width, height } };
        })
      );
    },
    [setFlowNodes]
  );
  const handleDropImage = useCallback(
    (dataUrl: string, position: { x: number; y: number }) => {
      boardActionRef.current = true;
      snapshot();
      const img = new Image();
      img.onload = () => {
        const scale = Math.min(1, 300 / (img.width || 300));
        const width = Math.max(48, Math.round((img.width || 300) * scale));
        const height = Math.max(32, Math.round((img.height || 200) * scale));
        const id = `img${Date.now()}`;
        setFlowNodes((ns) => [...ns, mkImageNode(id, dataUrl, position, width, height, handleImageResize, handleResizeEnd)]);
        setSelNodeId(id);
        saveBoard();
      };
      img.src = dataUrl;
    },
    [handleImageResize, handleResizeEnd, setFlowNodes, snapshot, saveBoard]
  );

  // ---------- 挂载时恢复自动保存的画板 ----------
  useEffect(() => {
    const saved = loadBoardFromStorage();
    if (!saved || !BOARD_TYPES.includes(saved.diagramType) || saved.nodes.length === 0) return;
    setDiagramType(saved.diagramType);
    setPrompt(saved.prompt || '');
    setDirection(saved.direction || 'TD');
    setMermaidCode(saved.mermaidCode || '');
    setFlowNodes(
      saved.nodes.map((n) => {
        const img = n.data as FlowImageNodeData;
        if (img.src) {
          return {
            id: n.id,
            type: 'image',
            position: n.position,
            data: { src: img.src, width: img.width, height: img.height, onResize: handleImageResize, onResizeEnd: handleResizeEnd } as FlowImageNodeData,
          };
        }
        return {
          id: n.id,
          type: 'flow',
          position: n.position,
          data: {
            ...n.data,
            direction: saved.direction,
            onLabelChange: handleLabelChange,
            onResize: handleResize,
            onResizeEnd: handleResizeEnd,
          } as FlowNodeData,
        };
      })
    );
    setFlowEdges(
      saved.edges.map((e) => {
        const base = makeEdge({ source: e.source, target: e.target }, e.label);
        return {
          ...base,
          id: e.id,
          style: e.style as CSSProperties,
          markerEnd: e.markerEnd,
          data: e.points ? { points: e.points } : undefined,
        };
      })
    );
    setFitSignal((s) => s + 1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---------- 应用生成/解析的代码到画板 ----------
  const applyParsedToBoard = useCallback(
    (code: string): boolean => {
      if (!BOARD_TYPES.includes(diagramType)) return false;
      try {
        const fc = parseMermaidFlowchart(code);
        if (fc.nodes.length === 0) return false;
        const layouted = layoutFlowchart(fc);
        setDirection(fc.direction);
        setFlowNodes(buildFlowNodes(layouted, fc.direction, handleLabelChange, handleResize, handleResizeEnd));
        setFlowEdges(fc.edges.map((e) => makeEdge({ source: e.source, target: e.target }, e.label)));
        setRenderError('');
        setFitSignal((s) => s + 1);
        return true;
      } catch {
        return false;
      }
    },
    [diagramType, handleLabelChange, handleResize, handleResizeEnd, setFlowEdges, setFlowNodes]
  );

  // 画板 → 源码 同步（仅用户操作画板时；图片节点不进入 mermaid 源码）
  useEffect(() => {
    if (!boardActionRef.current) return;
    boardActionRef.current = false;
    if (!isBoardMode) return;
    const code = serializeFlowchart(
      flowNodes
        .filter((n) => (n.data as { src?: string }).src === undefined)
        .map((n) => {
          const d = n.data as FlowNodeData;
          return { id: n.id, label: d.label, shape: d.shape, style: d.style };
        }),
      flowEdges.map((e) => ({ source: e.source, target: e.target, label: typeof e.label === 'string' ? e.label : undefined })),
      direction
    );
    setMermaidCode(code);
  }, [flowNodes, flowEdges, direction, isBoardMode]);

  // ---------- 画板事件 ----------
  const handleNodesChange = useCallback(
    (changes: Parameters<typeof onFlowNodesChange>[0]) => {
      boardActionRef.current = true;
      onFlowNodesChange(changes);
    },
    [onFlowNodesChange]
  );
  const handleEdgesChange = useCallback(
    (changes: Parameters<typeof onFlowEdgesChange>[0]) => {
      boardActionRef.current = true;
      onFlowEdgesChange(changes);
    },
    [onFlowEdgesChange]
  );
  const handleConnect = useCallback(
    (conn: Connection) => {
      boardActionRef.current = true;
      snapshot();
      setFlowEdges((eds) => addEdge(makeEdge(conn), eds));
      saveBoard();
    },
    [setFlowEdges, snapshot, saveBoard]
  );
  const handleNodesDelete = useCallback(
    (deleted: Node[]) => {
      boardActionRef.current = true;
      snapshot();
      const ids = new Set(deleted.map((n) => n.id));
      setFlowEdges((eds) => eds.filter((e) => !ids.has(e.source) && !ids.has(e.target)));
      if (deleted.some((n) => n.id === selNodeId)) setSelNodeId(null);
      saveBoard();
    },
    [setFlowEdges, selNodeId, snapshot, saveBoard]
  );
  const handleSelectionChange = useCallback((nodes: Node[], edges: Edge[]) => {
    selectedNodesRef.current = nodes;
    setSelectedNodes(nodes);
    setSelNodeId(nodes.length === 1 ? nodes[0].id : null);
    setSelEdgeId(edges.length === 1 ? edges[0].id : null);
  }, []);
  const handleNodeDragStop = useCallback(() => {
    snapshot();
    saveBoard();
  }, [snapshot, saveBoard]);
  const handleDropShape = useCallback(
    (shape: FlowShape, position: { x: number; y: number }) => {
      boardActionRef.current = true;
      snapshot();
      const id = `n${Date.now()}`;
      setFlowNodes((ns) => [...ns, mkNode(id, shape, position, direction, handleLabelChange, handleResize, handleResizeEnd)]);
      setSelNodeId(id);
      saveBoard();
    },
    [direction, handleLabelChange, handleResize, handleResizeEnd, setFlowNodes, snapshot, saveBoard]
  );
  // 按指定形状在画布下方新增节点
  const handleAddShape = useCallback(
    (shape: FlowShape) => {
      boardActionRef.current = true;
      snapshot();
      const id = `n${Date.now()}`;
      const base = nodesRef.current.length > 0 ? Math.max(...nodesRef.current.map((n) => n.position.y)) + 90 : 40;
      setFlowNodes((ns) => [...ns, mkNode(id, shape, { x: 60, y: base }, direction, handleLabelChange, handleResize, handleResizeEnd)]);
      setSelNodeId(id);
      saveBoard();
    },
    [direction, handleLabelChange, handleResize, handleResizeEnd, setFlowNodes, snapshot, saveBoard]
  );
  const handleAddNode = useCallback(() => handleAddShape('rect'), [handleAddShape]);

  // ---------- 属性面板 ----------
  const selNode = flowNodes.find((n) => n.id === selNodeId) || null;
  const selEdge = flowEdges.find((e) => e.id === selEdgeId) || null;
  const ppTarget = selNode ? 'node' : selEdge ? 'edge' : null;

  const nodePanelData: NodePanelData | null = selNode
    ? {
        id: selNode.id,
        label: (selNode.data as FlowNodeData).label,
        shape: (selNode.data as FlowNodeData).shape,
        style: (selNode.data as FlowNodeData).style,
      }
    : null;

  const edgePanelData: EdgePanelData | null = selEdge
    ? {
        id: selEdge.id,
        label: typeof selEdge.label === 'string' ? selEdge.label : undefined,
        lineStyle:
          (selEdge.style as { strokeDasharray?: string })?.strokeDasharray === '8 5'
            ? 'dashed'
            : (selEdge.style as { strokeDasharray?: string })?.strokeDasharray === '2 4'
              ? 'dotted'
              : 'solid',
        color: ((selEdge.style as { stroke?: string })?.stroke as string) || '#8a8a92',
        arrowType: !selEdge.markerEnd
          ? 'none'
          : (selEdge.markerEnd as { type?: string })?.type === 'arrow'
            ? 'open'
            : 'closed',
        width: Number((selEdge.style as { strokeWidth?: number })?.strokeWidth) || 1.6,
      }
    : null;

  const patchNode = useCallback(
    (id: string, patch: Partial<{ label: string; shape: FlowShape; style: NodeStyle }>) => {
      boardActionRef.current = true;
      snapshot();
      setFlowNodes((ns) =>
        ns.map((n) => {
          if (n.id !== id) return n;
          const cur = n.data as FlowNodeData;
          return {
            ...n,
            data: {
              ...cur,
              ...(patch.label !== undefined ? { label: patch.label } : {}),
              ...(patch.shape !== undefined ? { shape: patch.shape } : {}),
              style: { ...(cur.style || {}), ...(patch.style || {}) },
            } as FlowNodeData,
          };
        })
      );
      saveBoard();
    },
    [setFlowNodes, snapshot, saveBoard]
  );

  const patchEdge = useCallback(
    (id: string, patch: Parameters<typeof styleEdge>[1]) => {
      boardActionRef.current = true;
      snapshot();
      setFlowEdges((es) => es.map((e) => (e.id === id ? styleEdge(e, patch) : e)));
      saveBoard();
    },
    [setFlowEdges, snapshot, saveBoard]
  );

  // ---------- 双击连线编辑标签 ----------
  const handleEdgeLabelEdit = useCallback(
    (id: string, label: string) => {
      patchEdge(id, { label });
    },
    [patchEdge]
  );

  // ---------- 连线拐点拖拽编辑 ----------
  const handleEdgePathChange = useCallback(
    (edgeId: string, pts: { x: number; y: number }[]) => {
      boardActionRef.current = true;
      setFlowEdges((es) => es.map((e) => (e.id === edgeId ? { ...e, data: { ...(e.data || {}), points: pts } } : e)));
    },
    [setFlowEdges]
  );
  const handleEdgePathEditEnd = useCallback(
    (edgeId: string) => {
      snapshot();
      saveBoard();
      setSelEdgeId(edgeId);
    },
    [snapshot, saveBoard]
  );

  // ---------- 画板导出 PNG / SVG（零依赖手绘导出） ----------
  const exportBoard = useCallback((fmt: 'png' | 'svg') => {
    const svgStr = buildDiagramSvg(nodesRef.current, edgesRef.current);
    if (!svgStr) return;
    const filename = `flowchart-${Date.now()}.${fmt}`;
    const blob = new Blob([svgStr], { type: 'image/svg+xml;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    if (fmt === 'svg') {
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
      return;
    }
    // PNG：SVG → Image → canvas
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement('canvas');
      canvas.width = img.width;
      canvas.height = img.height;
      const ctx = canvas.getContext('2d');
      if (ctx) {
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(img, 0, 0);
      }
      URL.revokeObjectURL(url);
      const a = document.createElement('a');
      a.href = canvas.toDataURL('image/png');
      a.download = filename;
      a.click();
    };
    img.onerror = () => URL.revokeObjectURL(url);
    img.src = url;
  }, []);

  const deleteNodeById = useCallback(
    (id: string) => {
      boardActionRef.current = true;
      snapshot();
      setFlowNodes((ns) => ns.filter((n) => n.id !== id));
      setFlowEdges((es) => es.filter((e) => e.source !== id && e.target !== id));
      if (selNodeId === id) setSelNodeId(null);
      saveBoard();
    },
    [setFlowEdges, setFlowNodes, selNodeId, snapshot, saveBoard]
  );

  const deleteEdgeById = useCallback(
    (id: string) => {
      boardActionRef.current = true;
      snapshot();
      setFlowEdges((es) => es.filter((e) => e.id !== id));
      if (selEdgeId === id) setSelEdgeId(null);
      saveBoard();
    },
    [setFlowEdges, selEdgeId, snapshot, saveBoard]
  );

  const handlePanelDelete = () => {
    if (selNodeId) deleteNodeById(selNodeId);
    else if (selEdgeId) deleteEdgeById(selEdgeId);
  };

  const setNodeZ = useCallback(
    (id: string, z: number) => {
      boardActionRef.current = true;
      snapshot();
      setFlowNodes((ns) => ns.map((n) => (n.id === id ? { ...n, zIndex: z } : n)));
      saveBoard();
    },
    [setFlowNodes, snapshot, saveBoard]
  );

  // ---------- 多选：对齐 / 分布 / 统一尺寸 ----------
  const alignSelected = useCallback(
    (mode: AlignMode) => {
      const sel = selectedNodesRef.current;
      if (sel.length < 2) return;
      boardActionRef.current = true;
      snapshot();
      const ids = new Set(sel.map((n) => n.id));
      const xs = sel.map((n) => n.position.x);
      const ys = sel.map((n) => n.position.y);
      const rightX = Math.max(...sel.map((n) => n.position.x + (n.measured?.width ?? 100)));
      const bottomY = Math.max(...sel.map((n) => n.position.y + (n.measured?.height ?? 40)));
      const boxCx = (Math.min(...xs) + rightX) / 2;
      const boxCy = (Math.min(...ys) + bottomY) / 2;
      setFlowNodes((ns) =>
        ns.map((n) => {
          if (!ids.has(n.id)) return n;
          const w = n.measured?.width ?? 100;
          const h = n.measured?.height ?? 40;
          let { x, y } = n.position;
          if (mode === 'left') x = Math.min(...xs);
          else if (mode === 'right') x = rightX - w;
          else if (mode === 'centerX') x = boxCx - w / 2;
          else if (mode === 'top') y = Math.min(...ys);
          else if (mode === 'bottom') y = bottomY - h;
          else if (mode === 'centerY') y = boxCy - h / 2;
          return { ...n, position: { x, y } };
        })
      );
      saveBoard();
    },
    [setFlowNodes, snapshot, saveBoard]
  );

  const distributeSelected = useCallback(
    (mode: DistMode) => {
      const sel = selectedNodesRef.current;
      if (sel.length < 3) return;
      boardActionRef.current = true;
      snapshot();
      const sorted = [...sel].sort((a, b) => (mode === 'X' ? a.position.x - b.position.x : a.position.y - b.position.y));
      const sizes = sorted.map((n) => (mode === 'X' ? n.measured?.width ?? 100 : n.measured?.height ?? 40));
      const totalSpan = (mode === 'X' ? Math.max(...sorted.map((n) => n.position.x + (n.measured?.width ?? 100))) : Math.max(...sorted.map((n) => n.position.y + (n.measured?.height ?? 40)))) - (mode === 'X' ? sorted[0].position.x : sorted[0].position.y);
      const gap = (totalSpan - sizes.reduce((a, b) => a + b, 0)) / (sorted.length - 1);
      let cursor = mode === 'X' ? sorted[0].position.x : sorted[0].position.y;
      const posMap = new Map<string, { x: number; y: number }>();
      sorted.forEach((n, i) => {
        posMap.set(n.id, mode === 'X' ? { x: cursor, y: n.position.y } : { x: n.position.x, y: cursor });
        cursor += (sizes[i] ?? 0) + gap;
      });
      setFlowNodes((ns) => ns.map((n) => (posMap.has(n.id) ? { ...n, position: posMap.get(n.id)! } : n)));
      saveBoard();
    },
    [setFlowNodes, snapshot, saveBoard]
  );

  // ---------- 右键菜单 ----------
  const handleCtxMenu = useCallback((target: CtxTarget, id: string | null, x: number, y: number) => {
    setCtxMenu({ target, id, x, y });
  }, []);

  const buildCtxActions = useCallback(
    (m: CtxMenuState): CtxMenuAction[] => {
      if (!m) return [];
      if (m.target === 'node' && m.id) {
        const isImage = (nodesRef.current.find((x) => x.id === m.id)?.data as { src?: string })?.src !== undefined;
        const actions: CtxMenuAction[] = [];
        if (!isImage) actions.push({ label: '编辑文字', onClick: () => setSelNodeId(m.id) });
        actions.push(
          { label: '复制', onClick: () => handleCopyNode(m.id!) },
          { label: '粘贴', onClick: () => handlePaste() },
          { label: '置于顶层', onClick: () => setNodeZ(m.id!, 999) },
          { label: '置于底层', onClick: () => setNodeZ(m.id!, -1) },
          { label: '删除', danger: true, onClick: () => deleteNodeById(m.id!) }
        );
        return actions;
      }
      if (m.target === 'edge' && m.id) {
        return [
          { label: '编辑标签', onClick: () => setSelEdgeId(m.id) },
          { label: '删除连线', danger: true, onClick: () => deleteEdgeById(m.id!) },
        ];
      }
      return [
        { label: '粘贴', onClick: () => handlePaste() },
        { label: '全选', onClick: () => setFlowNodes((ns) => ns.map((n) => ({ ...n, selected: true }))) },
        { label: '添加节点', onClick: () => handleAddNode() },
      ];
    },
    [handleCopyNode, handlePaste, setNodeZ, deleteNodeById, deleteEdgeById, handleAddNode, setFlowNodes]
  );

  // ---------- 生成 ----------
  const handleGenerate = async () => {
    if (!prompt.trim() || generating) return;
    setGenerating(true);
    setApiError('');
    setRenderError('');
    try {
      const result = await analyzeUml(prompt.trim(), diagramType);
      setMermaidCode(result.mermaid);
      const ok = applyParsedToBoard(result.mermaid);
      if (!ok) {
        setSvg('');
        setRenderError('');
        renderDiagram(result.mermaid);
      }
      setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 200);
    } catch (err) {
      setApiError(err instanceof Error ? err.message : '生成失败，请稍后重试');
    } finally {
      setGenerating(false);
    }
  };

  // ---------- 源码编辑 ----------
  const handleCodeEdit = (v: string) => {
    setMermaidCode(v);
    if (isBoardMode) {
      const ok = applyParsedToBoard(v);
      if (ok) boardActionRef.current = false;
      else renderDiagram(v);
    } else {
      renderDiagram(v);
    }
  };

  const copyCode = async () => {
    if (!mermaidCode) return;
    try {
      await navigator.clipboard.writeText(mermaidCode);
    } catch {
      /* ignore */
    }
  };

  const downloadMmd = () => {
    if (!mermaidCode) return;
    const blob = new Blob([mermaidCode], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `flowchart-${Date.now()}.mmd`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const downloadPng = () => {
    if (!svg) return;
    const blob = new Blob([svg], { type: 'image/svg+xml;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const img = new Image();
    img.onload = () => {
      const m = svg.match(/viewBox="([^"]+)"/);
      const vb = m ? m[1].split(' ').map(Number) : [0, 0, 800, 600];
      const canvas = document.createElement('canvas');
      canvas.width = vb[2];
      canvas.height = vb[3];
      const ctx = canvas.getContext('2d');
      if (ctx) {
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(img, 0, 0);
      }
      URL.revokeObjectURL(url);
      const a = document.createElement('a');
      a.href = canvas.toDataURL('image/png');
      a.download = `flowchart-${Date.now()}.png`;
      a.click();
    };
    img.onerror = () => URL.revokeObjectURL(url);
    img.src = url;
  };

  const hasResult = mermaidCode.trim().length > 0;
  const boardReady = isBoardMode && flowNodes.length > 0;

  return (
    <div className="uml-page">
      {/* 输入区 */}
      <div className="uml-input-card">
        <div className="uml-card-head">
          <span className="uml-card-title">生成流程图</span>
          <span className="uml-card-desc">描述你的需求，或直接粘贴代码，AI 将分析并生成 Mermaid 流程图</span>
        </div>
        <textarea
          className="uml-input"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder={'例如：\n用户登录流程：输入账号密码，校验通过进入首页，失败提示重试，连续失败 5 次锁定账号。\n\n或直接粘贴一段 Python / JS / Java 代码…'}
          rows={5}
        />
        <div className="uml-input-foot">
          <div className="uml-examples">
            {EXAMPLES.map((ex) => (
              <button key={ex.label} className="uml-example-btn" onClick={() => setPrompt(ex.text)}>
                {ex.label}
              </button>
            ))}
          </div>
          <div className="uml-actions">
            <select
              className="uml-select"
              value={diagramType}
              onChange={(e) => setDiagramType(e.target.value as UmlDiagramType)}
            >
              {DIAGRAM_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
            <button className="uml-generate-btn" onClick={handleGenerate} disabled={!prompt.trim() || generating}>
              {generating ? (
                <>
                  <span className="uml-spinner" />
                  分析生成中…
                </>
              ) : (
                '生成流程图'
              )}
            </button>
          </div>
        </div>
        {apiError && <div className="uml-error">{apiError}</div>}
      </div>

      {/* 结果区 */}
      {hasResult && (
        <div className="uml-result" ref={resultRef}>
          <div className="uml-toolbar">
            <span className="uml-toolbar-type">
              {DIAGRAM_OPTIONS.find((o) => o.value === diagramType)?.label}
              {isBoardMode && <span className="uml-toolbar-tag">可编辑画板</span>}
            </span>
            <div className="uml-toolbar-btns">
              {isBoardMode && boardReady && (
                <>
                  <button className="uml-tool-btn" onClick={handleAddNode} title="在画布中添加一个矩形节点">
                    + 节点
                  </button>
                  <button className="uml-tool-btn" onClick={undo} title="撤销 (Ctrl+Z)">
                    ↩ 撤销
                  </button>
                  <button className="uml-tool-btn" onClick={redo} title="重做 (Ctrl+Y)">
                    ↪ 重做
                  </button>
                  <label className="uml-snap-label" title="对齐网格">
                    <input type="checkbox" checked={snapToGrid} onChange={(e) => setSnapToGrid(e.target.checked)} />
                    网格
                  </label>
                  <button className="uml-tool-btn" onClick={() => exportBoard('png')} title="导出画板为 PNG 图片">
                    导出 PNG
                  </button>
                  <button className="uml-tool-btn" onClick={() => exportBoard('svg')} title="导出画板为 SVG 矢量图">
                    导出 SVG
                  </button>
                </>
              )}
              <button className="uml-tool-btn" onClick={copyCode} title="复制 Mermaid 源码">
                复制源码
              </button>
              <button className="uml-tool-btn" onClick={downloadMmd} title="下载 .mmd 源码文件">
                下载 .mmd
              </button>
              {!isBoardMode && (
                <button className="uml-tool-btn" onClick={downloadPng} title="导出为 PNG 图片">
                  导出 PNG
                </button>
              )}
            </div>
          </div>

          {renderError && <div className="uml-error">渲染错误：{renderError}</div>}

          {boardReady ? (
            <div className="uml-board">
              <ShapePalette onAdd={handleAddShape} />
                <div className="uml-canvas-fl" ref={boardRef}>
                  {/* 多选工具栏 */}
                {selectedNodes.length >= 2 && (
                  <div className="fl-selbar">
                    <span className="fl-selbar-count">{selectedNodes.length} 节点</span>
                    <button className="fl-selbar-btn" onClick={() => alignSelected('left')} title="左对齐">
                      ⬅ 左对齐
                    </button>
                    <button className="fl-selbar-btn" onClick={() => alignSelected('centerX')} title="水平居中">
                      ⬌ 居中
                    </button>
                    <button className="fl-selbar-btn" onClick={() => alignSelected('right')} title="右对齐">
                      右对齐 ➡
                    </button>
                    <button className="fl-selbar-btn" onClick={() => alignSelected('top')} title="顶部对齐">
                      ⬆ 顶对齐
                    </button>
                    <button className="fl-selbar-btn" onClick={() => alignSelected('centerY')} title="垂直居中">
                      ⬍ 垂直居中
                    </button>
                    <button className="fl-selbar-btn" onClick={() => alignSelected('bottom')} title="底部对齐">
                      底对齐 ⬇
                    </button>
                    <button className="fl-selbar-btn" onClick={() => distributeSelected('X')} title="水平等距分布">
                      ↔ 水平分布
                    </button>
                    <button className="fl-selbar-btn" onClick={() => distributeSelected('Y')} title="垂直等距分布">
                      ↕ 垂直分布
                    </button>
                  </div>
                )}
                <FlowCanvas
                  nodes={flowNodes}
                  edges={flowEdges}
                  snapToGrid={snapToGrid}
                  fitSignal={fitSignal}
                  onNodesChange={handleNodesChange}
                  onEdgesChange={handleEdgesChange}
                  onConnect={handleConnect}
                  onNodesDelete={handleNodesDelete}
                  onEdgesDelete={() => {
                    boardActionRef.current = true;
                  }}
                  onSelectionChange={handleSelectionChange}
                  onNodeDragStop={handleNodeDragStop}
                  onDropShape={handleDropShape}
                  onDropImage={handleDropImage}
                  onContextMenuRequest={handleCtxMenu}
                  onEdgeLabelEdit={handleEdgeLabelEdit}
                  onEdgePathChange={handleEdgePathChange}
                  onEdgePathEditStart={() => {
                    /* 拖动开始时无需额外处理 */
                  }}
                  onEdgePathEditEnd={handleEdgePathEditEnd}
                />
              </div>
              {ppTarget && (
                <PropertiesPanel
                  target={ppTarget}
                  node={nodePanelData}
                  edge={edgePanelData}
                  onChangeNode={(patch) => selNodeId && patchNode(selNodeId, patch)}
                  onChangeEdge={(patch) => selEdgeId && patchEdge(selEdgeId, patch)}
                  onDelete={handlePanelDelete}
                  onClose={() => {
                    setSelNodeId(null);
                    setSelEdgeId(null);
                  }}
                />
              )}
            </div>
          ) : (
            <div className="uml-panes">
              <div className="uml-canvas">
                {svg ? (
                  <div className="uml-canvas-svg" dangerouslySetInnerHTML={{ __html: svg }} />
                ) : (
                  <div className="uml-canvas-empty">图表渲染中…</div>
                )}
              </div>
              <div className="uml-editor">
                <div className="uml-editor-head">
                  Mermaid 源码
                  <span className="uml-editor-hint">编辑后自动重绘</span>
                </div>
                <textarea
                  className="uml-editor-textarea"
                  value={mermaidCode}
                  onChange={(e) => handleCodeEdit(e.target.value)}
                  spellCheck={false}
                />
              </div>
            </div>
          )}

          {isBoardMode && (
            <div className="uml-editor">
              <div className="uml-editor-head">
                Mermaid 源码
                <span className="uml-editor-hint">与画板双向同步，编辑后自动重绘</span>
              </div>
              <textarea
                className="uml-editor-textarea uml-editor-textarea-short"
                value={mermaidCode}
                onChange={(e) => handleCodeEdit(e.target.value)}
                spellCheck={false}
              />
            </div>
          )}
        </div>
      )}

      {/* 右键菜单 */}
      {ctxMenu && (
        <ContextMenu state={ctxMenu} actions={buildCtxActions(ctxMenu)} onClose={() => setCtxMenu(null)} />
      )}
    </div>
  );
}
