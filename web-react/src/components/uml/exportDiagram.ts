import type { Node, Edge } from '@xyflow/react';
import type { FlowNodeData } from './FlowNode';
import type { FlowShape } from './mermaidParser';

/** 手绘 SVG 导出（零依赖）：根据画板数据生成干净的高质量 SVG 图表 */

const PAD = 40;

function escapeXml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function wrapText(label: string, maxChars: number): string[] {
  const lines: string[] = [];
  let cur = '';
  for (const ch of label) {
    if (cur.length >= maxChars) {
      lines.push(cur);
      cur = ch;
    } else {
      cur += ch;
    }
  }
  if (cur) lines.push(cur);
  return lines.slice(0, 4);
}

function nodeShapeEl(shape: FlowShape, x: number, y: number, w: number, h: number, fill: string, stroke: string): string {
  const cx = x + w / 2;
  const cy = y + h / 2;
  const sw = 1.5;
  switch (shape) {
    case 'round':
      return `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${h / 2}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}"/>`;
    case 'circle':
      return `<ellipse cx="${cx}" cy="${cy}" rx="${w / 2}" ry="${h / 2}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}"/>`;
    case 'diamond':
      return `<polygon points="${cx},${y} ${x + w},${cy} ${cx},${y + h} ${x},${cy}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}"/>`;
    case 'parallelogram':
      return `<polygon points="${x + w * 0.14},${y} ${x + w},${y} ${x + w * 0.86},${y + h} ${x},${y + h}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}"/>`;
    case 'subroutine': {
      const inset = w * 0.18;
      return `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="4" fill="${fill}" stroke="${stroke}" stroke-width="${sw}"/><path d="M${x + inset},${y}V${y + h}M${x + w - inset},${y}V${y + h}" fill="none" stroke="${stroke}" stroke-width="${sw}"/>`;
    }
    case 'cylinder': {
      const ry = Math.min(11, h * 0.18);
      return `<ellipse cx="${cx}" cy="${y + ry}" rx="${w / 2}" ry="${ry}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}"/><rect x="${x}" y="${y + ry}" width="${w}" height="${h - ry * 2}" fill="${fill}"/><path d="M${x},${y + ry}V${y + h - ry}M${x + w},${y + ry}V${y + h - ry}" fill="none" stroke="${stroke}" stroke-width="${sw}"/><ellipse cx="${cx}" cy="${y + h - ry}" rx="${w / 2}" ry="${ry}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}"/>`;
    }
    case 'note': {
      const fold = 15;
      return `<path d="M${x},${y}H${x + w - fold}L${x + w},${y + fold}V${y + h}H${x}Z" fill="${fill}" stroke="${stroke}" stroke-width="${sw}"/><path d="M${x + w - fold},${y}V${y + fold}H${x + w}" fill="none" stroke="${stroke}" stroke-width="${sw}"/>`;
    }
    case 'actor':
      return `<ellipse cx="${cx}" cy="${cy}" rx="${w / 2}" ry="${h / 2}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}"/>`;
    case 'rect':
    default:
      return `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="6" fill="${fill}" stroke="${stroke}" stroke-width="${sw}"/>`;
  }
}

/** 正交直角路径点集（与画板 step 边一致：始终横平竖直，不产生斜线） */
function stepPoints(sx: number, sy: number, tx: number, ty: number, vertical: boolean): [number, number][] {
  if (Math.abs(sx - tx) < 1 || Math.abs(sy - ty) < 1) return [[sx, sy], [tx, ty]];
  if (vertical) {
    const midY = (sy + ty) / 2;
    return [[sx, sy], [sx, midY], [tx, midY], [tx, ty]];
  }
  const midX = (sx + tx) / 2;
  return [[sx, sy], [midX, sy], [midX, ty], [tx, ty]];
}

/** 根据画板数据生成 SVG 字符串 */
export function buildDiagramSvg(nodes: Node[], edges: Edge[]): string {
  if (nodes.length === 0) return '';
  const direction = ((nodes[0].data as FlowNodeData | undefined)?.direction as 'TD' | 'LR' | 'BT' | 'RL') || 'TD';
  const vertical = direction === 'TD' || direction === 'BT';

  const xs = nodes.map((n) => n.position.x);
  const ys = nodes.map((n) => n.position.y);
  const wOf = (n: Node): number => n.measured?.width ?? (n.data as { width?: number }).width ?? 120;
  const hOf = (n: Node): number => n.measured?.height ?? (n.data as { height?: number }).height ?? 44;
  const rights = nodes.map((n) => n.position.x + wOf(n));
  const bottoms = nodes.map((n) => n.position.y + hOf(n));
  const minX = Math.min(...xs) - PAD;
  const minY = Math.min(...ys) - PAD;
  const width = Math.max(...rights) + PAD - minX;
  const height = Math.max(...bottoms) + PAD - minY;

  const defs: string[] = [];
  const edgeEls: string[] = [];
  for (const e of edges) {
    const s = nodes.find((n) => n.id === e.source);
    const t = nodes.find((n) => n.id === e.target);
    if (!s || !t) continue;
    const sw = s.measured?.width ?? 120;
    const sh = s.measured?.height ?? 44;
    const tw = t.measured?.width ?? 120;
    const th = t.measured?.height ?? 44;
    const sCx = s.position.x + sw / 2;
    const tCx = t.position.x + tw / 2;
    const sx = vertical ? sCx : s.position.x + sw;
    const sy = vertical ? s.position.y + sh : s.position.y + sh / 2;
    const tx = vertical ? tCx : t.position.x;
    const ty = vertical ? t.position.y : t.position.y + th / 2;

    const lx = sx - minX;
    const ly = sy - minY;
    const px = tx - minX;
    const py = ty - minY;
    const custom = (e.data as { points?: { x: number; y: number }[] } | undefined)?.points;
    const points = custom && custom.length >= 2
      ? custom.map((p) => [p.x - minX, p.y - minY] as [number, number])
      : stepPoints(lx, ly, px, py, vertical);

    const color = ((e.style as { stroke?: string } | undefined)?.stroke as string) || '#8a8a92';
    const widthN = Number((e.style as { strokeWidth?: number } | undefined)?.strokeWidth) || 1.6;
    const dash = (e.style as { strokeDasharray?: string } | undefined)?.strokeDasharray;
    const markerId = `arr-${e.id}`;
    defs.push(`<marker id="${markerId}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto-start-reverse"><path d="M0,0L10,5L0,10z" fill="${color}"/></marker>`);
    const pts = points.map(([a, b]) => `${Math.round(a * 10) / 10},${Math.round(b * 10) / 10}`).join(' ');
    edgeEls.push(
      `<polyline points="${pts}" fill="none" stroke="${color}" stroke-width="${widthN}" ${dash ? `stroke-dasharray="${dash}"` : ''} marker-end="url(#${markerId})"/>`
    );
    if (e.label) {
      const midX = (lx + px) / 2;
      const midY = (ly + py) / 2;
      edgeEls.push(
        `<text x="${midX}" y="${midY}" text-anchor="middle" dominant-baseline="middle" fill="${color}" font-size="11.5" font-family="PingFang SC, Microsoft YaHei, sans-serif"><tspan dx="0">${escapeXml(String(e.label))}</tspan></text>`
      );
    }
  }

  const nodeEls: string[] = [];
  for (const n of nodes) {
    const imgData = n.data as { src?: string; width?: number; height?: number };
    if (imgData.src) {
      const w = imgData.width ?? 200;
      const h = imgData.height ?? 150;
      const x = n.position.x - minX;
      const y = n.position.y - minY;
      nodeEls.push(`<image x="${x}" y="${y}" width="${w}" height="${h}" href="${escapeXml(imgData.src)}" preserveAspectRatio="xMidYMid meet"/>`);
      continue;
    }
    const d = n.data as FlowNodeData;
    const w = n.measured?.width ?? 120;
    const h = n.measured?.height ?? 44;
    const x = n.position.x - minX;
    const y = n.position.y - minY;
    const cx = x + w / 2;
    const cy = y + h / 2;
    const style = d.style || {};
    const fill = style.fill || '#ffffff';
    const stroke = style.border || '#d5d5dc';
    const color = style.textColor || '#1d1c23';
    const fs = style.fontSize ?? 13.5;
    const shapeEl = nodeShapeEl(d.shape, x, y, w, h, fill, stroke);

    const lines = wrapText(d.label, Math.max(2, Math.floor((w - 18) / fs)));
    const lineH = fs * 1.4;
    const tspans = lines
      .map((ln, i) => `<tspan x="${cx}" y="${i === 0 ? cy - ((lines.length - 1) * lineH) / 2 : lineH}">${escapeXml(ln)}</tspan>`)
      .join('');
    nodeEls.push(
      `${shapeEl}<text x="${cx}" y="${cy}" text-anchor="middle" dominant-baseline="middle" fill="${color}" font-size="${fs}" font-weight="600" font-family="PingFang SC, Microsoft YaHei, sans-serif">${tspans}</text>`
    );
  }

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${Math.round(width)}" height="${Math.round(height)}" viewBox="0 0 ${Math.round(width)} ${Math.round(height)}"><rect width="100%" height="100%" fill="#ffffff"/><defs>${defs.join('')}</defs>${edgeEls.join('')}${nodeEls.join('')}</svg>`;
}
