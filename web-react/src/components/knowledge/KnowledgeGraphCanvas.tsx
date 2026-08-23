import { useEffect, useMemo, useState } from 'react';
import { SigmaContainer, useLoadGraph, useRegisterEvents, useSigma } from '@react-sigma/core';
import { UndirectedGraph } from 'graphology';
import '@react-sigma/core/lib/style.css';

export type GraphNode = { id: string; label: string; kind: string; document_count: number };
export type GraphEdge = { source: string; target: string; relation: string };

function GraphLoader({ nodes, edges, onSelect }: { nodes: GraphNode[]; edges: GraphEdge[]; onSelect: (id: string) => void }) {
  const loadGraph = useLoadGraph(); const sigma = useSigma(); const registerEvents = useRegisterEvents();
  const [dragged, setDragged] = useState<string | null>(null);
  const graph = useMemo(() => {
    const value = new UndirectedGraph();
    nodes.forEach((node, index) => { const angle = index * Math.PI * 2 / Math.max(nodes.length, 1); const radius = node.kind === 'topic' ? 0.1 : .38 + (index % 3) * .08; value.addNode(node.id, { label: node.label, x: .5 + Math.cos(angle) * radius, y: .5 + Math.sin(angle) * radius, size: node.kind === 'topic' ? 17 : 8 + Math.min(node.document_count, 4), color: node.kind === 'topic' ? '#171717' : '#f8f8f8', borderColor: '#171717' }); });
    edges.forEach((edge, index) => { if (value.hasNode(edge.source) && value.hasNode(edge.target) && !value.hasEdge(edge.source, edge.target)) value.addEdgeWithKey(`edge-${index}`, edge.source, edge.target, { label: edge.relation, color: '#a3a3a3', size: 1 }); });
    return value;
  }, [nodes, edges]);
  useEffect(() => { loadGraph(graph); sigma.getCamera().animatedReset(); }, [graph, loadGraph, sigma]);
  useEffect(() => { registerEvents({ clickNode: ({ node }) => onSelect(node), downNode: ({ node }) => setDragged(node), mousemovebody: (event) => { if (!dragged) return; const position = sigma.viewportToGraph(event); sigma.getGraph().setNodeAttribute(dragged, 'x', position.x); sigma.getGraph().setNodeAttribute(dragged, 'y', position.y); event.preventSigmaDefault(); }, mouseup: () => setDragged(null) }); }, [dragged, onSelect, registerEvents, sigma]);
  return null;
}

export default function KnowledgeGraphCanvas({ nodes, edges, onSelect }: { nodes: GraphNode[]; edges: GraphEdge[]; onSelect: (id: string) => void }) {
  return <div className="knowledge-sigma"><SigmaContainer settings={{ renderEdgeLabels: false, defaultEdgeColor: '#a3a3a3', defaultNodeColor: '#f8f8f8', labelColor: { color: '#262626' }, labelRenderedSizeThreshold: 7, defaultNodeType: 'circle', zIndex: true }}><GraphLoader nodes={nodes} edges={edges} onSelect={onSelect} /></SigmaContainer></div>;
}
