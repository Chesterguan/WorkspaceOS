'use client';

import { useEffect } from 'react';
import { X } from 'lucide-react';
import Link from 'next/link';

interface Props {
  onClose: () => void;
}

export function PortfolioOverlay({ onClose }: Props) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-40 bg-background flex flex-col">
      <header className="flex items-center justify-between border-b border-border/60 px-6 py-3">
        <h1 className="text-lg font-semibold">Portfolio</h1>
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
        <div className="text-sm text-muted-foreground space-y-3">
          <p>The combined multi-project portfolio view lives at the existing route for now.</p>
          <Link
            href="/portfolio"
            className="inline-block rounded-md bg-primary/80 px-3 py-1.5 text-xs text-primary-foreground hover:bg-primary"
          >
            Open portfolio
          </Link>
          <p className="text-xs text-muted-foreground/80">
            A future task will embed the portfolio view directly in this overlay.
          </p>
        </div>
      </div>
    </div>
  );
}
