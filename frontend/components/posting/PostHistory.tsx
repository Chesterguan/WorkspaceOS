"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PlatformBadge } from "@/components/PlatformBadge";
import { MarkPostedDialog } from "@/components/posting/MarkPostedDialog";
import { usePostRecords } from "@/lib/hooks/usePosting";
import { useDrafts } from "@/lib/hooks/useDrafts";
import { ExternalLink, History, Plus, Loader2 } from "lucide-react";
import { formatDistanceToNow } from "@/lib/utils";
import type { Draft } from "@/lib/types";

interface PostHistoryProps {
  projectId: string;
}

export function PostHistory({ projectId }: PostHistoryProps) {
  const { data: records, error, isLoading, mutate } = usePostRecords(projectId);
  const { data: draftsData } = useDrafts(projectId);
  const drafts: Draft[] = draftsData ?? [];

  const [markPostedOpen, setMarkPostedOpen] = useState(false);
  const [markPostedDraft, setMarkPostedDraft] = useState<Draft | null>(null);

  const sorted = [...(records ?? [])].sort(
    (a, b) => new Date(b.posted_at).getTime() - new Date(a.posted_at).getTime(),
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide flex items-center gap-1.5">
          <History className="w-3.5 h-3.5" />
          Post History
        </h3>
        <Button
          size="sm"
          variant="outline"
          className="gap-1.5"
          onClick={() => {
            setMarkPostedDraft(null);
            setMarkPostedOpen(true);
          }}
        >
          <Plus className="w-3.5 h-3.5" />
          Record Post
        </Button>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          Failed to load history: {error.message}
        </div>
      )}

      {!isLoading && !error && sorted.length === 0 && (
        <div className="text-center py-12 border border-dashed border-border rounded-lg text-muted-foreground">
          <History className="w-8 h-8 mx-auto mb-2 opacity-30" />
          <p className="text-sm">No post records yet.</p>
          <p className="text-xs mt-1">
            Use &quot;Record Post&quot; to log a post you&apos;ve published.
          </p>
        </div>
      )}

      {!isLoading && !error && sorted.length > 0 && (
        <div className="rounded-lg border border-border overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-secondary/20">
                <th className="text-left px-4 py-2.5 text-xs font-medium text-muted-foreground">
                  Draft
                </th>
                <th className="text-left px-4 py-2.5 text-xs font-medium text-muted-foreground">
                  Platform
                </th>
                <th className="text-left px-4 py-2.5 text-xs font-medium text-muted-foreground">
                  Posted
                </th>
                <th className="text-left px-4 py-2.5 text-xs font-medium text-muted-foreground">
                  Link
                </th>
                <th className="text-left px-4 py-2.5 text-xs font-medium text-muted-foreground">
                  Notes
                </th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((record) => {
                const draft = drafts.find((d) => d.id === record.draft_id);
                return (
                  <tr
                    key={record.id}
                    className="border-b border-border last:border-0 hover:bg-secondary/10 transition-colors"
                  >
                    <td className="px-4 py-3 max-w-[200px]">
                      <p className="text-xs truncate text-foreground/80">
                        {draft ? draft.content.slice(0, 50) + "…" : record.draft_id.slice(0, 8)}
                      </p>
                    </td>
                    <td className="px-4 py-3">
                      <PlatformBadge platform={record.platform} />
                    </td>
                    <td className="px-4 py-3 text-xs text-muted-foreground whitespace-nowrap">
                      <span title={new Date(record.posted_at).toLocaleString()}>
                        {formatDistanceToNow(record.posted_at)}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {record.post_url ? (
                        <a
                          href={record.post_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
                        >
                          <ExternalLink className="w-3 h-3" />
                          View
                        </a>
                      ) : (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 max-w-[180px]">
                      {record.notes ? (
                        <p className="text-xs text-muted-foreground truncate">{record.notes}</p>
                      ) : (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Mark posted dialog — when opened from header button, allow draft selection */}
      <MarkPostedDialog
        open={markPostedOpen}
        onOpenChange={setMarkPostedOpen}
        projectId={projectId}
        draft={markPostedDraft}
        onRecorded={() => {
          mutate();
          setMarkPostedOpen(false);
        }}
      />
    </div>
  );
}
