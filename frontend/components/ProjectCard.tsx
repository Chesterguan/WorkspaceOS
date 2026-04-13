"use client";

import Link from "next/link";
import { useState } from "react";
import { mutate } from "swr";
import { toast } from "sonner";
import {
  GitBranch,
  Clock,
  FileText,
  Circle,
  MoreHorizontal,
  Pencil,
  Trash2,
  Loader2,
  AlertTriangle,
} from "lucide-react";

import { formatDistanceToNow, cn } from "@/lib/utils";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { projects as projectsApi } from "@/lib/api";
import type { Project } from "@/lib/types";

interface ProjectCardProps {
  project: Project;
  /** ISO timestamp of the most recent completed sync (drives the status dot). */
  lastSyncAt?: string | null;
  /** Number of drafts associated with this project. */
  draftCount?: number;
}

function syncStatusTier(lastSyncAt?: string | null): "recent" | "stale" | "never" {
  if (!lastSyncAt) return "never";
  const diffDays = (Date.now() - new Date(lastSyncAt).getTime()) / 86_400_000;
  if (diffDays <= 7) return "recent";
  if (diffDays <= 30) return "stale";
  return "never";
}

const SYNC_STATUS_STYLES = {
  recent: "text-emerald-500",
  stale: "text-amber-400",
  never: "text-muted-foreground/50",
} as const;

const SYNC_STATUS_LABELS = {
  recent: "Synced recently",
  stale: "Sync is stale",
  never: "Never synced",
} as const;

export function ProjectCard({ project, lastSyncAt, draftCount }: ProjectCardProps) {
  const tier = syncStatusTier(lastSyncAt);
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  const isDemo = project.status === "demo";

  return (
    <>
      {/* The card uses an absolute-positioned Link as the click target so the
          dropdown menu button (layered on top with z-10) can swallow clicks
          without fighting a parent Link for navigation control. */}
      <Card className="group relative hover:border-primary/50 hover:bg-card/80 transition-all duration-200 h-full">
        <Link
          href={`/projects/${project.id}/overview`}
          aria-label={`Open ${project.name}`}
          className="absolute inset-0 z-0 rounded-lg"
        />

        <CardHeader className="pb-3 relative z-10 pointer-events-none">
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-center gap-2 min-w-0">
              <h3 className="font-semibold text-base leading-tight group-hover:text-primary transition-colors truncate">
                {project.name}
              </h3>
              {isDemo && (
                <Badge
                  className="text-[10px] px-1.5 py-0 bg-amber-500/15 text-amber-400 border-amber-500/30"
                  variant="outline"
                >
                  Demo
                </Badge>
              )}
            </div>

            <div className="flex items-center gap-1 shrink-0">
              {project.github_repo && (
                <Badge
                  variant="outline"
                  className="shrink-0 text-xs bg-secondary/50 font-mono"
                >
                  <GitBranch className="w-3 h-3 mr-1" />
                  {project.github_repo}
                </Badge>
              )}

              {!isDemo && (
                <div
                  className="pointer-events-auto"
                  onClick={(e) => {
                    e.stopPropagation();
                    e.preventDefault();
                  }}
                >
                  <DropdownMenu>
                    <DropdownMenuTrigger
                      render={
                        <button
                          type="button"
                          aria-label="Project actions"
                          className="inline-flex items-center justify-center w-7 h-7 rounded-md text-muted-foreground hover:text-foreground hover:bg-secondary/60 transition-colors focus:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                        />
                      }
                    >
                      <MoreHorizontal className="w-4 h-4" />
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem onClick={() => setEditOpen(true)}>
                        <Pencil className="w-3.5 h-3.5 mr-2" />
                        Edit
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        onClick={() => setDeleteOpen(true)}
                        className="text-destructive focus:text-destructive"
                      >
                        <Trash2 className="w-3.5 h-3.5 mr-2" />
                        Delete
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              )}
            </div>
          </div>

          {project.description && (
            <p className="text-sm text-muted-foreground line-clamp-2 mt-1">
              {project.description}
            </p>
          )}
        </CardHeader>

        <CardContent className="pt-0 relative z-10 pointer-events-none">
          <div className="flex items-center gap-4 text-xs text-muted-foreground">
            <span className="flex items-center gap-1.5" title={SYNC_STATUS_LABELS[tier]}>
              <Circle className={cn("w-2 h-2 fill-current", SYNC_STATUS_STYLES[tier])} />
              <Clock className="w-3.5 h-3.5" />
              {lastSyncAt ? `Synced ${formatDistanceToNow(lastSyncAt)}` : "Never synced"}
            </span>

            {draftCount !== undefined && draftCount > 0 && (
              <span className="flex items-center gap-1">
                <FileText className="w-3.5 h-3.5" />
                {draftCount} {draftCount === 1 ? "draft" : "drafts"}
              </span>
            )}
          </div>
        </CardContent>
      </Card>

      <EditProjectDialog
        project={project}
        open={editOpen}
        onOpenChange={setEditOpen}
      />
      <DeleteProjectDialog
        project={project}
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
      />
    </>
  );
}

// ---------------------------------------------------------------------------
// Edit dialog — updates name + description via PATCH /projects/{id}
// ---------------------------------------------------------------------------

interface EditDialogProps {
  project: Project;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function EditProjectDialog({ project, open, onOpenChange }: EditDialogProps) {
  const [name, setName] = useState(project.name);
  const [description, setDescription] = useState(project.description ?? "");
  const [focusNotes, setFocusNotes] = useState(project.focus_notes ?? "");
  const [saving, setSaving] = useState(false);

  // Reset the form whenever the dialog is re-opened for a (possibly different)
  // project so stale edits from a previous open don't bleed through.
  function handleOpenChange(next: boolean) {
    if (next) {
      setName(project.name);
      setDescription(project.description ?? "");
      setFocusNotes(project.focus_notes ?? "");
    }
    onOpenChange(next);
  }

  async function handleSave() {
    const trimmedName = name.trim();
    if (!trimmedName) {
      toast.error("Name cannot be empty");
      return;
    }
    setSaving(true);
    try {
      // Send focus_notes even when empty — empty string clears the pin.
      // description uses undefined-on-empty because the model stores NULL
      // and the UI shouldn't force the user to distinguish.
      await projectsApi.update(project.id, {
        name: trimmedName,
        description: description.trim() || undefined,
        focus_notes: focusNotes,
      });
      await mutate("/projects");
      toast.success("Project updated");
      onOpenChange(false);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to update project");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Edit project</DialogTitle>
          <DialogDescription>
            Update the display name and description. The slug and GitHub repo link
            stay the same.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-2">
            <Label htmlFor="project-name">Name</Label>
            <Input
              id="project-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={saving}
              maxLength={255}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="project-description">Description</Label>
            <Textarea
              id="project-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={saving}
              rows={3}
              placeholder="What is this project about?"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="project-focus-notes" className="flex items-center gap-2">
              Focus / commitments
              <span className="text-[10px] font-normal text-muted-foreground">
                pinned context the AI respects
              </span>
            </Label>
            <Textarea
              id="project-focus-notes"
              value={focusNotes}
              onChange={(e) => setFocusNotes(e.target.value)}
              disabled={saving}
              rows={4}
              placeholder="Deadlines, decisions, things-in-progress, what you want reports to emphasise this week…"
            />
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="ghost"
            onClick={() => onOpenChange(false)}
            disabled={saving}
          >
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={saving}>
            {saving && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Delete confirm — cascading deletes handled server-side via FK
// ---------------------------------------------------------------------------

interface DeleteDialogProps {
  project: Project;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function DeleteProjectDialog({ project, open, onOpenChange }: DeleteDialogProps) {
  const [deleting, setDeleting] = useState(false);

  async function handleDelete() {
    setDeleting(true);
    try {
      await projectsApi.delete(project.id);
      await mutate("/projects");
      toast.success(`Deleted "${project.name}"`);
      onOpenChange(false);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to delete project");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-destructive" />
            Delete project?
          </DialogTitle>
          <DialogDescription className="pt-2">
            This will permanently delete{" "}
            <span className="font-semibold text-foreground">{project.name}</span>{" "}
            and all of its drafts, memory entries, sync history, and cached
            workspace data. This cannot be undone.
          </DialogDescription>
        </DialogHeader>

        <DialogFooter>
          <Button
            variant="ghost"
            onClick={() => onOpenChange(false)}
            disabled={deleting}
          >
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={handleDelete}
            disabled={deleting}
          >
            {deleting && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
            Delete
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
