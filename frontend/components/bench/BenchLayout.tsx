'use client';

import { ReactNode, useState } from 'react';
import { MessageSquare } from 'lucide-react';

interface BenchLayoutProps {
  rail: ReactNode;
  inspector: ReactNode | null;
  main: ReactNode;
  log: ReactNode;
}

/**
 * Four-column bench layout (desktop): rail | inspector | main | log
 *
 * Responsive collapse:
 *   < md (768px):  rail + inspector hidden; main full-width; log behind a
 *                  floating "Show events" button that opens it as a sheet.
 *   md..lg:        rail + inspector + main visible; log hidden behind sheet.
 *   >= lg (1024px): all four columns visible.
 */
export function BenchLayout({ rail, inspector, main, log }: BenchLayoutProps) {
  const [logOpen, setLogOpen] = useState(false);

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground">
      <div className="hidden md:block w-12 shrink-0 border-r border-border/60 bg-card/30">
        {rail}
      </div>

      {inspector && (
        <div className="hidden md:block w-60 shrink-0 border-r border-border/60 bg-card/20 overflow-y-auto animate-in slide-in-from-left-4 duration-200">
          {inspector}
        </div>
      )}

      <div className="flex-1 min-w-0 flex flex-col">{main}</div>

      <div className="hidden lg:block w-[32%] shrink-0 border-l border-border/60 bg-[#0a0a0a]">
        {log}
      </div>

      {/* Mobile/tablet floating button to open log as a sheet */}
      <button
        type="button"
        onClick={() => setLogOpen(true)}
        className="fixed bottom-4 right-4 z-30 lg:hidden rounded-full border border-border bg-card p-3 shadow-lg hover:bg-card/80"
        aria-label="Show events"
      >
        <MessageSquare className="h-5 w-5" />
      </button>

      {logOpen && (
        <div
          className="fixed inset-0 z-40 lg:hidden bg-black/40 animate-in fade-in-0 duration-150"
          onClick={() => setLogOpen(false)}
        >
          <div
            className="absolute bottom-0 left-0 right-0 h-[60vh] bg-[#0a0a0a] border-t border-border animate-in slide-in-from-bottom-4 duration-200"
            onClick={(e) => e.stopPropagation()}
          >
            {log}
          </div>
        </div>
      )}
    </div>
  );
}
