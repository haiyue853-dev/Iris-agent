/**
 * Mermaid flowchart 解析 / 序列化 / 布局工具。
 * 支持语法子集：
 *  - 方向：flowchart TD / LR / BT / RL、graph TD ...
 *  - 节点形状：[矩形] {菱形} ((圆形)) (圆角) [[子程序]] [(圆柱)]
 *  - 连线：-->、-- 文本 -->、-->|文本|、---、-.->、==>
 *  - 注释：%% 开头行
 * 暂不支持：subgraph、& 并行、样式类。
 */

export type FlowShape =
  | 'rect'
  | 'round'
  | 'diamond'
  | 'circle'
  | 'subroutine'
  | 'cylinder'
  | 'parallelogram'
  | 'note'
  | 'actor';
export type FlowDirection = 'TD' | 'LR' | 'BT' | 'RL';

export type ParsedNode = { id: string; label: string; shape: FlowShape };
export type ParsedEdge = { source: string; target: string; label?: string };

export type ParsedFlowchart = {
  direction: FlowDirection;
  nodes: ParsedNode[];
  edges: ParsedEdge[];
};

export type LayoutedNode = ParsedNode & { x: number; y: number };

// 形状的显示名（画板属性面板/形状库用）
export const SHAPE_NAMES: Record<FlowShape, string> = {
  rect: '矩形',
  round: '圆角矩形',
  diamond: '菱形（判断）',
  circle: '圆形（起止）',
  subroutine: '子程序',
  cylinder: '圆柱（数据）',
  parallelogram: '平行四边形（输入/出）',
  note: '便签',
  actor: '角色',
};

// ---------------- 解析 ----------------

const SHAPE_PATTERNS: [RegExp, FlowShape][] = [
  [/\[\[(.+?)\]\]/s, 'subroutine'],
  [/\[\/(.+?)\/\]/s, 'parallelogram'],
  [/\[\((.+?)\)\]/s, 'cylinder'],
  [/\[(.+?)\]/s, 'rect'],
  [/\{(.+?)\}/s, 'diamond'],
  [/\(\((.+?)\)\)/s, 'circle'],
  [/\((.+?)\)/s, 'round'],
];

const EDGE_TOKEN = /(?:-->|---|-.->|==>)/;

/** 解析单个 "id[text]" 或裸 "id" 节点声明，返回 null 若无法匹配 */
function parseNodeDecl(seg: string): ParsedNode | null {
  const m = seg.match(/([A-Za-z0-9_\u4e00-\u9fa5]+)\s*(\[\[.+?\]\]|\[.+?\]|\{.+?\}|\(\(.+?\)\)|\[\(.+?\)\]|\(.+?\))/s);
  if (m) {
    const id = m[1];
    const body = m[2];
    for (const [re, shape] of SHAPE_PATTERNS) {
      const sm = body.match(re);
      if (sm) {
        return { id, label: sm[1].trim(), shape };
      }
    }
  }
  // 裸 ID（已在其他行定义过的节点引用）
  const idOnly = seg.match(/^([A-Za-z0-9_\u4e00-\u9fa5]+)$/);
  if (idOnly) return { id: idOnly[1], label: '', shape: 'rect' };
  return null;
}

/** 把 "A -- 文本 --> B" 归一化为 "A -->|文本| B" 便于统一解析 */
function normalizeEdgeLabels(line: string): string {
  return line.replace(/--\s+([^->]+?)\s+-->/g, '-->|$1|');
}

/** 解析一行（可含链式连线 A --> B --> C） */
function parseLine(line: string, fc: ParsedFlowchart, nodeById: Map<string, ParsedNode>) {
  const segs = line.split(EDGE_TOKEN);
  const edges = line.match(new RegExp(EDGE_TOKEN.source, 'g')) || [];
  // 每个连接符后的段首可能带 |label|，按边索引对齐提取
  const labels = segs.slice(1).map((s) => {
    const lm = s.match(/^\|(.+?)\|\s*/);
    return lm ? lm[1].trim() : undefined;
  });
  const cleaned = segs
    .map((s, i) => (i > 0 ? s.replace(/^\|(.+?)\|\s*/, '') : s))
    .map((s) => s.trim())
    .filter(Boolean);
  // 段数 = 边数 + 1（链式）
  if (cleaned.length !== edges.length + 1) return;

  const parsedSegs = cleaned.map((s) => parseNodeDecl(s));
  for (let i = 0; i < parsedSegs.length; i++) {
    const p = parsedSegs[i];
    if (!p) return; // 本行含无法解析的内容，跳过整行
    const exist = nodeById.get(p.id);
    if (exist) {
      if (!exist.label && p.label) exist.label = p.label;
      // 之前是裸 ID（默认 rect、无 label），后续带形状声明时补全形状
      if (exist.label === '' && exist.shape === 'rect' && p.shape !== 'rect') {
        exist.shape = p.shape;
      }
    } else {
      nodeById.set(p.id, p);
      fc.nodes.push(p);
    }
  }
  for (let i = 0; i < edges.length; i++) {
    const src = parsedSegs[i];
    const dst = parsedSegs[i + 1];
    if (!src || !dst) continue;
    fc.edges.push({ source: src.id, target: dst.id, label: labels[i] });
  }
}

/** 解析 mermaid flowchart 源码 */
export function parseMermaidFlowchart(code: string): ParsedFlowchart {
  const fc: ParsedFlowchart = { direction: 'TD', nodes: [], edges: [] };
  const nodeById = new Map<string, ParsedNode>();

  const lines = code
    .split('\n')
    .map((l) => l.replace(/%%.*$/, '').trim())
    .filter(Boolean);

  for (const raw of lines) {
    // 方向声明
    const dm = raw.match(/^(?:flowchart|graph)\s+(TD|LR|BT|RL)\b/i);
    if (dm) {
      fc.direction = dm[1].toUpperCase() as FlowDirection;
      continue;
    }
    if (/^(?:flowchart|graph)\b/i.test(raw)) continue; // 无方向声明行
    parseLine(normalizeEdgeLabels(raw), fc, nodeById);
  }
  return fc;
}

// ---------------- 布局 ----------------

const NODE_W = 200;
const NODE_H = 64;
const GAP_X = 80;
const GAP_Y = 90;

/** 基于 BFS 的简单分层布局（不依赖外部库） */
export function layoutFlowchart(fc: ParsedFlowchart): LayoutedNode[] {
  const indeg = new Map<string, number>();
  const children = new Map<string, string[]>();
  for (const n of fc.nodes) {
    indeg.set(n.id, 0);
    children.set(n.id, []);
  }
  for (const e of fc.edges) {
    indeg.set(e.target, (indeg.get(e.target) || 0) + 1);
    children.get(e.source)?.push(e.target);
  }
  // 根：入度为 0 的节点；若无则从第一个节点开始
  let roots = fc.nodes.filter((n) => (indeg.get(n.id) || 0) === 0);
  if (roots.length === 0 && fc.nodes.length > 0) roots = [fc.nodes[0]];

  const layerOf = new Map<string, number>();
  const queue: { id: string; layer: number }[] = roots.map((n) => ({ id: n.id, layer: 0 }));
  let qi = 0;
  while (qi < queue.length) {
    const cur = queue[qi++];
    if (!layerOf.has(cur.id)) layerOf.set(cur.id, cur.layer);
    for (const c of children.get(cur.id) || []) {
      const l = cur.layer + 1;
      if (!layerOf.has(c)) queue.push({ id: c, layer: l });
    }
  }
  // 未遍历到的孤立节点放最后层
  for (const n of fc.nodes) {
    if (!layerOf.has(n.id)) layerOf.set(n.id, (fc.nodes.length > 0 ? Math.max(...layerOf.values(), 0) : 0) + 1);
  }

  // 每层节点列
  const layers = new Map<number, string[]>();
  for (const [id, layer] of layerOf) {
    if (!layers.has(layer)) layers.set(layer, []);
    layers.get(layer)!.push(id);
  }
  const sortedLayers = [...layers.keys()].sort((a, b) => a - b);

  const pos = new Map<string, { x: number; y: number }>();
  for (const layer of sortedLayers) {
    const ids = layers.get(layer)!;
    ids.forEach((id, i) => {
      const span = ids.length;
      const x = ((i + 1) * (NODE_W + GAP_X * 2)) / (span + 1) - NODE_W / 2;
      const y = layer * (NODE_H + GAP_Y);
      pos.set(id, { x, y });
    });
  }

  // 孤立节点排布到末层下方
  const orphanIds = fc.nodes.filter((n) => !pos.has(n.id)).map((n) => n.id);
  const baseY = (sortedLayers.length || 1) * (NODE_H + GAP_Y);
  orphanIds.forEach((id, i) => {
    const x = ((i + 1) * (NODE_W + GAP_X * 2)) / (orphanIds.length + 1) - NODE_W / 2;
    pos.set(id, { x, y: baseY });
  });

  return fc.nodes.map((n) => {
    const p = pos.get(n.id) || { x: 0, y: 0 };
    return { ...n, x: p.x, y: p.y };
  });
}

// ---------------- 序列化 ----------------

/** 节点自定义样式（画板属性面板可改；mermaid 序列化为 style 行） */
export type NodeStyle = {
  fill?: string;
  border?: string;
  textColor?: string;
  fontSize?: number;
  borderStyle?: 'solid' | 'dashed';
  width?: number;
  height?: number;
};

export const DEFAULT_NODE_STYLE: Required<Omit<NodeStyle, 'width' | 'height'>> = {
  fill: '#ffffff',
  border: '#d5d5dc',
  textColor: '#1d1c23',
  fontSize: 13.5,
  borderStyle: 'solid',
};

export type SerializableNode = { id: string; label: string; shape: FlowShape; style?: NodeStyle };

function shapeMark(shape: FlowShape): [string, string] {
  switch (shape) {
    case 'rect':
      return ['[', ']'];
    case 'diamond':
      return ['{', '}'];
    case 'circle':
      return ['((', '))'];
    case 'round':
      return ['(', ')'];
    case 'subroutine':
      return ['[[', ']]'];
    case 'cylinder':
      return ['[(', ')]'];
    case 'parallelogram':
      return ['[/', '/]'];
    case 'note':
    case 'actor':
      return ['[', ']']; // mermaid 无便签/角色形状，映射为矩形
  }
}

/** 节点序列化为 mermaid 声明（无 label 时输出裸 ID） */
export function nodeDecl(n: ParsedNode): string {
  const [open, close] = shapeMark(n.shape);
  return n.label ? `${n.id}${open}${n.label}${close}` : n.id;
}

/** 把 React Flow 的 nodes/edges 序列化回 mermaid flowchart 源码（含样式） */
export function serializeFlowchart(
  nodes: SerializableNode[],
  edges: { source: string; target: string; label?: string }[],
  direction: FlowDirection
): string {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const lines: string[] = [`flowchart ${direction}`];
  const connected = new Set<string>();
  for (const e of edges) {
    const s = byId.get(e.source);
    const t = byId.get(e.target);
    if (!s || !t) continue;
    connected.add(s.id);
    connected.add(t.id);
    const label = e.label ? `-->|${e.label}|` : '-->';
    lines.push(`${nodeDecl(s)} ${label} ${nodeDecl(t)}`);
  }
  // 孤立节点
  for (const n of nodes) {
    if (!connected.has(n.id)) lines.push(nodeDecl(n));
  }
  // 样式行（非默认样式才输出）
  for (const n of nodes) {
    const st = n.style;
    if (!st) continue;
    const parts: string[] = [];
    if (st.fill && st.fill.toLowerCase() !== DEFAULT_NODE_STYLE.fill) parts.push(`fill:${st.fill}`);
    if (st.border && st.border.toLowerCase() !== DEFAULT_NODE_STYLE.border) parts.push(`stroke:${st.border}`);
    if (st.textColor && st.textColor.toLowerCase() !== DEFAULT_NODE_STYLE.textColor) parts.push(`color:${st.textColor}`);
    if (st.fontSize && st.fontSize !== DEFAULT_NODE_STYLE.fontSize) parts.push(`font-size:${st.fontSize}px`);
    if (st.borderStyle && st.borderStyle !== 'solid') parts.push('stroke-dasharray:6 4');
    if (parts.length > 0) lines.push(`    style ${n.id} ${parts.join(',')}`);
  }
  return lines.join('\n');
}
