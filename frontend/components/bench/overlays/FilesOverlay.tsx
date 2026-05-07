'use client';

import { useEffect } from 'react';
import { X } from 'lucide-react';
import Link from 'next/link';

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
    <div className="fixed inset-0 z-40 bg-background flex flex-col">
      <header className="flex items-center justify-between border-b border-border/60 px-6 py-3">
        <h1 className="text-lg font-semibold">Files</h1>
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
            <p>The file inbox UI for this project lives at the existing route for now.</p>
            <Link
              href={`/projects/${projectId}/files`}
              className="inline-block rounded-md bg-primary/80 px-3 py-1.5 text-xs text-primary-foreground hover:bg-primary"
            >
              Open project files
            </Link>
            <p className="text-xs text-muted-foreground/80">
              A future task will embed file listing + upload directly in this overlay.
            </p>
          </div>
        ) : (
          <div className="text-sm text-muted-foreground">
            Pick a project (in the bench header) to see its files. Cross-project Files view is a future task.
          </div>
        )}
      </div>
    </div>
  );
}
