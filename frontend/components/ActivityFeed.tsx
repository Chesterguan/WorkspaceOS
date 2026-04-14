"use client";

import { useState } from "react";
import useSWR from "swr";
import {
  GitBranch,
  RefreshCw,
  FileText,
  Sparkles,
  Brain,
  HardDrive,
  Pencil,
  Upload,
  Loader2,
  Activity as ActivityIcon,
  CalendarDays,
  Mail,
} from "lucide-react";

import { activity as activityApi, type ActivityEvent } from "@/lib/api";
import { formatDistanceToNow, cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

interface ActivityFeedProps {
  projectId: string;
  /** Initial page size. Subsequent pages use the same value. Defaults to 25. */
  pageSize?: number;
}

// Icon + colour per event_type. Unknown types fall through to a neutral
// default — keeps the feed rendering forward-compatible when the backend
// emits new kinds before the frontend ships a mapping for them.
const EVENT_ICONS: Record<string, { icon: typeof GitBranch; color: string }> = {
  "sync.completed":      { icon: RefreshCw, color: "text-cyan-400" },
  "worklog.generated":   { icon: FileText,  color: "text-orange-400" },
  "memory.added":        { icon: Brain,     color: "text-pink-400" },
  "wiki.refreshed":      { icon: Sparkles,  color: "text-violet-400" },
  "draft.created":       { icon: FileText,  color: "text-amber-400" },
  "draft.published":     { icon: Upload,    color: "text-emerald-400" },
  "project.edited":      { icon: Pencil,      color: "text-muted-foreground" },
  "workspace.scanned":   { icon: HardDrive,   color: "text-blue-400" },
  "ingest.calendar":     { icon: CalendarDays, color: "text-indigo-400" },
  "ingest.email":        { icon: Mail,        color: "text-sky-400" },
};

const DEFAULT_ICON = { icon: ActivityIcon, color: "text-muted-foreground/70" };


export function ActivityFeed({ projectId, pageSize = 25 }: ActivityFeedProps) {
  // Initial page via SWR so it participates in revalidation / focus refresh.
  const { data: initial, error, isLoading, mutate } = useSWR(
    projectId ? `/projects/${projectId}/activity?limit=${pageSize}` : null,
    () => activityApi.list(projectId, { limit: pageSize }),
    { refreshInterval: 30_000 },
  );

  // Locally accumulated older pages. Kept outside SWR because "load more"
  // is a manual user action, not something to revalidate on focus.
  const [older, setOlder] = useState<ActivityEvent[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);

  // Derived: the full list is SWR's initial page + whatever the user has
  // paged into. Reset of `older` on projectId change would require a
  // useEffect; for now the component is keyed by projectId at the call
  // site so a remount handles that automatically.
  const items: ActivityEvent[] = [
    ...(initial?.items ?? []),
    ...older,
  ];
  const effectiveCursor = cursor ?? initial?.next_cursor ?? null;

  async function handleLoadMore() {
    if (!effectiveCursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const next = await activityApi.list(projectId, {
        limit: pageSize,
        cursor: effectiveCursor,
      });
      setOlder((prev) => [...prev, ...next.items]);
      setCursor(next.next_cursor);
    } finally {
      setLoadingMore(false);
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-xs text-muted-foreground py-4">
        <Loader2 className="w-3 h-3 animate-spin" />
        Loading activity…
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-xs text-destructive/80 py-2">
        Failed to load activity: {error.message ?? "unknown error"}
        <button
          type="button"
          onClick={() => mutate()}
          className="ml-2 underline hover:text-destructive"
        >
          retry
        </button>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="text-xs text-muted-foreground py-4">
        No activity yet. Sync the project, scan the workspace, or generate a
        work log — events will appear here.
      </div>
    );
  }

  return (
    <div className="space-y-1">
      {items.map((event) => (
        <ActivityRow key={event.id} event={event} />
      ))}
      {effectiveCursor && (
        <div className="pt-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={handleLoadMore}
            disabled={loadingMore}
            className="w-full text-xs text-muted-foreground hover:text-foreground"
          >
            {loadingMore ? (
              <>
                <Loader2 className="w-3 h-3 mr-1 animate-spin" />
                Loading…
              </>
            ) : (
              "Load more"
            )}
          </Button>
        </div>
      )}
    </div>
  );
}


// Each row is icon + summary + relative timestamp + source tag.
// Kept plain — "smart" enrichment (grouping, AI summaries) is v2.
function ActivityRow({ event }: { event: ActivityEvent }) {
  const { icon: Icon, color } = EVENT_ICONS[event.event_type] ?? DEFAULT_ICON;
  return (
    <div className="flex items-start gap-2.5 px-2 py-2 rounded-md hover:bg-secondary/30 transition-colors">
      <div
        className={cn(
          "w-6 h-6 rounded-full bg-background border border-border flex items-center justify-center shrink-0 mt-0.5",
          color,
        )}
      >
        <Icon className="w-3 h-3" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-xs text-foreground/90 leading-snug break-words">
          {event.summary}
        </p>
        <p className="text-[10px] text-muted-foreground mt-0.5">
          <span className="uppercase tracking-wide mr-2">{event.source}</span>
          <span>{formatDistanceToNow(event.created_at)}</span>
        </p>
      </div>
    </div>
  );
}
