import type { DomainConfigSurface } from '@/lib/types';

// Surface IDs are now whatever the active domain config defines (cofounder,
// drafts, knowledge, ...) — we keep this as a string alias so the type
// flows through useBenchState + rail without re-importing the config shape.
export type SurfaceId = string;

export function findSurface(
  surfaces: DomainConfigSurface[],
  id: string,
): DomainConfigSurface | undefined {
  return surfaces.find((s) => s.id === id);
}

export function findSurfaceByLetter(
  surfaces: DomainConfigSurface[],
  letter: string,
): DomainConfigSurface | undefined {
  return surfaces.find((s) => s.letter.toLowerCase() === letter.toLowerCase());
}

export function defaultSurfaceId(surfaces: DomainConfigSurface[]): SurfaceId | undefined {
  return surfaces[0]?.id;
}
