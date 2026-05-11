'use client';

import useSWR from 'swr';
import { blog as blogApi } from '@/lib/api';
import type { BlogPost } from '@/lib/types';
import { EmptyProjectPicker } from './EmptyProjectPicker';
import { SurfaceLoading } from '@/components/bench/SurfaceLoading';

interface Props {
  projectId: string | undefined;
}

export function PapersSurface({ projectId }: Props) {
  const { data: posts = [], isLoading } = useSWR<BlogPost[]>(
    projectId ? `/projects/${projectId}/blog?tag=paper` : null,
    () => blogApi.list(projectId!, { tag: 'paper' }),
  );

  if (!projectId) {
    return (
      <EmptyProjectPicker
        surfaceLabel="papers"
        hint="Single-project papers are scoped. To see a multi-project portfolio paper, pick 'Portfolio' from the header scope toggle (coming in a follow-up task)."
      />
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-6">
      {isLoading ? (
        <SurfaceLoading rows={4} />
      ) : posts.length === 0 ? (
        <div className="text-sm text-muted-foreground">No papers yet for this project.</div>
      ) : (
        <ul className="space-y-2">
          {posts.map((p) => (
            <li key={p.id} className="rounded-md border border-border bg-card/40 p-3">
              <div className="text-sm font-medium text-foreground">{p.title}</div>
              <div className="text-xs text-muted-foreground">
                {new Date(p.created_at).toLocaleDateString()}
                {p.tags && p.tags.length > 0 ? ` · ${p.tags.join(' · ')}` : ''}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
