'use client';

// NodeLinksPanel — shows outgoing + incoming typed edges for a knowledge node,
// and provides a "Link to…" modal to create new edges.

import { useState } from 'react';
import { toast } from 'sonner';
import { Link2, Plus, X } from 'lucide-react';
import { knowledge } from '@/lib/api';
import { useNodeLinks } from '@/lib/hooks/useKnowledge';
import { useKnowledgeTaxonomy } from '@/lib/knowledge-style';
import type { KnowledgeNode, LinkedEdge } from '@/lib/types';

// Canonical edge type list — mirrors the backend's _CANONICAL_EDGE_TYPES.
const EDGE_TYPES = [
  'supports',
  'refutes',
  'tests',
  'derived_from',
  'derives_from',
  'rejects',
  'related_to',
  'cites',
] as const;

interface Props {
  node: KnowledgeNode;
  /** All nodes available in the current view — used for the link picker search. */
  allNodes: KnowledgeNode[];
  /** Called when the node graph should re-fetch (e.g. after a new link is added). */
  onChanged: () => void;
  /** Navigates the graph view to a different node. */
  onSelectNode: (node: KnowledgeNode) => void;
}

export function NodeLinksPanel({ node, allNodes, onChanged, onSelectNode }: Props) {
  const { data: links, mutate } = useNodeLinks(node.id);
  const taxonomy = useKnowledgeTaxonomy();
  const [showModal, setShowModal] = useState(false);

  const refresh = () => {
    mutate();
    onChanged();
  };

  const handleDelete = async (edgeId: string) => {
    try {
      await knowledge.deleteEdge(edgeId);
      toast.success('Link removed');
      refresh();
    } catch (err) {
      toast.error((err as Error).message ?? 'Failed to remove link');
    }
  };

  const nodeLabel = (nodeType: string) => {
    const nt = taxonomy?.node_types.find((t) => t.id === nodeType);
    return nt?.label ?? nodeType;
  };

  return (
    <div className="mt-3 pt-3 border-t border-border/40">
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-1 text-[10px] font-medium text-muted-foreground uppercase tracking-wide">
          <Link2 size={11} />
          Links
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded border border-border/60 hover:bg-accent/30 transition-colors"
          title="Link to another node"
        >
          <Plus size={10} />
          Link to…
        </button>
      </div>

      {(!links || (links.outgoing.length === 0 && links.incoming.length === 0)) && (
        <p className="text-[11px] text-muted-foreground italic">No links yet.</p>
      )}

      {links && links.outgoing.length > 0 && (
        <div className="mb-2">
          <div className="text-[10px] text-muted-foreground mb-1">Outgoing</div>
          <div className="flex flex-col gap-1">
            {links.outgoing.map((le) => (
              <LinkedEdgeRow
                key={le.edge.id}
                linkedEdge={le}
                nodeLabel={nodeLabel}
                onSelect={onSelectNode}
                onDelete={handleDelete}
              />
            ))}
          </div>
        </div>
      )}

      {links && links.incoming.length > 0 && (
        <div>
          <div className="text-[10px] text-muted-foreground mb-1">Incoming</div>
          <div className="flex flex-col gap-1">
            {links.incoming.map((le) => (
              <LinkedEdgeRow
                key={le.edge.id}
                linkedEdge={le}
                nodeLabel={nodeLabel}
                onSelect={onSelectNode}
                onDelete={handleDelete}
              />
            ))}
          </div>
        </div>
      )}

      {showModal && (
        <LinkPickerModal
          sourceNode={node}
          allNodes={allNodes}
          onClose={() => setShowModal(false)}
          onCreated={refresh}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// LinkedEdgeRow — one pill in the linked-nodes list
// ---------------------------------------------------------------------------

function LinkedEdgeRow({
  linkedEdge,
  nodeLabel,
  onSelect,
  onDelete,
}: {
  linkedEdge: LinkedEdge;
  nodeLabel: (t: string) => string;
  onSelect: (n: KnowledgeNode) => void;
  onDelete: (edgeId: string) => void;
}) {
  const { edge, node } = linkedEdge;
  return (
    <div className="flex items-center gap-1 text-xs group">
      <span className="px-1.5 py-0.5 rounded bg-accent/30 text-[10px] font-mono shrink-0">
        {edge.edge_type}
      </span>
      <button
        onClick={() => onSelect(node)}
        className="flex-1 text-left truncate hover:underline text-sm"
        title={node.title}
      >
        <span className="text-[10px] text-muted-foreground mr-1">
          [{nodeLabel(node.node_type)}]
        </span>
        {node.title}
      </button>
      <button
        onClick={() => onDelete(edge.id)}
        className="opacity-0 group-hover:opacity-60 hover:!opacity-100 text-destructive transition-opacity shrink-0"
        title="Remove link"
      >
        <X size={12} />
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// LinkPickerModal — inline modal to create a new edge
// ---------------------------------------------------------------------------

interface ModalProps {
  sourceNode: KnowledgeNode;
  allNodes: KnowledgeNode[];
  onClose: () => void;
  onCreated: () => void;
}

function LinkPickerModal({ sourceNode, allNodes, onClose, onCreated }: ModalProps) {
  const [query, setQuery] = useState('');
  const [edgeType, setEdgeType] = useState<string>(EDGE_TYPES[0]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Exclude the source node itself from the picker.
  const filtered = allNodes.filter(
    (n) =>
      n.id !== sourceNode.id &&
      n.title.toLowerCase().includes(query.toLowerCase()),
  );

  const handleCreate = async () => {
    if (!selectedId) return;
    setBusy(true);
    try {
      await knowledge.createEdge({
        source_node_id: sourceNode.id,
        target_node_id: selectedId,
        edge_type: edgeType,
      });
      toast.success('Link created');
      onCreated();
      onClose();
    } catch (err) {
      const msg = (err as Error).message;
      if (msg?.includes('409') || msg?.toLowerCase().includes('already exists')) {
        toast.error('Link already exists');
      } else {
        toast.error(msg ?? 'Failed to create link');
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    // Backdrop
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      {/* Modal card — stop propagation so clicks inside don't dismiss */}
      <div
        className="bg-card border rounded-lg shadow-xl p-4 w-80 max-h-[70vh] flex flex-col gap-3"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <span className="text-sm font-semibold">Link to…</span>
          <button onClick={onClose} className="opacity-60 hover:opacity-100">
            <X size={14} />
          </button>
        </div>

        {/* Edge type picker */}
        <div>
          <label className="text-[10px] text-muted-foreground uppercase tracking-wide block mb-1">
            Edge type
          </label>
          <select
            value={edgeType}
            onChange={(e) => setEdgeType(e.target.value)}
            className="w-full text-xs rounded border bg-background px-2 py-1 focus:outline-none focus:ring-1 focus:ring-ring"
          >
            {EDGE_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>

        {/* Node search */}
        <div>
          <label className="text-[10px] text-muted-foreground uppercase tracking-wide block mb-1">
            Target node
          </label>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search nodes…"
            className="w-full text-xs rounded border bg-background px-2 py-1 focus:outline-none focus:ring-1 focus:ring-ring"
            autoFocus
          />
        </div>

        {/* Results list */}
        <div className="flex-1 overflow-y-auto max-h-48 flex flex-col gap-0.5">
          {filtered.length === 0 && (
            <p className="text-[11px] text-muted-foreground italic px-1">
              {allNodes.length <= 1 ? 'No other nodes available.' : 'No matches.'}
            </p>
          )}
          {filtered.map((n) => (
            <button
              key={n.id}
              onClick={() => setSelectedId(n.id === selectedId ? null : n.id)}
              className={`text-left text-xs px-2 py-1 rounded transition-colors ${
                selectedId === n.id
                  ? 'bg-primary/20 text-primary font-medium'
                  : 'hover:bg-accent/30'
              }`}
            >
              <span className="text-[10px] text-muted-foreground mr-1">[{n.node_type}]</span>
              {n.title}
            </button>
          ))}
        </div>

        {/* Create button */}
        <button
          disabled={!selectedId || busy}
          onClick={handleCreate}
          className="w-full text-sm py-1.5 rounded bg-primary text-primary-foreground disabled:opacity-40 hover:opacity-90 transition-opacity"
        >
          {busy ? 'Creating…' : 'Create link'}
        </button>
      </div>
    </div>
  );
}
