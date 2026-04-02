"use client";

import { useProjectContext } from "@/components/ProjectContext";
import { useTimeline } from "@/lib/hooks/useTimeline";
import {
  History,
  GitCommit,
  Tag,
  Lightbulb,
  FileText,
  ExternalLink,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { TimelineEvent } from "@/lib/types";

const EVENT_CONFIG: Record<
  string,
  { icon: React.ElementType; color: string; bg: string }
> = {
  release: {
    icon: Tag,
    color: "text-green-500",
    bg: "bg-green-500/10 border-green-500/30",
  },
  commit: {
    icon: GitCommit,
    color: "text-blue-400",
    bg: "bg-blue-500/10 border-blue-500/30",
  },
  insight: {
    icon: Lightbulb,
    color: "text-amber-400",
    bg: "bg-amber-500/10 border-amber-500/30",
  },
  summary: {
    icon: FileText,
    color: "text-purple-400",
    bg: "bg-purple-500/10 border-purple-500/30",
  },
  milestone: {
    icon: Tag,
    color: "text-green-400",
    bg: "bg-green-500/10 border-green-500/30",
  },
};

function TimelineEventCard({ event }: { event: TimelineEvent }) {
  const config = EVENT_CONFIG[event.type] ?? EVENT_CONFIG.commit;
  const Icon = config.icon;

  return (
    <div className="flex gap-3 group">
      {/* Dot + line */}
      <div className="flex flex-col items-center pt-1">
        <div
          className={cn(
            "w-8 h-8 rounded-full border flex items-center justify-center shrink-0",
            config.bg,
          )}
        >
          <Icon className={cn("w-4 h-4", config.color)} />
        </div>
        <div className="w-px flex-1 bg-border/50 mt-1" />
      </div>

      {/* Content */}
      <div className="pb-6 pt-0.5 min-w-0 flex-1">
        <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
          <span>{event.date}</span>
          <span
            className={cn(
              "px-1.5 py-0.5 rounded text-[10px] font-medium uppercase tracking-wider",
              config.bg,
              config.color,
            )}
          >
            {event.type}
          </span>
          {event.source_ref && (
            <span className="font-mono text-[11px] text-muted-foreground/70">
              {event.source_ref}
            </span>
          )}
        </div>

        <p className="text-sm font-medium leading-snug">{event.title}</p>

        {event.description && (
          <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
            {event.description}
          </p>
        )}

        {event.url && (
          <a
            href={event.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-xs text-primary hover:underline mt-1"
          >
            View on GitHub
            <ExternalLink className="w-3 h-3" />
          </a>
        )}
      </div>
    </div>
  );
}

function formatMonth(month: string): string {
  const [year, m] = month.split("-");
  const date = new Date(parseInt(year), parseInt(m) - 1);
  return date.toLocaleDateString("en-US", { year: "numeric", month: "long" });
}

export default function TimelinePage() {
  const { project } = useProjectContext();
  const { data: timeline, error, isLoading } = useTimeline(project.id);

  return (
    <div className="p-8 space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-semibold flex items-center gap-2">
          <History className="w-6 h-6" />
          Project Timeline
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Chronological view of commits, releases, and AI-extracted milestones.
        </p>
        {timeline && (
          <p className="text-xs text-muted-foreground mt-1">
            {timeline.total_events} events across{" "}
            {timeline.months.length} months
          </p>
        )}
      </div>

      {isLoading ? (
        <div className="animate-pulse space-y-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="flex gap-3">
              <div className="w-8 h-8 rounded-full bg-secondary/60 shrink-0" />
              <div className="flex-1 space-y-2">
                <div className="h-3 bg-secondary/40 rounded w-1/4" />
                <div className="h-4 bg-secondary/40 rounded w-3/4" />
              </div>
            </div>
          ))}
        </div>
      ) : error ? (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          Failed to load timeline: {error.message}
        </div>
      ) : !timeline || timeline.total_events === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 gap-3">
          <div className="w-12 h-12 rounded-full bg-secondary flex items-center justify-center">
            <History className="w-6 h-6 text-muted-foreground" />
          </div>
          <p className="text-sm text-muted-foreground">
            No timeline events yet. Sync the project to populate.
          </p>
        </div>
      ) : (
        <div className="space-y-8">
          {timeline.months.map((month) => (
            <div key={month.month}>
              <h2 className="text-sm font-semibold text-muted-foreground mb-4 sticky top-0 bg-background py-1 z-10">
                {formatMonth(month.month)}
              </h2>
              <div>
                {month.events.map((event, i) => (
                  <TimelineEventCard
                    key={`${month.month}-${i}`}
                    event={event}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
