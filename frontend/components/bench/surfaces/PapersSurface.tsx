'use client';

import useSWR from 'swr';
import Link from 'next/link';
import { blog as blogApi } from '@/lib/api';
import type { BlogPost } from '@/lib/types';
import { EmptyProjectPicker } from './EmptyProjectPicker';
import { SurfaceLoading } from '@/components/bench/SurfaceLoading';

interface Props {
  projectId: string | undefined;
}

export function PapersSurface({ projectId }: Props) {
  if (!projectId) {
    return (
      <EmptyProjectPicker
        surfaceLabel="papers"
        hint="Single-project papers are scoped. To see a multi-project portfolio paper, pick 'Portfolio' from the header scope toggle (coming in a follow-up task)."
      />
    );
  }

  // eslint-disable-next-line react-hooks/rules-of-hooks
  const { data: posts = [], isLoading } = useSWR<BlogPost[]>(
    `/projects/${projectId}/blog?tag=paper`,
    () => blogApi.list(projectId, { tag: 'paper' }),
  );

  return (
    <div className="flex-1 overflow-y-auto p-6">
      {isLoading ? (
        <SurfaceLoading rows={4} />
      ) : posts.length === 0 ? (
        <div className="text-sm text-muted-foreground">
          No papers yet. Generate one in the existing{' '}
          <Link
            href={`/projects/${projectId}/research/paper`}
            className="text-foreground underline hover:no-underline"
          >
            paper page
          </Link>
          {' '}— a &quot;+ New paper&quot; action will land here in a follow-up task.
        </div>
      ) : (
        <ul className="space-y-2">
          {posts.map((p) => (
            <li key={p.id} className="rounded-md border border-border bg-card/40 p-3">
              {/* Link to paper page without postId query — paper page manages its own pipeline state
                  and does not accept a postId param to load a specific post. */}
              <Link
                href={`/projects/${projectId}/research/paper`}
                className="block hover:bg-card/60 -mx-3 -my-3 px-3 py-3 rounded-md transition"
              >
                <div className="text-sm font-medium text-foreground">{p.title}</div>
                <div className="text-xs text-muted-foreground">
                  {new Date(p.created_at).toLocaleDateString()}
                  {p.tags && p.tags.length > 0 ? ` · ${p.tags.join(' · ')}` : ''}
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
