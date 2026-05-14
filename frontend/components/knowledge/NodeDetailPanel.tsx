'use client';

import { useState } from 'react';
import { toast } from 'sonner';
import { knowledge } from '@/lib/api';
import type { KnowledgeNode } from '@/lib/types';
import { nodeColor, nodeLabel, useKnowledgeTaxonomy } from '@/lib/knowledge-style';
import { NodeCapabilityActions } from '@/components/knowledge/NodeCapabilityActions';

interface Props {
  node: KnowledgeNode;
  onClose: () => void;
  onChanged: () => void;
}

export function NodeDetailPanel({ node, onClose, onChanged }: Props) {
  const [busy, setBusy] = useState(false);
  const taxonomy = useKnowledgeTaxonomy();

  const archive = async () => {
    setBusy(true);
    try {
      await knowledge.updateNode(node.id, { archived: !node.archived });
      onChanged();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Archive failed';
      toast.error(msg);
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!confirm('Delete this node?')) return;
    setBusy(true);
    try {
      await knowledge.deleteNode(node.id);
      onChanged();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Delete failed';
      toast.error(msg);
    } finally {
      setBusy(false);
    }
  };

  return (
    <aside className="border-t p-4 max-h-72 overflow-auto bg-card">
      <div className="flex items-start justify-between gap-4">
        <div>
          <span
            className="inline-block px-2 py-0.5 rounded text-xs text-white"
            style={{ background: nodeColor(taxonomy, node.node_type) }}
          >
            {nodeLabel(taxonomy, node.node_type)}
          </span>
          <h2 className="text-lg font-semibold mt-1">{node.title}</h2>
        </div>
        <button
          onClick={onClose}
          className="text-sm opacity-60 hover:opacity-100"
        >
          close
        </button>
      </div>
      <p className="mt-2 text-sm whitespace-pre-wrap">{node.content}</p>

      <div className="mt-3 text-xs opacity-70">
        Created {new Date(node.created_at).toLocaleString()} · {node.created_by}
      </div>

      {node.source_refs.length > 0 && (
        <div className="mt-2 text-xs">
          <div className="font-medium opacity-80">Sources</div>
          <ul className="list-disc pl-4">
            {node.source_refs.map((s, i) => (
              <li key={i}>
                {s.kind}
                {s.id ? ` · ${s.id.slice(0, 8)}` : ''}
                {s.note ? ` — ${s.note}` : ''}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-3 flex flex-wrap gap-2">
        <button
          disabled={busy}
          onClick={archive}
          className="text-sm px-2 py-1 rounded border disabled:opacity-50"
        >
          {node.archived ? 'Unarchive' : 'Archive'}
        </button>
        <button
          disabled={busy}
          onClick={remove}
          className="text-sm px-2 py-1 rounded border text-red-600 disabled:opacity-50"
        >
          Delete
        </button>
      </div>

      {/* Dynamic action_button capabilities from extensions */}
      <div className="mt-3 pt-3 border-t border-border/40">
        <div className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide mb-1.5">
          Extension actions
        </div>
        <NodeCapabilityActions node={node} onChanged={onChanged} />
      </div>
    </aside>
  );
}
