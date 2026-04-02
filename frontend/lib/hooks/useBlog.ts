import useSWR from 'swr';
import { blog } from '@/lib/api';
import type { BlogPost, BlogPostVersion } from '@/lib/types';
import type { BlogFilters } from '@/lib/api';

function blogListKey(projectId: string, filters?: BlogFilters) {
  const params = new URLSearchParams();
  if (filters?.status) params.set('status', filters.status);
  if (filters?.tag) params.set('tag', filters.tag);
  const qs = params.toString();
  return `/projects/${projectId}/blog${qs ? `?${qs}` : ''}`;
}

export function useBlogPosts(projectId: string | null, filters?: BlogFilters) {
  const { data, error, isLoading, mutate } = useSWR<BlogPost[]>(
    projectId ? blogListKey(projectId, filters) : null,
    () => blog.list(projectId!, filters),
  );

  return { data, error, isLoading, mutate };
}

export function useBlogPost(projectId: string | null, postId: string | null) {
  const { data, error, isLoading, mutate } = useSWR<BlogPost>(
    projectId && postId ? `/projects/${projectId}/blog/${postId}` : null,
    () => blog.get(projectId!, postId!),
  );

  return { data, error, isLoading, mutate };
}

export function useBlogVersions(
  projectId: string | null,
  postId: string | null,
) {
  const { data, error, isLoading, mutate } = useSWR<BlogPostVersion[]>(
    projectId && postId
      ? `/projects/${projectId}/blog/${postId}/versions`
      : null,
    () => blog.versions(projectId!, postId!),
  );

  return { data, error, isLoading, mutate };
}
