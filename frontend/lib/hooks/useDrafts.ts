import useSWR from 'swr';
import { drafts } from '@/lib/api';
import type { Draft } from '@/lib/types';
import type { DraftFilters } from '@/lib/api';

function filtersKey(projectId: string, filters?: DraftFilters) {
  const params = new URLSearchParams();
  if (filters?.platform) params.set('platform', filters.platform);
  if (filters?.status) params.set('status', filters.status);
  const qs = params.toString();
  return `/projects/${projectId}/drafts${qs ? `?${qs}` : ''}`;
}

export function useDrafts(projectId: string | null, filters?: DraftFilters) {
  const { data, error, isLoading, mutate } = useSWR<Draft[]>(
    projectId ? filtersKey(projectId, filters) : null,
    () => drafts.list(projectId!, filters),
  );

  return { data, error, isLoading, mutate };
}

export function useDraft(projectId: string | null, draftId: string | null) {
  const { data, error, isLoading, mutate } = useSWR<Draft>(
    projectId && draftId ? `/projects/${projectId}/drafts/${draftId}` : null,
    () => drafts.get(projectId!, draftId!),
  );

  return { data, error, isLoading, mutate };
}

export function useDraftVersions(projectId: string | null, draftId: string | null) {
  const { data, error, isLoading, mutate } = useSWR<Draft[]>(
    projectId && draftId
      ? `/projects/${projectId}/drafts/${draftId}/versions`
      : null,
    () => drafts.versions(projectId!, draftId!),
  );

  return { data, error, isLoading, mutate };
}
