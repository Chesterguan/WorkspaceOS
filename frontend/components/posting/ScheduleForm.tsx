"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Loader2, CalendarCheck } from "lucide-react";
import { posting } from "@/lib/api";
import { toast } from "sonner";
import { PlatformBadge, PLATFORM_LABELS } from "@/components/PlatformBadge";
import type { Draft, PostScheduleCreate } from "@/lib/types";

interface ScheduleFormProps {
  projectId: string;
  drafts: Draft[];
  defaultDate?: string; // ISO date string YYYY-MM-DD
  onCreated: () => void;
  onCancel?: () => void;
}

export function ScheduleForm({
  projectId,
  drafts,
  defaultDate,
  onCreated,
  onCancel,
}: ScheduleFormProps) {
  const [draftId, setDraftId] = useState("");
  const [scheduledDate, setScheduledDate] = useState(
    defaultDate ?? new Date().toISOString().slice(0, 10),
  );
  const [scheduledTime, setScheduledTime] = useState("09:00");
  const [notes, setNotes] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const selectedDraft = drafts.find((d) => d.id === draftId);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!draftId) {
      toast.error("Select a draft to schedule");
      return;
    }

    const scheduledAt = new Date(`${scheduledDate}T${scheduledTime}:00`).toISOString();

    const data: PostScheduleCreate = {
      draft_id: draftId,
      platform: selectedDraft!.platform,
      scheduled_for: scheduledAt,
      notes: notes.trim() || undefined,
    };

    setIsSubmitting(true);
    try {
      await posting.createSchedule(projectId, data);
      toast.success("Post scheduled", {
        description: `Scheduled for ${new Date(scheduledAt).toLocaleString()}`,
      });
      onCreated();
    } catch (err) {
      toast.error("Failed to schedule post", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setIsSubmitting(false);
    }
  }

  const approvedDrafts = drafts.filter(
    (d) => d.status === "draft" || d.status === "approved",
  );

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="space-y-2">
        <Label>Draft</Label>
        <Select value={draftId} onValueChange={(v) => setDraftId(v ?? "")}>
          <SelectTrigger className="bg-secondary/40">
            <SelectValue placeholder="Select a draft..." />
          </SelectTrigger>
          <SelectContent>
            {approvedDrafts.length === 0 ? (
              <div className="px-2 py-3 text-xs text-muted-foreground text-center">
                No drafts available
              </div>
            ) : (
              approvedDrafts.map((d) => (
                <SelectItem key={d.id} value={d.id}>
                  <span className="flex items-center gap-2">
                    <span>{PLATFORM_LABELS[d.platform]}</span>
                    <span className="text-muted-foreground text-xs truncate max-w-32">
                      — {d.content.slice(0, 40)}…
                    </span>
                  </span>
                </SelectItem>
              ))
            )}
          </SelectContent>
        </Select>
      </div>

      {/* Platform auto-filled from draft */}
      {selectedDraft && (
        <div className="flex items-center gap-2 rounded-md bg-secondary/30 px-3 py-2">
          <span className="text-xs text-muted-foreground">Platform:</span>
          <PlatformBadge platform={selectedDraft.platform} />
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-2">
          <Label htmlFor="sched-date">Date</Label>
          <Input
            id="sched-date"
            type="date"
            value={scheduledDate}
            onChange={(e) => setScheduledDate(e.target.value)}
            className="bg-secondary/40"
            required
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="sched-time">Time</Label>
          <Input
            id="sched-time"
            type="time"
            value={scheduledTime}
            onChange={(e) => setScheduledTime(e.target.value)}
            className="bg-secondary/40"
            required
          />
        </div>
      </div>

      <div className="space-y-2">
        <Label>Notes (optional)</Label>
        <Textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Any scheduling notes or reminders..."
          className="bg-secondary/40 resize-none"
          rows={2}
        />
      </div>

      <div className="flex gap-2">
        <Button type="submit" disabled={isSubmitting} className="flex-1 gap-2">
          {isSubmitting ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <CalendarCheck className="w-4 h-4" />
          )}
          {isSubmitting ? "Scheduling..." : "Schedule Post"}
        </Button>
        {onCancel && (
          <Button type="button" variant="outline" onClick={onCancel}>
            Cancel
          </Button>
        )}
      </div>
    </form>
  );
}
