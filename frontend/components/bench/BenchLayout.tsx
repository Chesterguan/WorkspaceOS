'use client';

import { ReactNode } from 'react';

interface BenchLayoutProps {
  rail: ReactNode;
  inspector: ReactNode | null;
  main: ReactNode;
  log: ReactNode;
}

/**
 * Four-column bench layout:
 *   [rail 48px] [inspector 240px conditional] [main flex] [log 32%]
 *
 * Inspector is null when no project is filtered — that column simply
 * doesn't render and the main area widens.
 */
export function BenchLayout({ rail, inspector, main, log }: BenchLayoutProps) {
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground">
      <div className="w-12 shrink-0 border-r border-border/60 bg-card/30">{rail}</div>
      {inspector && (
        <div className="w-60 shrink-0 border-r border-border/60 bg-card/20 overflow-y-auto">
          {inspector}
        </div>
      )}
      <div className="flex-1 min-w-0 flex flex-col">{main}</div>
      <div className="w-[32%] shrink-0 border-l border-border/60 bg-[#0a0a0a]">{log}</div>
    </div>
  );
}
