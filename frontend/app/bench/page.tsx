'use client';

import { Suspense } from 'react';
import { useRouter } from 'next/navigation';
import { BenchLayout } from '@/components/bench/BenchLayout';
import { Rail } from '@/components/bench/Rail';
import { ProjectFilter } from '@/components/bench/ProjectFilter';
import { useBenchState } from '@/lib/bench/useBenchState';
import { SURFACE_INDEX } from '@/lib/bench/surfaces';
import { RoundtableSurface } from '@/components/bench/surfaces/RoundtableSurface';
import { DraftsSurface } from '@/components/bench/surfaces/DraftsSurface';
import { PapersSurface } from '@/components/bench/surfaces/PapersSurface';
import { KnowledgeSurface } from '@/components/bench/surfaces/KnowledgeSurface';
import { WorklogSurface } from '@/components/bench/surfaces/WorklogSurface';
import { ProjectInspector } from '@/components/bench/ProjectInspector';

/**
 * Inner component separated so useSearchParams (called inside useBenchState)
 * is scoped to a Suspense boundary — required by Next.js 16 to avoid
 * prerendering build failures (see docs: use-search-params#prerendering).
 */
function BenchContent() {
  const router = useRouter();
  const { state, update } = useBenchState();
  const surface = SURFACE_INDEX[state.surface];

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
      inspector={
        state.projectId && state.inspectorOpen ? (
          <ProjectInspector
            projectId={state.projectId}
            onClose={() => update({ inspectorOpen: false })}
          />
        ) : null
      }
      main={
        <>
          <header className="flex items-center justify-between border-b border-border/60 px-6 py-3">
            <h1 className="text-lg font-semibold">{surface.label}</h1>
            <ProjectFilter
              projectId={state.projectId}
              onChange={(id) => update({ projectId: id })}
              onNewProject={() => { /* Task 12 */ }}
            />
          </header>
          <div className="flex-1 min-h-0 flex flex-col">
            {state.surface === 'r' && (
              <RoundtableSurface
                projectId={state.projectId}
                mode={state.mode}
                onModeChange={(m) => update({ mode: m })}
              />
            )}
            {state.surface === 'd' && <DraftsSurface projectId={state.projectId} />}
            {state.surface === 'p' && <PapersSurface projectId={state.projectId} />}
            {state.surface === 'k' && <KnowledgeSurface projectId={state.projectId} />}
            {state.surface === 'w' && <WorklogSurface projectId={state.projectId} />}
          </div>
        </>
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
