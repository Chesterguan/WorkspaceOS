"use client";

import { use, useState, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { BlogEditor } from "@/components/blog/BlogEditor";
import { BlogVersionHistory } from "@/components/blog/BlogVersionHistory";
import { AngleTagInput } from "@/components/AngleTagInput";
import { useProjectContext } from "@/components/ProjectContext";
import { useBlogPost, useBlogVersions } from "@/lib/hooks/useBlog";
import { blog } from "@/lib/api";
import { toast } from "sonner";
import {
  ArrowLeft,
  Loader2,
  Save,
  History,
  Sparkles,
  Trash2,
  Globe,
  FileText,
  AlertCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { BlogPostVersion } from "@/lib/types";

interface BlogPostPageProps {
  params: Promise<{ projectId: string; postId: string }>;
}

export default function BlogPostPage({ params }: BlogPostPageProps) {
  const { postId } = use(params);
  const { project } = useProjectContext();
  const router = useRouter();

  const { data: post, error, isLoading, mutate } = useBlogPost(project.id, postId);
  const { data: versions, mutate: mutateVersions } = useBlogVersions(project.id, postId);

  const [title, setTitle] = useState<string | null>(null);
  const [content, setContent] = useState<string | null>(null);
  const [isDirty, setIsDirty] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [showVersions, setShowVersions] = useState(false);

  // Initialize local state from fetched post on first load
  const currentTitle = title ?? post?.title ?? "";
  const currentContent = content ?? post?.content ?? "";

  function handleTitleChange(val: string) {
    setTitle(val);
    setIsDirty(true);
  }

  function handleContentChange(val: string) {
    setContent(val);
    setIsDirty(true);
  }

  async function handleSave() {
    if (!post) return;
    setIsSaving(true);
    try {
      await blog.update(project.id, post.id, {
        title: currentTitle,
        content: currentContent,
      });
      await mutate();
      await mutateVersions();
      setIsDirty(false);
      toast.success("Post saved");
    } catch (err) {
      toast.error("Failed to save", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setIsSaving(false);
    }
  }

  async function handleToggleStatus() {
    if (!post) return;
    const newStatus = post.status === "draft" ? "published" : "draft";
    try {
      await blog.update(project.id, post.id, { status: newStatus });
      await mutate();
      toast.success(
        newStatus === "published" ? "Post published" : "Post moved to draft",
      );
    } catch (err) {
      toast.error("Failed to update status", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    }
  }

  async function handleGenerate() {
    if (!post) return;
    setIsGenerating(true);
    try {
      const updated = await blog.generate(project.id, post.id, currentContent || undefined);
      setContent(updated.content);
      setIsDirty(false);
      await mutate();
      await mutateVersions();
      toast.success("Content regenerated with AI");
    } catch (err) {
      toast.error("Generation failed", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setIsGenerating(false);
    }
  }

  async function handleDelete() {
    if (!post) return;
    if (!confirm("Delete this blog post? This cannot be undone.")) return;
    setIsDeleting(true);
    try {
      await blog.delete(project.id, post.id);
      toast.success("Post deleted");
      router.push(`/projects/${project.id}/blog`);
    } catch (err) {
      toast.error("Failed to delete", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
      setIsDeleting(false);
    }
  }

  function handleSelectVersion(version: BlogPostVersion) {
    setTitle(version.title);
    setContent(version.content);
    setIsDirty(true);
    toast.info(`Loaded version ${version.version}`, {
      description: "Save to make this the current version.",
    });
  }

  async function handleTagsChange(newTags: string[]) {
    if (!post) return;
    try {
      await blog.update(project.id, post.id, { tags: newTags });
      await mutate();
    } catch (err) {
      toast.error("Failed to update tags", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    }
  }

  if (isLoading) {
    return (
      <div className="flex flex-col h-full">
        <div className="h-12 border-b border-border bg-card animate-pulse" />
        <div className="h-10 border-b border-border bg-secondary/10 animate-pulse" />
        <div className="flex-1 p-8 animate-pulse space-y-4">
          <div className="h-5 w-3/4 bg-secondary rounded" />
          <div className="h-4 w-full bg-secondary/60 rounded" />
          <div className="h-4 w-5/6 bg-secondary/60 rounded" />
          <div className="h-4 w-4/6 bg-secondary/60 rounded" />
        </div>
      </div>
    );
  }

  if (error || !post) {
    return (
      <div className="p-8">
        <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <AlertCircle className="w-4 h-4 shrink-0" />
          {error ? `Failed to load post: ${error.message}` : "Post not found"}
        </div>
      </div>
    );
  }

  const wordCount = currentContent.trim()
    ? currentContent.trim().split(/\s+/).length
    : 0;

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center gap-3 px-6 py-3 border-b border-border bg-card shrink-0 flex-wrap">
        <Link href={`/projects/${project.id}/blog`}>
          <Button variant="ghost" size="sm" className="gap-1.5 text-muted-foreground h-8">
            <ArrowLeft className="w-3.5 h-3.5" />
            Blog
          </Button>
        </Link>

        <span className="text-muted-foreground text-sm hidden sm:block">/</span>

        {/* Title input inline */}
        <Input
          value={currentTitle}
          onChange={(e) => handleTitleChange(e.target.value)}
          className="flex-1 min-w-0 bg-transparent border-0 focus-visible:ring-0 font-semibold text-sm px-0 h-8"
          placeholder="Post title..."
        />

        {/* Status badge + toggle */}
        <button type="button" onClick={handleToggleStatus}>
          <Badge
            variant="outline"
            className={cn(
              "text-xs capitalize cursor-pointer transition-colors",
              post.status === "published"
                ? "bg-green-600/20 text-green-400 border-green-600/30 hover:bg-green-600/30"
                : "bg-yellow-600/20 text-yellow-400 border-yellow-600/30 hover:bg-yellow-600/30",
            )}
          >
            {post.status === "published" ? (
              <Globe className="w-2.5 h-2.5 mr-1" />
            ) : (
              <FileText className="w-2.5 h-2.5 mr-1" />
            )}
            {post.status}
          </Badge>
        </button>

        <span className="text-xs text-muted-foreground tabular-nums hidden sm:block">
          {wordCount} words
        </span>

        {isDirty && (
          <span className="text-xs text-amber-400">Unsaved changes</span>
        )}

        <div className="flex items-center gap-1 ml-auto">
          <Button
            variant="ghost"
            size="sm"
            className="h-8 gap-1.5"
            onClick={() => setShowVersions((v) => !v)}
          >
            <History className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">History</span>
          </Button>

          <Button
            variant="outline"
            size="sm"
            className="h-8 gap-1.5"
            onClick={handleGenerate}
            disabled={isGenerating || isSaving}
          >
            {isGenerating ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Sparkles className="w-3.5 h-3.5" />
            )}
            <span className="hidden sm:inline">
              {isGenerating ? "Generating..." : "Generate"}
            </span>
          </Button>

          <Button
            size="sm"
            className="h-8 gap-1.5"
            onClick={handleSave}
            disabled={isSaving || isGenerating || !isDirty}
          >
            {isSaving ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Save className="w-3.5 h-3.5" />
            )}
            {isSaving ? "Saving..." : "Save"}
          </Button>

          <Button
            variant="ghost"
            size="sm"
            className="h-8 w-8 p-0 hover:text-destructive"
            onClick={handleDelete}
            disabled={isDeleting}
          >
            {isDeleting ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Trash2 className="w-3.5 h-3.5" />
            )}
          </Button>
        </div>
      </div>

      {/* Tags bar */}
      <div className="px-6 py-2 border-b border-border bg-secondary/10 shrink-0">
        <AngleTagInput
          tags={post.tags ?? []}
          onChange={handleTagsChange}
          placeholder="Add tag..."
        />
      </div>

      {/* Editor + optional version history */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        <BlogEditor
          content={currentContent}
          onChange={handleContentChange}
          className="flex-1 min-h-0"
        />

        {showVersions && (
          <BlogVersionHistory
            versions={versions ?? []}
            currentVersion={undefined}
            onSelectVersion={handleSelectVersion}
            onClose={() => setShowVersions(false)}
          />
        )}
      </div>
    </div>
  );
}
