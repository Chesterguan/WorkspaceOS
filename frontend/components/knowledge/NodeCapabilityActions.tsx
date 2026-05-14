'use client';

// Renders the dynamic action_button capabilities that target
// `knowledge_node`. Each button:
//   - is gated by the manifest's `visible_when` against the node
//   - POSTs to /capabilities/actions/<name>/invoke on click
//   - displays the handler's returned `toast` message on success
//   - calls onChanged() so the surrounding view can refetch

import { useState } from 'react';
import { toast } from 'sonner';
import {
  actionVisible,
  invokeAction,
  useItemActions,
  type ActionButtonEntry,
} from '@/lib/capabilities';
import type { KnowledgeNode } from '@/lib/types';

interface Props {
  node: KnowledgeNode;
  onChanged: () => void;
}

export function NodeCapabilityActions({ node, onChanged }: Props) {
  const { data: actions = [] } = useItemActions('knowledge_node');
  const visible = actions.filter((a) =>
    actionVisible(a.visible_when as Record<string, unknown>, node as unknown as Record<string, unknown>),
  );
  if (visible.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-2">
      {visible.map((action) => (
        <ActionButton key={action.id} action={action} node={node} onChanged={onChanged} />
      ))}
    </div>
  );
}

function ActionButton({
  action, node, onChanged,
}: {
  action: ActionButtonEntry;
  node: KnowledgeNode;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);

  async function handleClick() {
    setBusy(true);
    try {
      const result = await invokeAction(action.name, { target_id: node.id });
      const t = (result as Record<string, unknown>).toast;
      if (typeof t === 'string') toast.success(t);
      else if ((result as Record<string, unknown>).ok) toast.success(`${action.label} ✓`);
      onChanged();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <button
      disabled={busy}
      onClick={handleClick}
      title={`${action.label} (from ${action.source_extension})`}
      className="text-xs px-2 py-1 rounded border border-violet-500/40 bg-violet-500/10 text-violet-200 hover:bg-violet-500/20 disabled:opacity-50 transition-colors"
    >
      {action.label}
    </button>
  );
}
