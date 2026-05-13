// Single source of truth for persona pools rendered in the bench's
// roundtable chat surfaces. Reads from the live domain config when
// available, falls back to the legacy hardcoded ADVISORS map (and a
// thin equivalent for research reviewers) so deployments that haven't
// run the wizard yet keep working.

'use client';

import { useMemo } from 'react';
import { useDomainConfig } from '@/lib/bench/useDomainConfig';
import { ADVISORS, ADVISOR_ORDER } from '@/lib/advisors';

export interface PersonaInfo {
  id: string;
  name: string;
  /** Optional subtitle line. Cofounder pool uses it for taglines like
   *  "Startup Strategy & PMF". Empty for framework-generated personas. */
  tagline?: string;
  color: string;
  /** Resolved avatar source — backend URL, /public path, or empty string
   *  when the persona has no image. Empty string is the contract for
   *  PersonaAvatar to fall back to initials. */
  avatar: string;
}

interface UsePersonaPoolResult {
  /** Ordered list of personas — preserves config order, used by pickers. */
  personas: PersonaInfo[];
  /** Map keyed by persona id, for direct lookup from chat messages
   *  that carry an advisor_id metadata field. */
  byId: Record<string, PersonaInfo>;
  /** Source of truth for the active pool — useful for diagnostics. */
  source: 'domain_config' | 'legacy_hardcoded';
}

/**
 * Resolve the persona pool for a given roundtable surface.
 *
 * `surfaceId` matches the surface id in domain.yaml (e.g. "cofounder",
 * "research"). If the loaded domain config has that surface with a
 * `personas` block, we use it. Otherwise we fall back to the legacy
 * hardcoded list (cofounder only — research has no legacy fallback;
 * an empty pool there is the correct signal that something needs
 * configuring).
 */
export function usePersonaPool(surfaceId: string): UsePersonaPoolResult {
  const { data } = useDomainConfig();

  return useMemo(() => {
    const surface = data?.surfaces?.find((s) => s.id === surfaceId);
    const items = surface?.personas?.items;

    if (items && items.length > 0) {
      const personas: PersonaInfo[] = items.map((item) => ({
        id: item.id,
        name: item.name,
        color: item.color,
        avatar: item.avatar ?? '',
        // Domain-config-driven personas don't carry a tagline yet — the
        // ChatWindow card just shows the name. If we add a tagline field
        // to the persona schema later, this is where it picks up.
        tagline: undefined,
      }));
      const byId = Object.fromEntries(personas.map((p) => [p.id, p]));
      return { personas, byId, source: 'domain_config' as const };
    }

    // Fallback: legacy cofounder advisors, hardcoded in lib/advisors.ts.
    // Only meaningful for surfaceId === 'cofounder'; for any other id
    // we return an empty pool (research has no legacy fallback — the
    // surface renders an empty picker, which is the right signal that
    // domain config needs personas there).
    if (surfaceId === 'cofounder') {
      const personas: PersonaInfo[] = ADVISOR_ORDER.map((id) => {
        const a = ADVISORS[id];
        return {
          id: a.id,
          name: a.name,
          tagline: a.tagline,
          color: a.color,
          avatar: a.avatar,
        };
      });
      const byId = Object.fromEntries(personas.map((p) => [p.id, p]));
      return { personas, byId, source: 'legacy_hardcoded' as const };
    }

    return {
      personas: [],
      byId: {},
      source: 'legacy_hardcoded' as const,
    };
  }, [data, surfaceId]);
}
