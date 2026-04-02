"use client";

import { useState } from "react";
import Link from "next/link";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { PlatformBadge } from "@/components/PlatformBadge";
import { formatDistanceToNow } from "@/lib/utils";
import { Clock, Hash, ThumbsUp, PenLine, Loader2, CheckCircle2, Trash2 } from "lucide-react";
import { ai, drafts as draftsApi } from "@/lib/api";
import { toast } from "sonner";
import type { Draft, AIFeedback } from "@/lib/types";
import { PublishButton } from "@/components/publish/PublishButton";

const STATUS_COLORS: Record<string, string> = {
  draft: "bg-yellow-600/20 text-yellow-400 border-yellow-600/30",
  approved: "bg-green-600/20 text-green-400 border-green-600/30",
  archived: "bg-zinc-600/20 text-zinc-400 border-zinc-600/30",
};

const FEEDBACK_COLORS: Record<string, string> = {
  approved: "bg-green-600/20 text-green-400 border-green-600/30",
  heavily_edited: "bg-amber-600/20 text-amber-400 border-amber-600/30",
  rejected: "bg-red-600/20 text-red-400 border-red-600/30",
};

const FEEDBACK_LABELS: Record<string, string> = {
  approved: "Approved",
  heavily_edited: "Edited",
  rejected: "Rejected",
};

interface DraftCardProps {
  draft: Draft;
  projectId: string;
  onFeedbackRecorded?: () => void;
  onDeleted?: () => void;
}

export function DraftCard({ draft, projectId, onFeedbackRecorded, onDeleted }: DraftCardProps) {
  const [feedback, setFeedback] = useState<AIFeedback | null>(null);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [finalContent, setFinalContent] = useState("");
  const [editNotes, setEditNotes] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const canGiveFeedback = draft.status === "draft" || draft.status === "approved";

  async function handleDelete(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (!window.confirm("Delete this draft? This cannot be undone.")) return;
    try {
      await draftsApi.delete(projectId, draft.id);
      toast.success("Draft deleted");
      onDeleted?.();
    } catch (err) {
      toast.error("Failed to delete draft", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    }
  }

  async function handleApprove(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    setIsSubmitting(true);
    try {
      const result = await ai.recordFeedback(projectId, draft.id, {
        outcome: "approved",
      });
      setFeedback(result);
      toast.success("Feedback recorded", { description: "Draft marked as approved." });
      onFeedbackRecorded?.();
    } catch (err) {
      toast.error("Failed to record feedback", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleSubmitEdit(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    setIsSubmitting(true);
    try {
      const result = await ai.recordFeedback(projectId, draft.id, {
        outcome: "heavily_edited",
        final_content: finalContent || undefined,
        notes: editNotes || undefined,
      });
      setFeedback(result);
      setEditDialogOpen(false);
      toast.success("Feedback recorded", { description: "Edit feedback saved." });
      onFeedbackRecorded?.();
    } catch (err) {
      toast.error("Failed to record feedback", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <>
      <Link href={`/projects/${projectId}/drafts/${draft.id}`}>
        <Card className="group hover:border-primary/50 hover:bg-card/80 transition-all duration-200 cursor-pointer h-full">
          <CardHeader className="pb-2">
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-2 flex-wrap">
                <PlatformBadge platform={draft.platform} />
                <Badge
                  variant="outline"
                  className={`text-xs capitalize ${STATUS_COLORS[draft.status]}`}
                >
                  {draft.status}
                </Badge>
                {feedback && (
                  <Badge
                    variant="outline"
                    className={`text-xs ${FEEDBACK_COLORS[feedback.outcome]}`}
                  >
                    <CheckCircle2 className="w-2.5 h-2.5 mr-1" />
                    {FEEDBACK_LABELS[feedback.outcome]}
                  </Badge>
                )}
              </div>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 shrink-0 text-muted-foreground hover:text-destructive"
                onClick={handleDelete}
              >
                <Trash2 className="w-3.5 h-3.5" />
              </Button>
            </div>
          </CardHeader>
          <CardContent className="pt-0 space-y-3">
            <p className="text-sm text-foreground/80 line-clamp-3 leading-relaxed">
              {draft.content}
            </p>
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              <span className="flex items-center gap-1">
                <Hash className="w-3.5 h-3.5" />
                v{draft.version}
              </span>
              <span className="flex items-center gap-1 ml-auto">
                <Clock className="w-3.5 h-3.5" />
                {formatDistanceToNow(draft.updated_at)}
              </span>
            </div>

            {/* Feedback buttons — only shown for actionable statuses */}
            {canGiveFeedback && !feedback && (
              <div
                className="flex items-center gap-2 pt-1 border-t border-border"
                onClick={(e) => e.preventDefault()}
              >
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 px-2 text-xs gap-1 text-muted-foreground hover:text-green-400"
                  onClick={handleApprove}
                  disabled={isSubmitting}
                >
                  <ThumbsUp className="w-3 h-3" />
                  Approved
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 px-2 text-xs gap-1 text-muted-foreground hover:text-amber-400"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    setEditDialogOpen(true);
                  }}
                  disabled={isSubmitting}
                >
                  <PenLine className="w-3 h-3" />
                  Needed Editing
                </Button>
              </div>
            )}

            {/* Quick publish action — only shown for approved drafts */}
            {draft.status === "approved" && (
              <div
                className="pt-1 border-t border-border"
                onClick={(e) => e.preventDefault()}
              >
                <PublishButton
                  projectId={projectId}
                  draftId={draft.id}
                  platform={draft.platform}
                  content={draft.content}
                  compact
                  onPublished={() => onFeedbackRecorded?.()}
                />
              </div>
            )}
          </CardContent>
        </Card>
      </Link>

      {/* Edit feedback dialog */}
      <Dialog open={editDialogOpen} onOpenChange={setEditDialogOpen}>
        <DialogContent className="sm:max-w-md bg-card border-border">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <PenLine className="w-5 h-5 text-primary" />
              Record Edit Feedback
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 pt-2">
            <div className="space-y-2">
              <Label>Final content (optional)</Label>
              <Textarea
                value={finalContent}
                onChange={(e) => setFinalContent(e.target.value)}
                placeholder="Paste the final content you actually used..."
                className="bg-secondary/40 resize-none"
                rows={5}
              />
            </div>
            <div className="space-y-2">
              <Label>Notes (optional)</Label>
              <Textarea
                value={editNotes}
                onChange={(e) => setEditNotes(e.target.value)}
                placeholder="What needed to change? Tone, facts, length..."
                className="bg-secondary/40 resize-none"
                rows={3}
              />
            </div>
            <Button
              className="w-full gap-2"
              onClick={handleSubmitEdit}
              disabled={isSubmitting}
            >
              {isSubmitting ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <PenLine className="w-4 h-4" />
              )}
              {isSubmitting ? "Saving..." : "Save Feedback"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
