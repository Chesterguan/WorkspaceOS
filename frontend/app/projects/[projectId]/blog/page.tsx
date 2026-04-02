"use client";

import { useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { BlogPostCard } from "@/components/blog/BlogPostCard";
import { useProjectContext } from "@/components/ProjectContext";
import { useBlogPosts } from "@/lib/hooks/useBlog";
import { Plus, NotebookPen } from "lucide-react";
import type { BlogPostStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

const STATUS_FILTERS: { value: BlogPostStatus | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "draft", label: "Draft" },
  { value: "published", label: "Published" },
];

export default function BlogListPage() {
  const { project } = useProjectContext();
  const [statusFilter, setStatusFilter] = useState<BlogPostStatus | "all">("all");
  const [tagFilter, setTagFilter] = useState<string>("");

  const { data: posts, error, isLoading } = useBlogPosts(project.id, {
    status: statusFilter === "all" ? undefined : statusFilter,
    tag: tagFilter || undefined,
  });

  // Collect all unique tags from posts for the tag filter pills
  const allTags = Array.from(
    new Set((posts ?? []).flatMap((p) => p.tags ?? [])),
  ).sort();

  return (
    <div className="p-8 space-y-6 max-w-6xl">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Blog Posts</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {posts?.length ?? 0} post{(posts?.length ?? 0) !== 1 ? "s" : ""}
          </p>
        </div>
        <Link href={`/projects/${project.id}/blog/new`}>
          <Button className="gap-2">
            <Plus className="w-4 h-4" />
            New Post
          </Button>
        </Link>
      </div>

      {/* Status tabs */}
      <div className="flex items-center gap-1 border-b border-border pb-0">
        {STATUS_FILTERS.map((s) => (
          <button
            key={s.value}
            type="button"
            onClick={() => setStatusFilter(s.value as BlogPostStatus | "all")}
            className={cn(
              "px-4 py-2 text-sm font-medium border-b-2 transition-all -mb-px",
              statusFilter === s.value
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {s.label}
          </button>
        ))}
      </div>

      {/* Tag filter pills */}
      {allTags.length > 0 && (
        <div className="flex items-center gap-2 flex-wrap">
          <button
            type="button"
            onClick={() => setTagFilter("")}
            className={cn(
              "px-3 py-1 rounded-full text-xs font-medium border transition-all",
              !tagFilter
                ? "bg-primary text-primary-foreground border-primary"
                : "border-border text-muted-foreground hover:border-primary/50 hover:text-foreground",
            )}
          >
            All tags
          </button>
          {allTags.map((tag) => (
            <button
              key={tag}
              type="button"
              onClick={() => setTagFilter(tagFilter === tag ? "" : tag)}
              className={cn(
                "px-3 py-1 rounded-full text-xs font-medium border transition-all",
                tagFilter === tag
                  ? "bg-primary text-primary-foreground border-primary"
                  : "border-border text-muted-foreground hover:border-primary/50 hover:text-foreground",
              )}
            >
              {tag}
            </button>
          ))}
        </div>
      )}

      {/* Content */}
      {isLoading ? (
        <div className="animate-pulse space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-40 bg-secondary/40 rounded-lg" />
            ))}
          </div>
        </div>
      ) : error ? (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          Failed to load posts: {error.message}
        </div>
      ) : (posts?.length ?? 0) === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 gap-3">
          <div className="w-12 h-12 rounded-full bg-secondary flex items-center justify-center">
            <NotebookPen className="w-6 h-6 text-muted-foreground" />
          </div>
          <p className="text-sm text-muted-foreground">No blog posts yet.</p>
          <Link href={`/projects/${project.id}/blog/new`}>
            <Button variant="outline" size="sm" className="gap-1.5">
              <Plus className="w-3.5 h-3.5" />
              Write your first post
            </Button>
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {(posts ?? []).map((post) => (
            <BlogPostCard key={post.id} post={post} projectId={project.id} />
          ))}
        </div>
      )}
    </div>
  );
}
