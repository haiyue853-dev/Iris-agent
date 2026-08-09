import { memo, useEffect, useRef, useState } from 'react';
import { BaseEdge, EdgeLabelRenderer, Position, useReactFlow, type EdgeProps } from '@xyflow/react';

/** 正交直角路径点集（与画板 step 边一致：始终横平竖直，不产生斜线） */
function stepPoints(sx: number, sy: number, tx: number, ty: number, sp: Position, tp: Position): { x: number; y: number }[] {
  if (Math.abs(sx - tx) < 1 || Math.abs(sy - ty) < 1) return [{ x: sx, y: sy }, { x: tx, y: ty }];
  if (sp === Position.Right && tp === Position.Left) {
    const midX = (sx + tx) / 2;
    return [{ x: sx, y: sy }, { x: midX, y: sy }, { x: midX, y: ty }, { x: tx, y: ty }];
  }
  const midY = (sy + ty) / 2;
  return [{ x: sx, y: sy }, { x: sx, y: midY }, { x: tx, y: midY }, { x: tx, y: ty }];
}

function ptsToPath(pts: { x: number; y: number }[]): string {
  return pts.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x},${p.y}`).join(' ');
}

/** 正交拐点移动：拖点沿前段垂直方向自由移动，并联动后一点，保证整条路径横平竖直 */
function orthoMove(base: { x: number; y: number }[], i: number, mx: number, my: number): { x: number; y: number }[] {
  const next = base.map((p) => ({ ...p }));
  const prev = next[i - 1];
  const cur = next[i];
  const after = next[i + 1];
  if (!prev || !cur) return next;
  const prevIsVertical = Math.abs(prev.x - cur.x) < Math.abs(prev.y - cur.y);
  if (prevIsVertical) {
    // 前段竖直：本点 x 与前点对齐，y 跟随鼠标；后一点 y 联动
    cur.x = prev.x;
    cur.y = my;
    if (after) after.y = my;
  } else {
    // 前段水平：本点 y 与前点对齐，x 跟随鼠标；后一点 x 联动
    cur.y = prev.y;
    cur.x = mx;
    if (after) after.x = mx;
  }
  return next;
}

type FlowEdgeData = {
  points?: { x: number; y: number }[];
  onLabelEdit?: (edgeId: string, label: string) => void;
  onPathChange?: (edgeId: string, pts: { x: number; y: number }[]) => void;
  onPathEditStart?: (edgeId: string) => void;
  onPathEditEnd?: (edgeId: string) => void;
};

function FlowEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  markerEnd,
  style,
  label,
  labelStyle,
  labelBgStyle,
  data,
  selected,
}: EdgeProps) {
  const { screenToFlowPosition } = useReactFlow();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(typeof label === 'string' ? label : '');
  const [dragPts, setDragPts] = useState<{ x: number; y: number }[] | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const dragIdxRef = useRef<number | null>(null);
  const dragPtsRef = useRef<{ x: number; y: number }[] | null>(null);

  const d = data as FlowEdgeData | undefined;
  const onLabelEdit = d?.onLabelEdit;
  const onPathChange = d?.onPathChange;
  const onPathEditStart = d?.onPathEditStart;
  const onPathEditEnd = d?.onPathEditEnd;

  useEffect(() => {
    if (editing) {
      setDraft(typeof label === 'string' ? label : '');
      setTimeout(() => {
        inputRef.current?.focus();
        inputRef.current?.select();
      }, 0);
    }
  }, [editing, label]);

  const commit = () => {
    const v = draft.trim();
    if (onLabelEdit) onLabelEdit(id, v);
    setEditing(false);
  };

  // 自定义路径（有拐点）或自动路径
  const autoPts = stepPoints(sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition);
  const pts = d?.points && d.points.length >= 2 ? d.points : autoPts;
  const currentPts = dragPts ?? pts;
  const path = ptsToPath(currentPts);
  const midX = (sourceX + targetX) / 2;
  const midY = (sourceY + targetY) / 2;

  const onHandleDown = (e: React.PointerEvent, index: number) => {
    e.stopPropagation();
    e.preventDefault();
    dragIdxRef.current = index;
    const base = dragPtsRef.current ?? pts;
    dragPtsRef.current = base;
    setDragPts(base);
    onPathEditStart?.(id);
    (e.target as Element).setPointerCapture?.(e.pointerId);
  };

  const onHandleMove = (e: React.PointerEvent) => {
    const idx = dragIdxRef.current;
    if (idx === null) return;
    const pos = screenToFlowPosition({ x: e.clientX, y: e.clientY });
    const base = dragPtsRef.current ?? pts;
    const next = orthoMove(base, idx, pos.x, pos.y);
    dragPtsRef.current = next;
    setDragPts(next);
  };

  const onHandleUp = () => {
    const idx = dragIdxRef.current;
    if (idx === null) return;
    dragIdxRef.current = null;
    const finalPts = dragPtsRef.current ?? pts;
    onPathChange?.(id, finalPts);
    dragPtsRef.current = null;
    setDragPts(null);
    onPathEditEnd?.(id);
  };

  // 拐点手柄（选中边时显示）
  const knobs = selected ? currentPts.slice(1, -1) : [];

  return (
    <>
      <path d={path} fill="none" stroke="transparent" strokeWidth={26} style={{ pointerEvents: 'stroke', cursor: 'pointer' }} />
      <BaseEdge id={id} path={path} markerEnd={markerEnd} style={style} />
      <EdgeLabelRenderer>
        {editing ? (
          <div className="fl-edge-edit" style={{ transform: `translate(-50%, -50%) translate(${midX}px, ${midY}px)` }}>
            <input
              ref={inputRef}
              className="fl-edge-edit-input"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onBlur={commit}
              onKeyDown={(e) => {
                if (e.key === 'Enter') commit();
                if (e.key === 'Escape') setEditing(false);
              }}
            />
          </div>
        ) : (
          label !== undefined && label !== '' && (
            <div
              className="fl-edge-label"
              style={{
                transform: `translate(-50%, -50%) translate(${midX}px, ${midY}px)`,
                ...(labelBgStyle as object),
                ...(labelStyle as object),
              }}
              onDoubleClick={(e) => {
                e.stopPropagation();
                setEditing(true);
              }}
              title="双击编辑标签"
            >
              {label}
            </div>
          )
        )}
        {/* 拐点拖拽手柄（选中边时显示） */}
        {knobs.length > 0 &&
          currentPts.slice(1, -1).map((p, i) => (
            <div
              key={`${p.x}-${p.y}-${i}`}
              className="fl-edge-knob"
              style={{ transform: `translate(-50%, -50%) translate(${p.x}px, ${p.y}px)` }}
              onPointerDown={(e) => onHandleDown(e, i + 1)}
              onPointerMove={onHandleMove}
              onPointerUp={onHandleUp}
              title="拖动调整拐点"
            />
          ))}
      </EdgeLabelRenderer>
    </>
  );
}

export default memo(FlowEdge);
