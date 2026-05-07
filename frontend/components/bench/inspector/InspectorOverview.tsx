'use client';

import { useNarrative } from '@/lib/hooks/useNarrative';
import { useSyncRuns } from '@/lib/hooks/useSyncRuns';
import { formatDistanceToNow } from '@/lib/utils';

interface Props {
  projectId: string;
}

export function InspectorOverview({ projectId }: Props) {
  const { data: narrative } = useNarrative(projectId);
  const { data: syncs = [] } = useSyncRuns(projectId);
  const lastSync = syncs[0];

  return (
    <section className="space-y-2">
      <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Overview</div>
      {narrative?.one_liner ? (
        <div className="text-foreground">{narrative.one_liner}</div>
      ) : (
        <div className="text-muted-foreground italic">No one-liner yet.</div>
      )}
      {lastSync?.completed_at && (
        <div className="text-muted-foreground">
          Last sync: {formatDistanceToNow(lastSync.completed_at)}
        </div>
      )}
    </section>
  );
}
