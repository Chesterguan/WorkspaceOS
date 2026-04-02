"use client";

import { useState, useEffect, use } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { DraftEditor } from "@/components/DraftEditor";
import { DraftVersionHistory } from "@/components/DraftVersionHistory";
import { DraftGeneratePanel } from "@/components/DraftGeneratePanel";
import { PlatformBadge } from "@/components/PlatformBadge";
import { PublishButton } from "@/components/publish/PublishButton";
import { useProjectContext } from "@/components/ProjectContext";
import { useDraft, useDraftVersions } from "@/lib/hooks/useDrafts";
import { drafts } from "@/lib/api";
import { toast } from "sonner";
import {
  Save,
  Loader2,
  ChevronDown,
  Sparkles,
  ArrowLeft,
  AlertCircle,
  Trash2,
} from "lucide-react";
import type { Draft, DraftStatus } from "@/lib/types";

const STATUS_LABELS: Record<DraftStatus, string> = {
  draft: "Draft",
  approved: "Approved",
  archived: "Archived",
  published: "Published",
};

const STATUS_COLORS: Record<DraftStatus, string> = {
  draft: "bg-yellow-600/20 text-yellow-400 border-yellow-600/30",
  approved: "bg-green-600/20 text-green-400 border-green-600/30",
  archived: "bg-zinc-600/20 text-zinc-400 border-zinc-600/30",
  published: "bg-blue-600/20 text-blue-400 border-blue-600/30",
};

interface DraftStudioPageProps {
  params: Promise<{ projectId: string; draftId: string }>;
}

export default function DraftStudioPage({ params }: DraftStudioPageProps) {
  const { projectId, draftId } = use(params);
  const { project } = useProjectContext();
  const router = useRouter();

  const { data: draft, error, isLoading, mutate } = useDraft(projectId, draftId);
  const { data: versions, mutate: mutateVersions } = useDraftVersions(projectId, draftId);

  const [content, setContent] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [isChangingStatus, setIsChangingStatus] = useState(false);
  const [generateOpen, setGenerateOpen] = useState(false);
  const [previewDraft, setPreviewDraft] = useState<Draft | null>(null);

  useEffect(() => {
    if (draft && !previewDraft) {
      setContent(draft.content);
    }
  }, [draft, previewDraft]);

  const activeDraft = previewDraft ?? draft;

  async function handleSave() {
    if (!draft) return;
    setIsSaving(true);
    try {
      await drafts.update(projectId, draftId, { content });
      await Promise.all([mutate(), mutateVersions()]);
      setPreviewDraft(null);
      toast.success("Draft saved", {
        description: "A new version has been created.",
      });
    } catch (err) {
      toast.error("Save failed", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setIsSaving(false);
    }
  }

  async function handleStatusChange(status: DraftStatus) {
    if (!draft) return;
    setIsChangingStatus(true);
    try {
      await drafts.update(projectId, draftId, { status });
      await mutate();
      toast.success(`Status changed to ${STATUS_LABELS[status]}`);
    } catch (err) {
      toast.error("Failed to change status", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setIsChangingStatus(false);
    }
  }

  async function handleDelete() {
    if (!window.confirm("Delete this draft? This cannot be undone.")) return;
    try {
      await drafts.delete(projectId, draftId);
      toast.success("Draft deleted");
      router.push(`/projects/${projectId}/drafts`);
    } catch (err) {
      toast.error("Failed to delete draft", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    }
  }

  function handleSelectVersion(version: Draft) {
    setPreviewDraft(version);
    setContent(version.content);
    toast.info(`Viewing version ${version.version}`, {
      description: "Edit and save to create a new version based on this.",
    });
  }

  if (isLoading) {
    return (
      <div className="flex flex-col h-full">
        <div className="h-12 border-b border-border bg-card/50 animate-pulse" />
        <div className="flex flex-1 overflow-hidden">
          <div className="flex-[3] p-6 space-y-3 animate-pulse">
            <div className="h-5 w-32 bg-secondary rounded" />
            <div className="h-4 w-full bg-secondary/60 rounded" />
            <div className="h-4 w-5/6 bg-secondary/60 rounded" />
            <div className="h-4 w-4/6 bg-secondary/60 rounded" />
          </div>
          <div className="flex-[2] p-6 space-y-4 border-l border-border animate-pulse">
            <div className="h-6 w-24 bg-secondary rounded" />
            <div className="h-6 w-20 bg-secondary/60 rounded" />
            <div className="h-px bg-secondary/40 rounded" />
            <div className="h-4 w-28 bg-secondary/40 rounded" />
            <div className="h-4 w-36 bg-secondary/40 rounded" />
          </div>
        </div>
      </div>
    );
  }

  if (error || !draft) {
    return (
      <div className="p-8">
        <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <AlertCircle className="w-4 h-4 shrink-0" />
          {error ? `Failed to load draft: ${error.message}` : "Draft not found"}
        </div>
      </div>
    );
  }

  const hasUnsavedChanges = content !== draft.content;

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-6 py-3 border-b border-border bg-card/50">
        <div className="flex items-center gap-3">
          <Link href={`/projects/${projectId}/drafts`}>
            <Button variant="ghost" size="sm" className="gap-1.5 text-muted-foreground text-xs">
              <ArrowLeft className="w-3.5 h-3.5" />
              Drafts
            </Button>
          </Link>
        </div>

        <div className="flex items-center gap-2">
          {hasUnsavedChanges && (
            <span className="text-xs text-muted-foreground">Unsaved changes</span>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={handleDelete}
            className="gap-1.5 text-xs text-muted-foreground hover:text-destructive"
          >
            <Trash2 className="w-3.5 h-3.5" />
            Delete
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setGenerateOpen(true)}
            className="gap-1.5 text-xs"
          >
            <Sparkles className="w-3.5 h-3.5" />
            Regenerate
          </Button>
          <Button
            size="sm"
            onClick={handleSave}
            disabled={isSaving || !hasUnsavedChanges}
            className="gap-1.5"
          >
            {isSaving ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Save className="w-3.5 h-3.5" />
            )}
            {isSaving ? "Saving..." : "Save"}
          </Button>
        </div>
      </div>

      {/* Two-column layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: editor (60%) */}
        <div className="flex-[3] p-6 overflow-y-auto border-r border-border">
          <DraftEditor
            content={content}
            platform={draft.platform}
            onChange={setContent}
          />
        </div>

        {/* Right: metadata and versions (40%) */}
        <div className="flex-[2] p-6 overflow-y-auto space-y-5">
          {/* Platform and status */}
          <div className="space-y-3">
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground font-medium uppercase tracking-wide">
                Platform
              </p>
              <PlatformBadge platform={draft.platform} />
            </div>

            <div className="space-y-1">
              <p className="text-xs text-muted-foreground font-medium uppercase tracking-wide">
                Status
              </p>
              <DropdownMenu>
                <DropdownMenuTrigger
                  className={`inline-flex items-center gap-2 h-7 px-3 text-xs rounded-md border font-medium transition-colors focus:outline-none disabled:pointer-events-none disabled:opacity-50 ${STATUS_COLORS[draft.status]}`}
                  disabled={isChangingStatus}
                  render={<button type="button" />}
                >
                  {isChangingStatus ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <span className="capitalize">{STATUS_LABELS[draft.status]}</span>
                  )}
                  <ChevronDown className="w-3 h-3" />
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start">
                  {(["draft", "approved", "archived"] as DraftStatus[]).map((s) => (
                    <DropdownMenuItem
                      key={s}
                      onClick={() => handleStatusChange(s)}
                      className={draft.status === s ? "text-primary" : ""}
                    >
                      {STATUS_LABELS[s]}
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>

          {/* Publish action — shown prominently when draft is approved */}
          {draft.status === "approved" && (
            <div className="rounded-md border border-green-600/30 bg-green-950/20 px-4 py-3 space-y-2">
              <p className="text-xs text-green-400 font-medium uppercase tracking-wide">
                Ready to publish
              </p>
              <PublishButton
                projectId={projectId}
                draftId={draftId}
                platform={draft.platform}
                content={content}
                onPublished={async () => {
                  await mutate();
                }}
              />
            </div>
          )}

          <Separator />

          {/* Version preview indicator */}
          {previewDraft && (
            <div className="flex items-center justify-between rounded-md bg-yellow-950/30 border border-yellow-600/30 px-3 py-2 text-xs text-yellow-400">
              <span>Viewing version {previewDraft.version}</span>
              <button
                type="button"
                onClick={() => {
                  setPreviewDraft(null);
                  setContent(draft.content);
                }}
                className="hover:underline"
              >
                Back to latest
              </button>
            </div>
          )}

          {/* Version history */}
          <DraftVersionHistory
            versions={versions ?? []}
            currentVersion={draft.version}
            onSelectVersion={handleSelectVersion}
          />
        </div>
      </div>

      <DraftGeneratePanel
        projectId={projectId}
        open={generateOpen}
        onOpenChange={setGenerateOpen}
        onGenerated={(newDraftId) => {
          router.push(`/projects/${projectId}/drafts/${newDraftId}`);
        }}
      />
    </div>
  );
}
