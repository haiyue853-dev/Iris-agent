export type MindMapNode = {
  id: string;
  parent_id: string | null;
  label: string;
  summary: string;
  kind: 'root' | 'branch' | 'point';
  ordinal: number;
  evidence_chunk_ids: string[];
};

export default function DocumentMindMap({ nodes, onOpenEvidence }: { nodes: MindMapNode[]; onOpenEvidence: (chunkIds: string[]) => void }) {
  const root = nodes.find((node) => node.parent_id === null);
  if (!root) return <p className="knowledge-empty">这份资料还没有生成思维导图，请重新索引。</p>;
  const childrenOf = (id: string) => nodes.filter((node) => node.parent_id === id).sort((left, right) => left.ordinal - right.ordinal);
  return (
    <div className="document-mindmap" role="tree" aria-label="文档思维导图">
      <article className="mindmap-root" role="treeitem" aria-level={1}>
        <strong>{root.label}</strong>
        {root.summary && <p>{root.summary}</p>}
      </article>
      <div className="mindmap-branches" role="group">
        {childrenOf(root.id).map((branch) => (
          <section className="mindmap-branch" key={branch.id} role="treeitem" aria-level={2}>
            <button className="mindmap-node-title" onClick={() => branch.evidence_chunk_ids.length && onOpenEvidence(branch.evidence_chunk_ids)}>{branch.label}</button>
            {branch.summary && <p>{branch.summary}</p>}
            <div className="mindmap-points" role="group">
              {childrenOf(branch.id).map((point) => (
                <article className="mindmap-point" key={point.id} role="treeitem" aria-level={3}>
                  <button className="mindmap-node-title" onClick={() => point.evidence_chunk_ids.length && onOpenEvidence(point.evidence_chunk_ids)}>{point.label}</button>
                  {point.summary && <p>{point.summary}</p>}
                  {point.evidence_chunk_ids.length > 0 && <button className="mindmap-evidence" aria-label={`查看“${point.label}”的原文证据`} onClick={() => onOpenEvidence(point.evidence_chunk_ids)}>查看原文</button>}
                </article>
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
