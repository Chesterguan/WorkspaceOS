'use client';

import { Suspense, useState } from 'react';
import { useRouter } from 'next/navigation';
import { CommandPalette } from '@/components/bench/CommandPalette';
import { BenchLayout } from '@/components/bench/BenchLayout';
import { Rail } from '@/components/bench/Rail';
import { ProjectFilter } from '@/components/bench/ProjectFilter';
import { NewProjectModal } from '@/components/bench/NewProjectModal';
import { useBenchState } from '@/lib/bench/useBenchState';
import { SURFACE_INDEX, SURFACES } from '@/lib/bench/surfaces';
import { useBenchShortcuts } from '@/lib/bench/keyboard';
import { RoundtableSurface } from '@/components/bench/surfaces/RoundtableSurface';
import { DraftsSurface } from '@/components/bench/surfaces/DraftsSurface';
import { PapersSurface } from '@/components/bench/surfaces/PapersSurface';
import { KnowledgeSurface } from '@/components/bench/surfaces/KnowledgeSurface';
import { WorklogSurface } from '@/components/bench/surfaces/WorklogSurface';
import { ProjectInspector } from '@/components/bench/ProjectInspector';
import { EventLog } from '@/components/bench/EventLog';
import { FilesOverlay } from '@/components/bench/overlays/FilesOverlay';
import { MemoryOverlay } from '@/components/bench/overlays/MemoryOverlay';
import { PortfolioOverlay } from '@/components/bench/overlays/PortfolioOverlay';
import { MobileSurfaceBar } from '@/components/bench/MobileSurfaceBar';

/**
 * Inner component separated so useSearchParams (called inside useBenchState)
 * is scoped to a Suspense boundary — required by Next.js 16 to avoid
 * prerendering build failures (see docs: use-search-params#prerendering).
 */
function BenchContent() {
  const router = useRouter();
  const { state, update } = useBenchState();
  const surface = SURFACE_INDEX[state.surface];

  const [paletteOpen, setPaletteOpen] = useState(false);
  const [newProjectOpen, setNewProjectOpen] = useState(false);

  useBenchShortcuts({
    isPaletteOpen: paletteOpen,
    isOverlayOpen: state.overlay !== null,
    onSurfaceNumber: (i) => {
      const s = SURFACES[i];
      if (s) update({ surface: s.id });
    },
    onPaletteOpen: () => setPaletteOpen(true),
    onInspectorClose: () => update({ inspectorOpen: false }),
    onOverlayClose: () => update({ overlay: null }),
  });

  return (
    <>
    <BenchLayout
      rail={
        <Rail
          active={state.surface}
          onSelect={(id) => update({ surface: id })}
          onPaletteOpen={() => setPaletteOpen(true)}
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
              onNewProject={() => setNewProjectOpen(true)}
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
      log={<EventLog />}
      mobileNav={
        <MobileSurfaceBar
          active={state.surface}
          onSelect={(id) => update({ surface: id })}
          onPaletteOpen={() => setPaletteOpen(true)}
        />
      }
    />
    <CommandPalette
      open={paletteOpen}
      onClose={() => setPaletteOpen(false)}
      onProjectSelect={(id) => update({ projectId: id })}
      onOverlayOpen={(id) => update({ overlay: id })}
      onNewProject={() => setNewProjectOpen(true)}
    />
    <NewProjectModal
      open={newProjectOpen}
      onClose={() => setNewProjectOpen(false)}
      onCreated={(id) => update({ projectId: id, inspectorOpen: true })}
    />
    {state.overlay === 'files' && (
      <FilesOverlay projectId={state.projectId} onClose={() => update({ overlay: null })} />
    )}
    {state.overlay === 'memory' && (
      <MemoryOverlay projectId={state.projectId} onClose={() => update({ overlay: null })} />
    )}
    {state.overlay === 'portfolio' && (
      <PortfolioOverlay onClose={() => update({ overlay: null })} />
    )}
    </>
  );
}

export default function BenchPage() {
  return (
    <Suspense fallback={null}>
      <BenchContent />
    </Suspense>
  );
}
