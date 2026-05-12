'use client';

import { Suspense, useState } from 'react';
import { useRouter } from 'next/navigation';
import { CommandPalette } from '@/components/bench/CommandPalette';
import { BenchLayout } from '@/components/bench/BenchLayout';
import { Rail } from '@/components/bench/Rail';
import { ProjectFilter } from '@/components/bench/ProjectFilter';
import { NewProjectModal } from '@/components/bench/NewProjectModal';
import { useBenchState } from '@/lib/bench/useBenchState';
import { findSurface } from '@/lib/bench/surfaces';
import { useDomainConfig } from '@/lib/bench/useDomainConfig';
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
  const { data } = useDomainConfig();
  const surfaces = data?.surfaces ?? [];

  const [paletteOpen, setPaletteOpen] = useState(false);
  const [newProjectOpen, setNewProjectOpen] = useState(false);

  // Resolve the URL surface against the live config; fall back to the first
  // surface (avoids a blank screen when the URL has a stale id or none).
  const activeId = state.surface ?? surfaces[0]?.id;
  const surface = activeId ? findSurface(surfaces, activeId) : undefined;

  useBenchShortcuts({
    isPaletteOpen: paletteOpen,
    isOverlayOpen: state.overlay !== null,
    onSurfaceNumber: (i) => {
      const s = surfaces[i];
      if (s) update({ surface: s.id });
    },
    onPaletteOpen: () => setPaletteOpen(true),
    onInspectorClose: () => update({ inspectorOpen: false }),
    onOverlayClose: () => update({ overlay: null }),
  });

  if (!data) {
    return (
      <div className="flex h-screen items-center justify-center text-muted-foreground text-sm">
        Loading…
      </div>
    );
  }

  return (
    <>
    <BenchLayout
      rail={
        <Rail
          active={surface?.id}
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
            <h1 className="text-lg font-semibold">{surface?.label ?? ''}</h1>
            <ProjectFilter
              projectId={state.projectId}
              onChange={(id) => update({ projectId: id })}
              onNewProject={() => setNewProjectOpen(true)}
            />
          </header>
          <div className="flex-1 min-h-0 flex flex-col">
            {surface?.type === 'roundtable' && (
              <RoundtableSurface
                projectId={state.projectId}
                mode={state.mode}
                onModeChange={(m) => update({ mode: m })}
              />
            )}
            {surface?.type === 'list' && surface.id === 'drafts' && (
              <DraftsSurface projectId={state.projectId} />
            )}
            {surface?.type === 'list' && surface.id === 'papers' && (
              <PapersSurface projectId={state.projectId} />
            )}
            {surface?.type === 'graph' && (
              <KnowledgeSurface projectId={state.projectId} />
            )}
            {surface?.type === 'report' && (
              <WorklogSurface projectId={state.projectId} />
            )}
          </div>
        </>
      }
      log={<EventLog />}
      mobileNav={
        <MobileSurfaceBar
          active={surface?.id}
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
