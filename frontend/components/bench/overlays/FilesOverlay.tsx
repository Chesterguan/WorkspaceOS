'use client';

import { useEffect } from 'react';
import Link from 'next/link';
import { X } from 'lucide-react';

interface Props {
  projectId: string | undefined;
  onClose: () => void;
}

export function FilesOverlay({ projectId, onClose }: Props) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-40 bg-background flex flex-col"
      role="dialog"
      aria-modal="true"
      aria-labelledby="overlay-title"
    >
      <header className="flex items-center justify-between border-b border-border/60 px-6 py-3">
        <h1 id="overlay-title" className="text-lg font-semibold">Files</h1>
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
            <p>Project files for this project. Inline upload + list coming in a future task.</p>
            <Link
              href={`/projects/${projectId}/files`}
              className="inline-block rounded-md bg-primary/80 px-3 py-1.5 text-xs text-primary-foreground hover:bg-primary"
            >
              Open files (classic view)
            </Link>
          </div>
        ) : (
          <div className="text-sm text-muted-foreground">
            Pick a project to see its files. Cross-project Files view is a future task.
          </div>
        )}
      </div>
    </div>
  );
}
