'use client';

import { BenchLayout } from '@/components/bench/BenchLayout';

export default function BenchPage() {
  return (
    <BenchLayout
      rail={<div className="text-xs text-muted-foreground p-2">rail</div>}
      inspector={null}
      main={
        <div className="p-6 text-sm text-muted-foreground">
          Bench main area (skeleton)
        </div>
      }
      log={
        <div className="p-2 text-xs text-muted-foreground font-mono">events</div>
      }
    />
  );
}
