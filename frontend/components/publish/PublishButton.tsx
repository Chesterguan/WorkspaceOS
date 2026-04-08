"use client";

import { useState, useEffect, useCallback } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CopyDraftButton } from "@/components/publish/CopyDraftButton";
import { publish, drafts as draftsApi, linkedin as linkedinApi } from "@/lib/api";
import NextLink from "next/link";
import { toast } from "sonner";
import {
  Send,
  GitFork,
  Loader2,
  ExternalLink,
  AlertCircle,
  Link,
  Settings,
} from "lucide-react";
import type { Platform } from "@/lib/types";
import { PLATFORM_LABELS } from "@/components/PlatformBadge";

// ─── Platform-specific helpers ────────────────────────────────────────────────

const MANUAL_PLATFORMS: Platform[] = ["medium_outline", "xiaohongshu", "twitter"];

function isManualPlatform(platform: Platform): boolean {
  return MANUAL_PLATFORMS.includes(platform);
}

// ─── GitHub Release Dialog ────────────────────────────────────────────────────

interface GitHubReleaseDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string;
  draftId: string;
  onPublished: () => void;
}

function GitHubReleaseDialog({
  open,
  onOpenChange,
  projectId,
  draftId,
  onPublished,
}: GitHubReleaseDialogProps) {
  const [tagName, setTagName] = useState("");
  const [targetBranch, setTargetBranch] = useState("main");
  const [isDraftRelease, setIsDraftRelease] = useState(false);
  const [isPrerelease, setIsPrerelease] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!tagName.trim()) return;

    setIsSubmitting(true);
    try {
      const result = await publish.githubRelease(projectId, draftId, {
        tag_name: tagName.trim(),
        target_branch: targetBranch.trim() || "main",
        draft_release: isDraftRelease,
        prerelease: isPrerelease,
      });

      if (!result.success) {
        throw new Error(result.error ?? "Publish failed");
      }

      toast.success("GitHub Release published!", {
        description: result.post_url ? (
          <a
            href={result.post_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 underline text-sky-400"
          >
            View release <ExternalLink className="w-3 h-3" />
          </a>
        ) : `Tag ${tagName} created.`,
      });

      // Mark draft as published
      await draftsApi.update(projectId, draftId, { status: "published" });

      onPublished();
      onOpenChange(false);
      setTagName("");
    } catch (err) {
      toast.error("GitHub release failed", {
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
            <GitFork className="w-5 h-5 text-purple-400" />
            Publish GitHub Release
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4 pt-2">
          <div className="space-y-2">
            <Label htmlFor="tag-name">
              Tag name <span className="text-destructive">*</span>
            </Label>
            <Input
              id="tag-name"
              value={tagName}
              onChange={(e) => setTagName(e.target.value)}
              placeholder="v1.2.0"
              className="bg-secondary/40"
              required
              autoFocus
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="target-branch">Target branch</Label>
            <Input
              id="target-branch"
              value={targetBranch}
              onChange={(e) => setTargetBranch(e.target.value)}
              placeholder="main"
              className="bg-secondary/40"
            />
          </div>

          <div className="space-y-2.5">
            <label className="flex items-center gap-2.5 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={isDraftRelease}
                onChange={(e) => setIsDraftRelease(e.target.checked)}
                className="w-4 h-4 rounded border-border bg-secondary accent-purple-500"
              />
              <span className="text-sm text-muted-foreground">
                Save as draft release (not published publicly)
              </span>
            </label>
            <label className="flex items-center gap-2.5 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={isPrerelease}
                onChange={(e) => setIsPrerelease(e.target.checked)}
                className="w-4 h-4 rounded border-border bg-secondary accent-purple-500"
              />
              <span className="text-sm text-muted-foreground">
                Mark as pre-release
              </span>
            </label>
          </div>

          <div className="flex gap-2 pt-1">
            <Button
              type="button"
              variant="outline"
              className="flex-1"
              onClick={() => onOpenChange(false)}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              className="flex-1 gap-1.5 bg-green-700 hover:bg-green-600 text-white border-0"
              disabled={isSubmitting || !tagName.trim()}
            >
              {isSubmitting ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <GitFork className="w-3.5 h-3.5" />
              )}
              {isSubmitting ? "Publishing..." : "Publish Release"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ─── Mark as Posted Dialog ────────────────────────────────────────────────────

interface MarkPostedDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string;
  draftId: string;
  platformLabel: string;
  onPublished: () => void;
}

function MarkPostedDialog({
  open,
  onOpenChange,
  projectId,
  draftId,
  platformLabel,
  onPublished,
}: MarkPostedDialogProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleMark() {
    setIsSubmitting(true);
    try {
      await draftsApi.update(projectId, draftId, { status: "published" });
      toast.success(`Marked as posted to ${platformLabel}`);
      onPublished();
      onOpenChange(false);
    } catch (err) {
      toast.error("Failed to mark as posted", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm bg-card border-border">
        <DialogHeader>
          <DialogTitle>Mark as Posted</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 pt-2">
          <p className="text-sm text-muted-foreground">
            Confirm that you have manually posted this draft to {platformLabel}.
            This will update the draft status to Published.
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              className="flex-1"
              onClick={() => onOpenChange(false)}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button
              className="flex-1 gap-1.5"
              onClick={handleMark}
              disabled={isSubmitting}
            >
              {isSubmitting ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : null}
              {isSubmitting ? "Saving..." : "Mark as Posted"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ─── LinkedIn Confirm Dialog ──────────────────────────────────────────────────

interface LinkedInConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string;
  draftId: string;
  onPublished: () => void;
}

function LinkedInConfirmDialog({
  open,
  onOpenChange,
  projectId,
  draftId,
  onPublished,
}: LinkedInConfirmDialogProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handlePost() {
    setIsSubmitting(true);
    try {
      const result = await publish.linkedin(projectId, draftId);

      if (!result.success) {
        const isAuthError =
          result.error?.toLowerCase().includes("connect") ||
          result.error?.toLowerCase().includes("token") ||
          result.error?.toLowerCase().includes("auth") ||
          result.error?.toLowerCase().includes("oauth");

        if (isAuthError) {
          toast.error("LinkedIn not connected", {
            description:
              "Click 'Connect LinkedIn' to authorize your account, then try again.",
            duration: 8000,
          });
        } else {
          throw new Error(result.error ?? "Post failed");
        }
        return;
      }

      toast.success("Posted to LinkedIn!", {
        description: result.post_url ? (
          <a
            href={result.post_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 underline text-sky-400"
          >
            View post <ExternalLink className="w-3 h-3" />
          </a>
        ) : "Your post is live.",
      });

      await draftsApi.update(projectId, draftId, { status: "published" });

      onPublished();
      onOpenChange(false);
    } catch (err) {
      toast.error("LinkedIn post failed", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm bg-card border-border">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Link className="w-5 h-5 text-blue-400" />
            Post to LinkedIn
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-4 pt-2">
          <p className="text-sm text-muted-foreground">
            This will publish the draft content to your LinkedIn profile. This
            action cannot be undone.
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              className="flex-1"
              onClick={() => onOpenChange(false)}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button
              className="flex-1 gap-1.5 bg-blue-700 hover:bg-blue-600 text-white border-0"
              onClick={handlePost}
              disabled={isSubmitting}
            >
              {isSubmitting ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Send className="w-3.5 h-3.5" />
              )}
              {isSubmitting ? "Posting..." : "Post now"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ─── Dev.to Confirm Dialog ────────────────────────────────────────────────────

interface DevtoConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string;
  draftId: string;
  onPublished: () => void;
}

function DevtoConfirmDialog({
  open,
  onOpenChange,
  projectId,
  draftId,
  onPublished,
}: DevtoConfirmDialogProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handlePost() {
    setIsSubmitting(true);
    try {
      const result = await publish.devto(projectId, draftId);

      if (!result.success) {
        const isKeyError =
          result.error?.toLowerCase().includes("api_key") ||
          result.error?.toLowerCase().includes("configured") ||
          result.error?.toLowerCase().includes("settings");

        if (isKeyError) {
          toast.error("Dev.to API key not configured", {
            description:
              "Add your Dev.to API key in Settings > AI & API Keys, then try again.",
            duration: 8000,
          });
        } else {
          throw new Error(result.error ?? "Post failed");
        }
        return;
      }

      toast.success("Published to Dev.to!", {
        description: result.post_url ? (
          <a
            href={result.post_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 underline text-sky-400"
          >
            View article <ExternalLink className="w-3 h-3" />
          </a>
        ) : "Your article is live.",
      });

      await draftsApi.update(projectId, draftId, { status: "published" });

      onPublished();
      onOpenChange(false);
    } catch (err) {
      toast.error("Dev.to publish failed", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm bg-card border-border">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Send className="w-5 h-5 text-violet-400" />
            Publish to Dev.to
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-4 pt-2">
          <p className="text-sm text-muted-foreground">
            This will publish the draft as an article on Dev.to using your
            configured API key. This action cannot be undone.
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              className="flex-1"
              onClick={() => onOpenChange(false)}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button
              className="flex-1 gap-1.5 bg-violet-700 hover:bg-violet-600 text-white border-0"
              onClick={handlePost}
              disabled={isSubmitting}
            >
              {isSubmitting ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Send className="w-3.5 h-3.5" />
              )}
              {isSubmitting ? "Publishing..." : "Publish now"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ─── Hashnode Confirm Dialog ─────────────────────────────────────────────

interface HashnodeConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string;
  draftId: string;
  onPublished: () => void;
}

function HashnodeConfirmDialog({
  open,
  onOpenChange,
  projectId,
  draftId,
  onPublished,
}: HashnodeConfirmDialogProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handlePost() {
    setIsSubmitting(true);
    try {
      const result = await publish.hashnode(projectId, draftId);

      if (!result.success) {
        const isKeyError =
          result.error?.toLowerCase().includes("api_key") ||
          result.error?.toLowerCase().includes("configured") ||
          result.error?.toLowerCase().includes("settings");

        if (isKeyError) {
          toast.error("Hashnode API key not configured", {
            description:
              "Add your Hashnode API key and Publication ID in Settings > AI & API Keys, then try again.",
            duration: 8000,
          });
        } else {
          throw new Error(result.error ?? "Post failed");
        }
        return;
      }

      toast.success("Published to Hashnode!", {
        description: result.post_url ? (
          <a
            href={result.post_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 underline text-sky-400"
          >
            View article <ExternalLink className="w-3 h-3" />
          </a>
        ) : "Your article is live.",
      });

      await draftsApi.update(projectId, draftId, { status: "published" });

      onPublished();
      onOpenChange(false);
    } catch (err) {
      toast.error("Hashnode publish failed", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm bg-card border-border">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Send className="w-5 h-5 text-blue-400" />
            Publish to Hashnode
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-4 pt-2">
          <p className="text-sm text-muted-foreground">
            This will publish the draft as an article on Hashnode using your
            configured API key. This action cannot be undone.
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              className="flex-1"
              onClick={() => onOpenChange(false)}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button
              className="flex-1 gap-1.5 bg-blue-700 hover:bg-blue-600 text-white border-0"
              onClick={handlePost}
              disabled={isSubmitting}
            >
              {isSubmitting ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Send className="w-3.5 h-3.5" />
              )}
              {isSubmitting ? "Publishing..." : "Publish now"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ─── Main PublishButton ───────────────────────────────────────────────────────

interface PublishButtonProps {
  projectId: string;
  draftId: string;
  platform: Platform;
  content: string;
  onPublished: () => void;
  /** Compact mode — used inside DraftCard for smaller footprint */
  compact?: boolean;
}

export function PublishButton({
  projectId,
  draftId,
  platform,
  content,
  onPublished,
  compact = false,
}: PublishButtonProps) {
  const [githubDialogOpen, setGitForkDialogOpen] = useState(false);
  const [linkedInDialogOpen, setLinkedInDialogOpen] = useState(false);
  const [devtoDialogOpen, setDevtoDialogOpen] = useState(false);
  const [hashnodeDialogOpen, setHashnodeDialogOpen] = useState(false);
  const [markPostedDialogOpen, setMarkPostedDialogOpen] = useState(false);

  // LinkedIn connection state — only fetched when the platform is linkedin
  const [linkedInConnected, setLinkedInConnected] = useState<boolean | null>(null);

  const platformLabel = PLATFORM_LABELS[platform];

  const checkLinkedInStatus = useCallback(async () => {
    try {
      const status = await linkedinApi.getStatus();
      setLinkedInConnected(status.connected);
    } catch {
      setLinkedInConnected(false);
    }
  }, []);

  useEffect(() => {
    if (platform === "linkedin") {
      checkLinkedInStatus();
    }
  }, [platform, checkLinkedInStatus]);

  // ── LinkedIn: show status or direct to Settings to connect ───────────────
  if (platform === "linkedin") {
    // Loading state while we check connection
    if (linkedInConnected === null) {
      return (
        <Button
          variant="outline"
          size={compact ? "sm" : "sm"}
          disabled
          className="gap-1.5 text-xs border-blue-600/30 text-blue-400"
        >
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
          LinkedIn
        </Button>
      );
    }

    if (!linkedInConnected) {
      // Direct the user to the global Settings page to connect — OAuth is
      // configured once there, not per-draft.
      return (
        <NextLink href="/settings">
          <Button
            variant="outline"
            size={compact ? "sm" : "sm"}
            className="gap-1.5 text-xs border-blue-600/50 text-blue-400 hover:bg-blue-950/30"
          >
            <Settings className="w-3.5 h-3.5" />
            Connect in Settings
          </Button>
        </NextLink>
      );
    }

    // Connected — show post button
    return (
      <>
        <Button
          size={compact ? "sm" : "sm"}
          onClick={() => setLinkedInDialogOpen(true)}
          className="gap-1.5 text-xs bg-blue-700 hover:bg-blue-600 text-white border-0"
        >
          <Send className="w-3.5 h-3.5" />
          {compact ? "Post" : "Post to LinkedIn"}
        </Button>

        <LinkedInConfirmDialog
          open={linkedInDialogOpen}
          onOpenChange={setLinkedInDialogOpen}
          projectId={projectId}
          draftId={draftId}
          onPublished={onPublished}
        />
      </>
    );
  }

  // ── Manual platforms: copy + mark posted ─────────────────────────────────
  if (isManualPlatform(platform)) {
    return (
      <>
        <div className="flex flex-col gap-1.5">
          <CopyDraftButton
            content={content}
            platformLabel={platformLabel}
            size={compact ? "sm" : "sm"}
          />
          <button
            type="button"
            onClick={() => setMarkPostedDialogOpen(true)}
            className="text-xs text-muted-foreground hover:text-foreground underline-offset-2 hover:underline transition-colors self-start"
          >
            Mark as Posted
          </button>
        </div>

        <MarkPostedDialog
          open={markPostedDialogOpen}
          onOpenChange={setMarkPostedDialogOpen}
          projectId={projectId}
          draftId={draftId}
          platformLabel={platformLabel}
          onPublished={onPublished}
        />
      </>
    );
  }

  // ── GitHub Release ────────────────────────────────────────────────────────
  if (platform === "github_release") {
    return (
      <>
        <Button
          size={compact ? "sm" : "sm"}
          onClick={() => setGitForkDialogOpen(true)}
          className="gap-1.5 text-xs bg-green-700 hover:bg-green-600 text-white border-0"
        >
          <GitFork className="w-3.5 h-3.5" />
          {compact ? "Release" : "Publish Release"}
        </Button>

        <GitHubReleaseDialog
          open={githubDialogOpen}
          onOpenChange={setGitForkDialogOpen}
          projectId={projectId}
          draftId={draftId}
          onPublished={onPublished}
        />
      </>
    );
  }

  // ── Dev.to ────────────────────────────────────────────────────────────────
  if (platform === "devto") {
    return (
      <>
        <Button
          size={compact ? "sm" : "sm"}
          onClick={() => setDevtoDialogOpen(true)}
          className="gap-1.5 text-xs bg-violet-700 hover:bg-violet-600 text-white border-0"
        >
          <Send className="w-3.5 h-3.5" />
          {compact ? "Publish" : "Publish to Dev.to"}
        </Button>

        <DevtoConfirmDialog
          open={devtoDialogOpen}
          onOpenChange={setDevtoDialogOpen}
          projectId={projectId}
          draftId={draftId}
          onPublished={onPublished}
        />
      </>
    );
  }

  // ── Hashnode ──────────────────────────────────────────────────────────────
  if (platform === "hashnode") {
    return (
      <>
        <Button
          size={compact ? "sm" : "sm"}
          onClick={() => setHashnodeDialogOpen(true)}
          className="gap-1.5 text-xs bg-blue-700 hover:bg-blue-600 text-white border-0"
        >
          <Send className="w-3.5 h-3.5" />
          {compact ? "Publish" : "Publish to Hashnode"}
        </Button>

        <HashnodeConfirmDialog
          open={hashnodeDialogOpen}
          onOpenChange={setHashnodeDialogOpen}
          projectId={projectId}
          draftId={draftId}
          onPublished={onPublished}
        />
      </>
    );
  }

  // Fallback — should never reach for known platforms
  return (
    <div className="flex items-center gap-1 text-xs text-muted-foreground">
      <AlertCircle className="w-3.5 h-3.5" />
      Unsupported platform
    </div>
  );
}
