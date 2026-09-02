import { useEffect, useMemo, useState } from 'react';
import { SigmaContainer, useLoadGraph, useRegisterEvents, useSigma } from '@react-sigma/core';
import { UndirectedGraph } from 'graphology';
import '@react-sigma/core/lib/style.css';

export type GraphNode = { id: string; label: string; kind: string; document_count: number };
export type GraphEdge = { source: string; target: string; relation: string; document_id?: string; confidence?: number; evidence?: string | null; evidence_chunk_id?: string | null };

function GraphLoader({ nodes, edges, onSelect, onSelectEdge, activeNodeId, storageKey }: { nodes: GraphNode[]; edges: GraphEdge[]; onSelect: (id: string) => void; onSelectEdge: (edge: GraphEdge) => void; activeNodeId: string | null; storageKey: string }) {
  const loadGraph = useLoadGraph(); const sigma = useSigma(); const registerEvents = useRegisterEvents();
  const [dragged, setDragged] = useState<string | null>(null);
  const graph = useMemo(() => {
    const value = new UndirectedGraph();
    let saved: Record<string, { x: number; y: number }> = {};
    try { saved = JSON.parse(localStorage.getItem(`iris_graph_layout_${storageKey}`) || '{}'); } catch { saved = {}; }
    const neighbors = new Set(edges.filter((edge) => edge.source === activeNodeId || edge.target === activeNodeId).flatMap((edge) => [edge.source, edge.target]));
    nodes.forEach((node, index) => { const angle = index * Math.PI * 2 / Math.max(nodes.length, 1); const radius = node.kind === 'topic' ? 0.1 : .38 + (index % 3) * .08; const focused = !activeNodeId || node.id === activeNodeId || neighbors.has(node.id); const position = saved[node.id]; value.addNode(node.id, { label: node.label, x: position?.x ?? .5 + Math.cos(angle) * radius, y: position?.y ?? .5 + Math.sin(angle) * radius, size: node.id === activeNodeId ? 22 : node.kind === 'topic' ? 17 : 8 + Math.min(node.document_count, 4), color: focused ? (node.kind === 'topic' ? '#171717' : '#f8f8f8') : '#e5e5e5', borderColor: node.id === activeNodeId ? '#000000' : '#171717' }); });
    edges.forEach((edge, index) => { if (value.hasNode(edge.source) && value.hasNode(edge.target) && !value.hasEdge(edge.source, edge.target)) value.addEdgeWithKey(`edge-${index}`, edge.source, edge.target, { label: edge.relation, color: '#a3a3a3', size: 1, data: edge }); });
    return value;
  }, [nodes, edges, activeNodeId, storageKey]);
  useEffect(() => { loadGraph(graph); sigma.getCamera().animatedReset(); }, [graph, loadGraph, sigma]);
  useEffect(() => { registerEvents({ clickNode: ({ node }) => onSelect(node), clickEdge: ({ edge }) => onSelectEdge(sigma.getGraph().getEdgeAttribute(edge, 'data') as GraphEdge), downNode: ({ node }) => setDragged(node), mousemovebody: (event) => { if (!dragged) return; const position = sigma.viewportToGraph(event); sigma.getGraph().setNodeAttribute(dragged, 'x', position.x); sigma.getGraph().setNodeAttribute(dragged, 'y', position.y); event.preventSigmaDefault(); }, mouseup: () => { setDragged(null); const positions: Record<string, { x: number; y: number }> = {}; sigma.getGraph().forEachNode((id, attributes) => { positions[id] = { x: attributes.x, y: attributes.y }; }); try { localStorage.setItem(`iris_graph_layout_${storageKey}`, JSON.stringify(positions)); } catch { /* storage is optional */ } } }); }, [dragged, onSelect, onSelectEdge, registerEvents, sigma, storageKey]);
  return null;
}

export default function KnowledgeGraphCanvas({ nodes, edges, onSelect, onSelectEdge, activeNodeId, storageKey }: { nodes: GraphNode[]; edges: GraphEdge[]; onSelect: (id: string) => void; onSelectEdge: (edge: GraphEdge) => void; activeNodeId: string | null; storageKey: string }) {
  return <div className="knowledge-sigma"><SigmaContainer settings={{ renderEdgeLabels: false, defaultEdgeColor: '#a3a3a3', defaultNodeColor: '#f8f8f8', labelColor: { color: '#262626' }, labelRenderedSizeThreshold: 7, defaultNodeType: 'circle', zIndex: true }}><GraphLoader nodes={nodes} edges={edges} onSelect={onSelect} onSelectEdge={onSelectEdge} activeNodeId={activeNodeId} storageKey={storageKey} /></SigmaContainer></div>;
}
