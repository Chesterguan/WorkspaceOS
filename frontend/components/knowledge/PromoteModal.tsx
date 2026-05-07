'use client';

import { useState, useEffect, useRef } from 'react';
import { knowledge } from '@/lib/api';
import type { NodeType, SourceRef } from '@/lib/types';
import { NODE_TYPE_LABELS } from '@/lib/knowledge-style';

const TYPES: NodeType[] = [
  'claim', 'decision', 'question', 'hypothesis',
  'rejection', 'blocker', 'insight',
];

interface Props {
  open: boolean;
  source: SourceRef;
  projectId?: string | null;
  defaultExcerpt?: string;
  onClose: () => void;
  onSaved?: () => void;
}

export function PromoteModal({
  open, source, projectId, defaultExcerpt, onClose, onSaved,
}: Props) {
  const [type, setType] = useState<NodeType>('insight');
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset form only on the open false→true transition, not on every
  // defaultExcerpt change while the modal is already open. Without this,
  // clicking into the Title input (which clears the text selection →
  // defaultExcerpt becomes '') would wipe whatever the user had typed.
  const prevOpen = useRef(false);

  useEffect(() => {
    if (open && !prevOpen.current) {
      setType('insight');
      setTitle((defaultExcerpt ?? '').slice(0, 80).replace(/\s+/g, ' ').trim());
      setContent(defaultExcerpt ?? '');
      setError(null);
    }
    prevOpen.current = open;
  }, [open, defaultExcerpt]);

  // Close on Escape — WAI-ARIA modal contract (aria-modal="true" implies this)
  useEffect(() => {
    if (!open) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [open, onClose]);

  if (!open) return null;

  const submit = async () => {
    if (!title.trim() || !content.trim()) {
      setError('Title and content are required');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await knowledge.promote({
        project_id: projectId ?? undefined,
        source,
        suggested_type: type,
        title: title.trim().slice(0, 160),
        content: content.trim(),
      });
      onSaved?.();
      onClose();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Save failed';
      setError(msg);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="bg-card rounded-lg p-6 w-[480px] max-w-[90vw] space-y-4 border shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold">Save as knowledge</h2>

        <label className="block text-sm">
          <span className="block mb-1 font-medium">Type</span>
          <select
            value={type}
            onChange={(e) => setType(e.target.value as NodeType)}
            className="w-full p-2 rounded border bg-background"
          >
            {TYPES.map((t) => (
              <option key={t} value={t}>{NODE_TYPE_LABELS[t]}</option>
            ))}
          </select>
        </label>

        <label className="block text-sm">
          <span className="block mb-1 font-medium">Title</span>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={160}
            className="w-full p-2 rounded border bg-background"
          />
          <span className="text-xs text-muted-foreground">{title.length}/160</span>
        </label>

        <label className="block text-sm">
          <span className="block mb-1 font-medium">Content</span>
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            className="w-full p-2 rounded border bg-background h-24 resize-y"
          />
        </label>

        {error && (
          <div className="text-sm text-red-600 bg-red-50 dark:bg-red-950/30 px-2 py-1 rounded">
            {error}
          </div>
        )}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            className="px-3 py-1.5 rounded border text-sm disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={busy || !title.trim() || !content.trim()}
            className="px-3 py-1.5 rounded bg-primary text-primary-foreground text-sm disabled:opacity-50"
          >
            {busy ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}
