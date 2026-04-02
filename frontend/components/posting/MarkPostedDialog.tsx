"use client";

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Loader2, CheckCircle2 } from "lucide-react";
import { posting } from "@/lib/api";
import { useDrafts } from "@/lib/hooks/useDrafts";
import { toast } from "sonner";
import { PlatformBadge } from "@/components/PlatformBadge";
import { PLATFORM_LABELS } from "@/components/PlatformBadge";
import type { Draft } from "@/lib/types";

interface MarkPostedDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string;
  /** When provided, the draft is pre-selected and the selector is hidden. */
  draft: Draft | null;
  onRecorded: () => void;
}

export function MarkPostedDialog({
  open,
  onOpenChange,
  projectId,
  draft: preSelectedDraft,
  onRecorded,
}: MarkPostedDialogProps) {
  const nowIso = () => {
    const d = new Date();
    return d.toISOString().slice(0, 16);
  };

  const { data: draftsData } = useDrafts(
    preSelectedDraft ? null : projectId,
  );
  const availableDrafts: Draft[] = draftsData ?? [];

  const [selectedDraftId, setSelectedDraftId] = useState("");
  const [postedAt, setPostedAt] = useState(nowIso);
  const [url, setUrl] = useState("");
  const [notes, setNotes] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const activeDraft =
    preSelectedDraft ??
    availableDrafts.find((d) => d.id === selectedDraftId) ??
    null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!activeDraft) {
      toast.error("Select a draft first");
      return;
    }

    setIsSubmitting(true);
    try {
      await posting.createRecord(projectId, {
        draft_id: activeDraft.id,
        platform: activeDraft.platform,
        posted_at: new Date(postedAt).toISOString(),
        post_url: url.trim() || undefined,
        notes: notes.trim() || undefined,
      });
      toast.success("Post recorded", {
        description: "Added to posting history.",
      });
      onRecorded();
      onOpenChange(false);
      setUrl("");
      setNotes("");
      setPostedAt(nowIso());
      setSelectedDraftId("");
    } catch (err) {
      toast.error("Failed to record post", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md bg-card border-border">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <CheckCircle2 className="w-5 h-5 text-green-400" />
            Mark as Posted
          </DialogTitle>
        </DialogHeader>

        {/* Pre-selected draft preview */}
        {preSelectedDraft && (
          <div className="flex items-center gap-2 rounded-md bg-secondary/30 px-3 py-2">
            <PlatformBadge platform={preSelectedDraft.platform} />
            <p className="text-xs text-muted-foreground truncate">
              {preSelectedDraft.content.slice(0, 60)}…
            </p>
          </div>
        )}

        {/* Draft selector — only shown when no pre-selected draft */}
        {!preSelectedDraft && (
          <div className="space-y-2">
            <Label>Draft</Label>
            <Select value={selectedDraftId} onValueChange={(v) => setSelectedDraftId(v ?? "")}>
              <SelectTrigger className="bg-secondary/40">
                <SelectValue placeholder="Select a draft..." />
              </SelectTrigger>
              <SelectContent>
                {availableDrafts.length === 0 ? (
                  <div className="px-2 py-3 text-xs text-muted-foreground text-center">
                    No drafts available
                  </div>
                ) : (
                  availableDrafts.map((d) => (
                    <SelectItem key={d.id} value={d.id}>
                      <span className="flex items-center gap-2">
                        <span>{PLATFORM_LABELS[d.platform]}</span>
                        <span className="text-muted-foreground text-xs">
                          — {d.content.slice(0, 35)}…
                        </span>
                      </span>
                    </SelectItem>
                  ))
                )}
              </SelectContent>
            </Select>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="posted-at">Posted at</Label>
            <Input
              id="posted-at"
              type="datetime-local"
              value={postedAt}
              onChange={(e) => setPostedAt(e.target.value)}
              className="bg-secondary/40"
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="post-url">URL (optional)</Label>
            <Input
              id="post-url"
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://linkedin.com/posts/..."
              className="bg-secondary/40"
            />
          </div>

          <div className="space-y-2">
            <Label>Notes (optional)</Label>
            <Textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Any notes about this post..."
              className="bg-secondary/40 resize-none"
              rows={2}
            />
          </div>

          <Button
            type="submit"
            disabled={isSubmitting || (!activeDraft && !selectedDraftId)}
            className="w-full gap-2"
          >
            {isSubmitting ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <CheckCircle2 className="w-4 h-4" />
            )}
            {isSubmitting ? "Recording..." : "Record Post"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
