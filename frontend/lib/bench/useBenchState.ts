'use client';

import { useCallback } from 'react';
import { useRouter, useSearchParams, usePathname } from 'next/navigation';
import type { SurfaceId } from '@/lib/bench/surfaces';
import { SURFACES } from '@/lib/bench/surfaces';

export type RoundtableMode = 'cofounder' | 'research';
export type OverlayId = 'files' | 'memory' | 'portfolio' | null;

export interface BenchState {
  surface: SurfaceId;
  projectId: string | undefined;          // undefined = "All projects"
  inspectorOpen: boolean;
  mode: RoundtableMode;                   // only meaningful when surface === 'r'
  overlay: OverlayId;
}

const VALID_SURFACES = new Set<SurfaceId>(SURFACES.map((s) => s.id));

function parseSurface(raw: string | null): SurfaceId {
  return raw && VALID_SURFACES.has(raw as SurfaceId) ? (raw as SurfaceId) : 'r';
}

function parseMode(raw: string | null): RoundtableMode {
  return raw === 'research' ? 'research' : 'cofounder';
}

function parseOverlay(raw: string | null): OverlayId {
  if (raw === 'files' || raw === 'memory' || raw === 'portfolio') return raw;
  return null;
}

export function useBenchState() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();

  const state: BenchState = {
    surface: parseSurface(params.get('surface')),
    projectId: params.get('project') || undefined,
    inspectorOpen: params.get('inspector') !== 'closed' && Boolean(params.get('project')),
    mode: parseMode(params.get('mode')),
    overlay: parseOverlay(params.get('overlay')),
  };

  const update = useCallback((patch: Partial<BenchState>) => {
    const next = new URLSearchParams(params.toString());

    if (patch.surface !== undefined) {
      next.set('surface', patch.surface);
    }
    if (patch.projectId !== undefined) {
      if (patch.projectId === undefined || patch.projectId === '') {
        next.delete('project');
        next.delete('inspector');           // no inspector when no project
      } else {
        next.set('project', patch.projectId);
      }
    }
    if (patch.inspectorOpen !== undefined) {
      if (patch.inspectorOpen) next.delete('inspector');
      else next.set('inspector', 'closed');
    }
    if (patch.mode !== undefined) {
      next.set('mode', patch.mode);
    }
    if (patch.overlay !== undefined) {
      if (patch.overlay) next.set('overlay', patch.overlay);
      else next.delete('overlay');
    }

    router.replace(`${pathname}?${next.toString()}`);
  }, [params, pathname, router]);

  return { state, update };
}
