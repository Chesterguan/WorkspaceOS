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
import { useFirstRunRedirect } from '@/lib/onboarding/useFirstRunRedirect';
import { getSurfaceRenderer } from '@/lib/bench/surface-registry';
// Side-effect import — populates the surface registry with in-tree
// renderers before this module renders.
import '@/lib/bench/register-surfaces';
// Surface components are registered via the surface-registry side-effect
// import above. The bench dispatches through getSurfaceRenderer().
import { ProjectInspector } from '@/components/bench/ProjectInspector';
import { EventLog } from '@/components/bench/EventLog';
import { FilesOverlay } from '@/components/bench/overlays/FilesOverlay';
import { MemoryOverlay } from '@/components/bench/overlays/MemoryOverlay';
import { PortfolioOverlay } from '@/components/bench/overlays/PortfolioOverlay';
import { MobileSurfaceBar } from '@/components/bench/MobileSurfaceBar';
import { FeedbackButton } from '@/components/feedback/FeedbackButton';

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

  // Fresh users with no projects + incomplete wizard → soft-redirect to /onboarding
  useFirstRunRedirect();

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
            {(() => {
              if (!surface) return null;
              const Renderer = getSurfaceRenderer(surface.type);
              if (!Renderer) {
                // Surface type referenced in domain.yaml but no renderer
                // is registered. Either a typo, or an extension is
                // missing. Show a friendly placeholder instead of a
                // blank panel.
                return (
                  <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground p-8 text-center">
                    Surface type <code className="px-1 mx-1 rounded bg-card border border-border">{surface.type}</code>
                    is not registered. Install the extension that provides it, or check for a typo in your domain config.
                  </div>
                );
              }
              return (
                <Renderer
                  projectId={state.projectId}
                  surface={{
                    id: surface.id,
                    type: surface.type,
                    label: surface.label,
                    accent: surface.accent,
                  }}
                />
              );
            })()}
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
      activeProjectId={state.projectId}
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
    <FeedbackButton />
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
