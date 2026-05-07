'use client';

import { useEffect } from 'react';
import { X } from 'lucide-react';
import Link from 'next/link';

interface Props {
  projectId: string | undefined;
  onClose: () => void;
}

export function MemoryOverlay({ projectId, onClose }: Props) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-40 bg-background flex flex-col">
      <header className="flex items-center justify-between border-b border-border/60 px-6 py-3">
        <h1 className="text-lg font-semibold">Memory</h1>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="text-muted-foreground hover:text-foreground"
        >
          <X className="h-5 w-5" />
        </button>
      </header>
      <div className="flex-1 overflow-y-auto p-6">
        {projectId ? (
          <div className="text-sm text-muted-foreground space-y-3">
            <p>Raw memory entries (the evidence behind Knowledge nodes) for this project.</p>
            <Link
              href={`/projects/${projectId}/memory`}
              className="inline-block rounded-md bg-primary/80 px-3 py-1.5 text-xs text-primary-foreground hover:bg-primary"
            >
              Open project memory
            </Link>
          </div>
        ) : (
          <div className="text-sm text-muted-foreground">
            Pick a project to see its memory entries.
          </div>
        )}
      </div>
    </div>
  );
}
