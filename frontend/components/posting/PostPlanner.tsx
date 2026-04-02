"use client";

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScheduleForm } from "@/components/posting/ScheduleForm";
import { MarkPostedDialog } from "@/components/posting/MarkPostedDialog";
import { PlatformBadge } from "@/components/PlatformBadge";
import { usePostSchedules } from "@/lib/hooks/usePosting";
import { useDrafts } from "@/lib/hooks/useDrafts";
import { posting } from "@/lib/api";
import { toast } from "sonner";
import {
  ChevronLeft,
  ChevronRight,
  CalendarDays,
  Plus,
  Trash2,
  Loader2,
  CheckCircle2,
} from "lucide-react";
import { formatDistanceToNow } from "@/lib/utils";
import type { PostSchedule, Draft } from "@/lib/types";
import { cn } from "@/lib/utils";

const WEEKDAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

// Map platform to a dot color for the calendar
const PLATFORM_DOT: Record<string, string> = {
  linkedin: "bg-blue-400",
  twitter: "bg-sky-400",
  xiaohongshu: "bg-red-400",
  medium_outline: "bg-emerald-400",
  github_release: "bg-purple-400",
};

interface PostPlannerProps {
  projectId: string;
}

export function PostPlanner({ projectId }: PostPlannerProps) {
  const today = new Date();
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth()); // 0-based

  // Fetch schedules for the visible calendar month
  const monthFrom = new Date(year, month, 1).toISOString();
  const monthTo = new Date(year, month + 1, 0, 23, 59, 59).toISOString();
  const { data: schedules, mutate: mutateSchedules } = usePostSchedules(
    projectId,
    monthFrom,
    monthTo,
  );

  // Separately fetch upcoming schedules from today forward (30-day lookahead)
  // so the Upcoming list always shows near-future items regardless of which
  // calendar month is currently displayed.
  const upcomingFrom = today.toISOString();
  const upcomingTo = new Date(
    today.getFullYear(),
    today.getMonth(),
    today.getDate() + 30,
    23,
    59,
    59,
  ).toISOString();
  const { data: upcomingSchedules } = usePostSchedules(
    projectId,
    upcomingFrom,
    upcomingTo,
  );
  const { data: draftsData } = useDrafts(projectId);
  const drafts: Draft[] = draftsData ?? [];

  const [scheduleDialogOpen, setScheduleDialogOpen] = useState(false);
  const [selectedDay, setSelectedDay] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [markPostedDraft, setMarkPostedDraft] = useState<Draft | null>(null);
  const [markPostedOpen, setMarkPostedOpen] = useState(false);

  function prevMonth() {
    if (month === 0) {
      setMonth(11);
      setYear((y) => y - 1);
    } else {
      setMonth((m) => m - 1);
    }
  }

  function nextMonth() {
    if (month === 11) {
      setMonth(0);
      setYear((y) => y + 1);
    } else {
      setMonth((m) => m + 1);
    }
  }

  // Build calendar grid
  const firstDay = new Date(year, month, 1).getDay(); // 0=Sun
  const daysInMonth = new Date(year, month + 1, 0).getDate();

  // Build a map from date string (YYYY-MM-DD) → schedules
  const schedulesByDay: Record<string, PostSchedule[]> = {};
  (schedules ?? []).forEach((s) => {
    const key = s.scheduled_for.slice(0, 10);
    if (!schedulesByDay[key]) schedulesByDay[key] = [];
    schedulesByDay[key].push(s);
  });

  function dayKey(d: number) {
    return `${year}-${String(month + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
  }

  async function handleDeleteSchedule(id: string) {
    setDeletingId(id);
    try {
      await posting.deleteSchedule(projectId, id);
      toast.success("Schedule removed");
      mutateSchedules();
    } catch (err) {
      toast.error("Failed to remove schedule", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setDeletingId(null);
    }
  }

  // Upcoming schedules sorted ascending — drawn from the dedicated lookahead
  // fetch so items outside the visible calendar month still appear here.
  const upcoming = [...(upcomingSchedules ?? [])].sort(
    (a, b) =>
      new Date(a.scheduled_for).getTime() - new Date(b.scheduled_for).getTime(),
  );

  return (
    <div className="space-y-6">
      {/* Calendar header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button variant="outline" size="sm" onClick={prevMonth} className="h-8 w-8 p-0">
            <ChevronLeft className="w-4 h-4" />
          </Button>
          <span className="text-base font-semibold">
            {MONTH_NAMES[month]} {year}
          </span>
          <Button variant="outline" size="sm" onClick={nextMonth} className="h-8 w-8 p-0">
            <ChevronRight className="w-4 h-4" />
          </Button>
        </div>
        <Button
          size="sm"
          onClick={() => {
            setSelectedDay(null);
            setScheduleDialogOpen(true);
          }}
          className="gap-1.5"
        >
          <Plus className="w-3.5 h-3.5" />
          Schedule Post
        </Button>
      </div>

      {/* Calendar grid */}
      <div className="rounded-lg border border-border overflow-hidden">
        {/* Weekday headers */}
        <div className="grid grid-cols-7 border-b border-border">
          {WEEKDAY_LABELS.map((d) => (
            <div
              key={d}
              className="py-2 text-center text-xs font-medium text-muted-foreground"
            >
              {d}
            </div>
          ))}
        </div>

        {/* Day cells */}
        <div className="grid grid-cols-7">
          {/* Empty cells before first day */}
          {Array.from({ length: firstDay }).map((_, i) => (
            <div key={`empty-${i}`} className="h-20 border-b border-r border-border/40 bg-secondary/5" />
          ))}

          {/* Day cells */}
          {Array.from({ length: daysInMonth }).map((_, i) => {
            const day = i + 1;
            const key = dayKey(day);
            const daySchedules = schedulesByDay[key] ?? [];
            const isToday =
              today.getFullYear() === year &&
              today.getMonth() === month &&
              today.getDate() === day;
            const col = (firstDay + i) % 7;
            const isLastCol = col === 6;

            return (
              <button
                key={key}
                type="button"
                onClick={() => {
                  setSelectedDay(key);
                  setScheduleDialogOpen(true);
                }}
                className={cn(
                  "h-20 p-1.5 text-left border-b border-border/40 transition-colors hover:bg-secondary/30 relative",
                  !isLastCol && "border-r",
                  isToday && "bg-primary/5",
                )}
              >
                <span
                  className={cn(
                    "text-xs font-medium inline-flex items-center justify-center w-5 h-5 rounded-full",
                    isToday
                      ? "bg-primary text-primary-foreground"
                      : "text-muted-foreground",
                  )}
                >
                  {day}
                </span>
                {/* Platform dots */}
                <div className="flex flex-wrap gap-0.5 mt-1">
                  {daySchedules.slice(0, 4).map((s) => (
                    <span
                      key={s.id}
                      className={cn(
                        "w-2 h-2 rounded-full shrink-0",
                        PLATFORM_DOT[s.platform] ?? "bg-zinc-400",
                      )}
                      title={s.platform}
                    />
                  ))}
                  {daySchedules.length > 4 && (
                    <span className="text-xs text-muted-foreground">
                      +{daySchedules.length - 4}
                    </span>
                  )}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Upcoming posts list */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide flex items-center gap-1.5">
          <CalendarDays className="w-3.5 h-3.5" />
          Upcoming
        </h3>

        {upcoming.length === 0 ? (
          <p className="text-sm text-muted-foreground py-4 text-center border border-dashed border-border rounded-lg">
            No upcoming scheduled posts.
          </p>
        ) : (
          <div className="space-y-2">
            {upcoming.map((s) => {
              const draft = drafts.find((d) => d.id === s.draft_id);
              return (
                <div
                  key={s.id}
                  className="flex items-start gap-3 p-3 rounded-lg border border-border bg-card hover:border-border/70 transition-colors"
                >
                  <div className="flex-1 min-w-0 space-y-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <PlatformBadge platform={s.platform} />
                      <span className="text-xs text-muted-foreground">
                        {new Date(s.scheduled_for).toLocaleString()}
                      </span>
                      <Badge
                        variant="outline"
                        className="text-xs bg-yellow-600/15 text-yellow-400 border-yellow-600/30"
                      >
                        scheduled
                      </Badge>
                    </div>
                    {draft && (
                      <p className="text-xs text-muted-foreground truncate">
                        {draft.content.slice(0, 80)}…
                      </p>
                    )}
                    {s.notes && (
                      <p className="text-xs text-muted-foreground/70 italic">
                        {s.notes}
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    {draft && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 px-2 text-xs gap-1 hover:text-green-400"
                        onClick={() => {
                          setMarkPostedDraft(draft);
                          setMarkPostedOpen(true);
                        }}
                      >
                        <CheckCircle2 className="w-3 h-3" />
                        Posted
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 w-7 p-0 hover:text-destructive"
                      onClick={() => handleDeleteSchedule(s.id)}
                      disabled={deletingId === s.id}
                    >
                      {deletingId === s.id ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <Trash2 className="w-3.5 h-3.5" />
                      )}
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Schedule dialog */}
      <Dialog open={scheduleDialogOpen} onOpenChange={setScheduleDialogOpen}>
        <DialogContent className="sm:max-w-md bg-card border-border">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <CalendarDays className="w-5 h-5 text-primary" />
              Schedule a Post
              {selectedDay && (
                <span className="text-sm font-normal text-muted-foreground">
                  — {new Date(selectedDay + "T12:00:00").toLocaleDateString()}
                </span>
              )}
            </DialogTitle>
          </DialogHeader>
          <ScheduleForm
            projectId={projectId}
            drafts={drafts}
            defaultDate={selectedDay ?? undefined}
            onCreated={() => {
              setScheduleDialogOpen(false);
              mutateSchedules();
            }}
            onCancel={() => setScheduleDialogOpen(false)}
          />
        </DialogContent>
      </Dialog>

      {/* Mark posted dialog */}
      <MarkPostedDialog
        open={markPostedOpen}
        onOpenChange={setMarkPostedOpen}
        projectId={projectId}
        draft={markPostedDraft}
        onRecorded={() => {
          setMarkPostedOpen(false);
          setMarkPostedDraft(null);
          mutateSchedules();
        }}
      />
    </div>
  );
}
