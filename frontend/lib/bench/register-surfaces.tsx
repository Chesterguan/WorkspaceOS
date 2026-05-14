// In-tree surface renderer registrations.
//
// Imported for side effect by app/bench/page.tsx — populates the
// SURFACE_RENDERERS map before the page first renders. Adding a new
// in-tree surface type is a 1-line change here.
//
// Note: `list` surfaces dispatch on surface.id (drafts vs papers)
// rather than .type because both share the "list" shape but render
// different components. v0.4 will introduce a more granular contract
// (each surface type ships its own renderer); for v0.2.x we keep
// the per-id branch for `list` only.

'use client';

import type { SurfaceRenderer } from './surface-registry';
import { registerSurfaceRenderer } from './surface-registry';
import { RoundtableSurface } from '@/components/bench/surfaces/RoundtableSurface';
import { DraftsSurface } from '@/components/bench/surfaces/DraftsSurface';
import { PapersSurface } from '@/components/bench/surfaces/PapersSurface';
import { KnowledgeSurface } from '@/components/bench/surfaces/KnowledgeSurface';
import { WorklogSurface } from '@/components/bench/surfaces/WorklogSurface';

const RoundtableRenderer: SurfaceRenderer = ({ projectId, surface }) => (
  <RoundtableSurface projectId={projectId} surfaceId={surface.id} />
);

const ListRenderer: SurfaceRenderer = ({ projectId, surface }) => {
  // For v0.2.x there are two list-typed surfaces shipped in core.
  // v0.4 will let each list-typed surface ship its own renderer.
  if (surface.id === 'drafts') return <DraftsSurface projectId={projectId} />;
  if (surface.id === 'papers') return <PapersSurface projectId={projectId} />;
  return null;
};

const GraphRenderer: SurfaceRenderer = ({ projectId }) => (
  <KnowledgeSurface projectId={projectId} />
);

const ReportRenderer: SurfaceRenderer = ({ projectId }) => (
  <WorklogSurface projectId={projectId} />
);

registerSurfaceRenderer('roundtable', RoundtableRenderer);
registerSurfaceRenderer('list', ListRenderer);
registerSurfaceRenderer('graph', GraphRenderer);
registerSurfaceRenderer('report', ReportRenderer);
