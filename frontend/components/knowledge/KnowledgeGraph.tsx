'use client';

import { useEffect, useMemo } from 'react';
import {
  Background, Controls, ReactFlow,
  type Edge, type Node, useEdgesState, useNodesState,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import dagre from 'dagre';
import useSWR from 'swr';
import { knowledge } from '@/lib/api';
import type { KnowledgeNode, KnowledgeEdge } from '@/lib/types';
import { edgeStyle, nodeColor, useKnowledgeTaxonomy } from '@/lib/knowledge-style';

const NODE_W = 220;
const NODE_H = 70;

interface Props {
  nodes: KnowledgeNode[];
  onSelect: (n: KnowledgeNode) => void;
}

function layout(nodes: Node[], edges: Edge[]): Node[] {
  if (!nodes.length) return [];
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: 'TB', nodesep: 40, ranksep: 60 });
  nodes.forEach((n) => g.setNode(n.id, { width: NODE_W, height: NODE_H }));
  edges.forEach((e) => g.setEdge(e.source, e.target));
  dagre.layout(g);
  return nodes.map((n) => {
    const p = g.node(n.id);
    return { ...n, position: { x: p.x - NODE_W / 2, y: p.y - NODE_H / 2 } };
  });
}

export function KnowledgeGraph({ nodes, onSelect }: Props) {
  const taxonomy = useKnowledgeTaxonomy();

  // Fetch edges where BOTH endpoints are visible — keyed by sorted ids
  // so SWR cache hits when the same set of nodes is shown.
  const idKey = useMemo(
    () => [...nodes.map((n) => n.id)].sort().join(','),
    [nodes],
  );

  const { data: edgeData } = useSWR<KnowledgeEdge[]>(
    nodes.length ? ['knowledge/edges', idKey] : null,
    () => knowledge.listEdgesForNodes(nodes.map((n) => n.id)),
  );

  const initialNodes: Node[] = useMemo(
    () =>
      nodes.map((n) => ({
        id: n.id,
        data: { label: <NodeLabel node={n} /> },
        position: { x: 0, y: 0 },
        style: {
          background: 'white',
          border: `2px solid ${nodeColor(taxonomy, n.node_type)}`,
          borderRadius: 8,
          padding: 8,
          width: NODE_W,
        },
      })),
    [nodes, taxonomy],
  );

  const initialEdges: Edge[] = useMemo(() => {
    const all = edgeData ?? [];
    return all.map((e) => {
      const style = edgeStyle(taxonomy, e.edge_type);
      return {
        id: e.id,
        source: e.source_node_id,
        target: e.target_node_id,
        label: e.edge_type,
        style: {
          stroke: style.stroke,
          strokeDasharray: style.dashed ? '4 4' : undefined,
        },
      };
    });
  }, [edgeData, taxonomy]);

  // React Flow 12 type-tightness workaround: useNodesState([]) infers never[],
  // but useNodesState<Node>([]) causes NodeChange callback mismatches.
  // Using typed empty-array casts avoids both problems.
  const [rfNodes, setRfNodes, onNodesChange] = useNodesState([] as Node[]);
  const [rfEdges, setRfEdges, onEdgesChange] = useEdgesState([] as Edge[]);

  useEffect(() => {
    setRfNodes(layout(initialNodes, initialEdges));
  }, [initialNodes, initialEdges, setRfNodes]);

  useEffect(() => {
    setRfEdges(initialEdges);
  }, [initialEdges, setRfEdges]);

  if (!nodes.length) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-sm text-muted-foreground gap-2 px-6 text-center">
        <p>No knowledge nodes yet.</p>
        <p>
          Click <span className="font-medium text-foreground">New</span> to create one,
          or save a decision/claim from a roundtable conversation using the bookmark icon
          on any advisor reply.
        </p>
      </div>
    );
  }

  return (
    <ReactFlow
      nodes={rfNodes}
      edges={rfEdges}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onNodeClick={(_, n) => {
        const found = nodes.find((x) => x.id === n.id);
        if (found) onSelect(found);
      }}
      fitView
    >
      <Background />
      <Controls />
    </ReactFlow>
  );
}

function NodeLabel({ node }: { node: KnowledgeNode }) {
  return (
    <div className="text-xs text-left">
      <div className="font-medium truncate">{node.title}</div>
      <div className="opacity-70 truncate">{node.node_type}</div>
    </div>
  );
}
