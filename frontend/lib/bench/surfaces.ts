import { ComponentType } from 'react';

export type SurfaceId = 'r' | 'd' | 'p' | 'k' | 'w';

export interface SurfaceDef {
  id: SurfaceId;
  letter: string;
  label: string;
  accent: string;        // tailwind color class fragment
  description: string;
}

export const SURFACES: SurfaceDef[] = [
  { id: 'r', letter: 'R', label: 'Roundtable', accent: 'violet',  description: 'Talk to advisors and reviewers' },
  { id: 'd', letter: 'D', label: 'Drafts',     accent: 'orange',  description: 'Blog and social drafts' },
  { id: 'p', letter: 'P', label: 'Papers',     accent: 'blue',    description: 'Generate and edit research papers' },
  { id: 'k', letter: 'K', label: 'Knowledge',  accent: 'teal',    description: 'Cross-project knowledge graph' },
  { id: 'w', letter: 'W', label: 'Worklog',    accent: 'emerald', description: 'Periodic progress reports' },
];

export const SURFACE_INDEX: Record<SurfaceId, SurfaceDef> = Object.fromEntries(
  SURFACES.map((s) => [s.id, s]),
) as Record<SurfaceId, SurfaceDef>;

/**
 * Map an accent name to the dim background + foreground tailwind classes
 * we use for the active rail icon. Kept here so styling stays consistent.
 */
export function accentClasses(accent: string, active: boolean): string {
  const base = active
    ? `bg-${accent}-500/20 text-${accent}-300 border border-${accent}-500/30`
    : 'text-muted-foreground hover:text-foreground hover:bg-muted/40';
  return base;
}
