'use client';

import { useState } from 'react';
import { Bookmark } from 'lucide-react';
import { PromoteModal } from './PromoteModal';
import type { SourceRef } from '@/lib/types';

interface Props {
  text: string;
  rect: DOMRect | null;
  sourceKind: string;       // e.g. 'paper', 'draft', 'file_ingest'
  sourceId?: string;
  projectId?: string;
  onSaved?: () => void;
}

/**
 * Floating "Save as knowledge" button anchored to a text-selection rect.
 *
 * Renders nothing when rect is null (no selection). When the user clicks
 * the button, opens the PromoteModal prefilled with the selection.
 */
export function SelectionPromoteOverlay({
  text, rect, sourceKind, sourceId, projectId, onSaved,
}: Props) {
  const [open, setOpen] = useState(false);

  const source: SourceRef = {
    kind: sourceKind,
    id: sourceId,
    excerpt: text.slice(0, 200),
  };

  if (!rect) return null;

  // Position the button just above the selection's top edge.
  // Clamp to viewport so it never goes off-screen on tiny windows.
  const style: React.CSSProperties = {
    position: 'fixed',
    top: Math.max(8, rect.top - 40),
    left: Math.max(8, Math.min(window.innerWidth - 200, rect.left)),
    zIndex: 40,
  };

  return (
    <>
      <button
        type="button"
        onMouseDown={(e) => {
          // Prevent the click from clearing the selection before we read it.
          e.preventDefault();
        }}
        onClick={() => setOpen(true)}
        style={style}
        className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md bg-primary text-primary-foreground text-xs font-medium shadow-lg hover:opacity-90 transition"
      >
        <Bookmark className="w-3.5 h-3.5" />
        Save as knowledge
      </button>
      <PromoteModal
        open={open}
        source={source}
        projectId={projectId}
        defaultExcerpt={text}
        onClose={() => setOpen(false)}
        onSaved={onSaved}
      />
    </>
  );
}
