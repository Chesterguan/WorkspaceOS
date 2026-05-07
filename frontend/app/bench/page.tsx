'use client';

import { Suspense } from 'react';
import { useRouter } from 'next/navigation';
import { BenchLayout } from '@/components/bench/BenchLayout';
import { Rail } from '@/components/bench/Rail';
import { useBenchState } from '@/lib/bench/useBenchState';

/**
 * Inner component separated so useSearchParams (called inside useBenchState)
 * is scoped to a Suspense boundary — required by Next.js 16 to avoid
 * prerendering build failures (see docs: use-search-params#prerendering).
 */
function BenchContent() {
  const router = useRouter();
  const { state, update } = useBenchState();

  return (
    <BenchLayout
      rail={
        <Rail
          active={state.surface}
          onSelect={(id) => update({ surface: id })}
          onPaletteOpen={() => { /* Task 11 */ }}
          onSettingsOpen={() => router.push('/settings')}
        />
      }
      inspector={null}
      main={
        <div className="p-6 text-sm text-muted-foreground">
          surface: <span className="text-foreground font-medium">{state.surface}</span> ·
          project: <span className="text-foreground font-medium">{state.projectId ?? 'all'}</span>
        </div>
      }
      log={
        <div className="p-2 text-xs text-muted-foreground font-mono">events</div>
      }
    />
  );
}

export default function BenchPage() {
  return (
    <Suspense fallback={null}>
      <BenchContent />
    </Suspense>
  );
}
