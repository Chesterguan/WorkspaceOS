// Surface renderer registry — adaptive (v0.2.1, v0.4 path reserved).
//
// Today: surface dispatch is one table-driven map. The bench page does:
//
//     const Renderer = SURFACE_RENDERERS[surface.type] ?? FallbackRenderer;
//     return <Renderer projectId={...} surface={...} />;
//
// v0.4 path (reserved): the registry becomes runtime-extensible —
// extensions ship a React component + a manifest declaration, the
// framework imports + registers it at app boot. The contract for a
// renderer is the SurfaceRenderer type below, designed so v0.4
// contributions are additive.
//
// In-tree surface types today: roundtable, list, graph, report.
// Adding a new type is one entry in this map + the schema/loader
// catching up.

import type { ComponentType } from 'react';

export interface SurfaceRendererProps {
  /** Currently filtered project id, or undefined for "All projects". */
  projectId: string | undefined;
  /** The surface config entry from domain.yaml, denormalized. */
  surface: { id: string; type: string; label: string; accent: string };
}

export type SurfaceRenderer = ComponentType<SurfaceRendererProps>;

/** Runtime registry of surface renderers, keyed by surface.type.
 *
 *  When v0.4 lands, this dict is what extensions mutate. The bench
 *  page reads from here, not from a hardcoded if-chain.
 */
export const SURFACE_RENDERERS: Record<string, SurfaceRenderer> = {};

export function registerSurfaceRenderer(type: string, renderer: SurfaceRenderer): void {
  if (SURFACE_RENDERERS[type] && SURFACE_RENDERERS[type] !== renderer) {
    // Hot-reload during dev re-runs this; identity check above avoids
    // spurious warnings. A genuine conflict surfaces here so we don't
    // silently overwrite.
    if (process.env.NODE_ENV === 'production') {
      throw new Error(
        `surface_renderer name conflict: ${type} already registered`,
      );
    }
  }
  SURFACE_RENDERERS[type] = renderer;
}

/** Look up a renderer; returns undefined if the type is unregistered.
 *  The bench page should fall back to a "this surface type isn't
 *  available — extension may be missing" placeholder. */
export function getSurfaceRenderer(type: string): SurfaceRenderer | undefined {
  return SURFACE_RENDERERS[type];
}
