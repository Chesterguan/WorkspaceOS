"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { AngleTagInput } from "@/components/AngleTagInput";
import { useProjectContext } from "@/components/ProjectContext";
import { blog } from "@/lib/api";
import { toast } from "sonner";
import { ArrowLeft, Loader2, Sparkles, Save } from "lucide-react";
import type { BlogPostStatus } from "@/lib/types";

export default function NewBlogPostPage() {
  const router = useRouter();
  const { project } = useProjectContext();

  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [status, setStatus] = useState<BlogPostStatus>("draft");
  const [isSaving, setIsSaving] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) {
      toast.error("Title is required");
      return;
    }

    setIsSaving(true);
    try {
      const post = await blog.create(project.id, {
        title: title.trim(),
        content: content.trim(),
        tags,
        status,
      });
      toast.success("Post created!");
      router.push(`/projects/${project.id}/blog/${post.id}`);
    } catch (err) {
      toast.error("Failed to create post", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setIsSaving(false);
    }
  }

  async function handleGenerateWithAI() {
    if (!title.trim()) {
      toast.error("Enter a title first so AI knows what to write about");
      return;
    }

    setIsGenerating(true);
    try {
      // Create the post first, then generate content for it
      const post = await blog.create(project.id, {
        title: title.trim(),
        content: content || `# ${title.trim()}\n\n`,
        tags,
        status: "draft",
      });

      const generated = await blog.generate(
        project.id,
        post.id,
        content || undefined,
      );

      toast.success("Content generated!", {
        description: "Your blog post has been drafted by AI.",
      });
      router.push(`/projects/${project.id}/blog/${generated.id}`);
    } catch (err) {
      toast.error("Generation failed", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setIsGenerating(false);
    }
  }

  const wordCount = content.trim() ? content.trim().split(/\s+/).length : 0;

  return (
    <div className="p-8 space-y-6 max-w-3xl">
      <div className="flex items-center gap-3">
        <Link href={`/projects/${project.id}/blog`}>
          <Button variant="ghost" size="sm" className="gap-1.5 text-muted-foreground">
            <ArrowLeft className="w-4 h-4" />
            Blog
          </Button>
        </Link>
        <span className="text-muted-foreground">/</span>
        <span className="text-sm font-medium">New Post</span>
      </div>

      <form onSubmit={handleSave} className="space-y-5">
        <div className="space-y-2">
          <Label htmlFor="post-title">
            Title <span className="text-destructive">*</span>
          </Label>
          <Input
            id="post-title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="My blog post title"
            className="bg-secondary/40 text-lg font-semibold"
            required
          />
        </div>

        <div className="space-y-2">
          <Label>Tags</Label>
          <AngleTagInput
            tags={tags}
            onChange={setTags}
            placeholder="Add tags (press Enter)"
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="post-status">Status</Label>
          <Select
            value={status}
            onValueChange={(v) => setStatus(v as BlogPostStatus)}
          >
            <SelectTrigger className="bg-secondary/40 w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="draft">Draft</SelectItem>
              <SelectItem value="published">Published</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label htmlFor="post-content">Content (Markdown)</Label>
            <span className="text-xs text-muted-foreground tabular-nums">
              {wordCount} word{wordCount !== 1 ? "s" : ""}
            </span>
          </div>
          <Textarea
            id="post-content"
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder="# Introduction&#10;&#10;Start writing in Markdown..."
            className="bg-secondary/40 resize-none font-mono text-sm min-h-[300px]"
            rows={16}
          />
        </div>

        <div className="flex gap-3 pt-2">
          <Button type="submit" disabled={isSaving || isGenerating} className="gap-2">
            {isSaving ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Save className="w-4 h-4" />
            )}
            {isSaving ? "Saving..." : "Save Post"}
          </Button>

          <Button
            type="button"
            variant="outline"
            disabled={isSaving || isGenerating}
            onClick={handleGenerateWithAI}
            className="gap-2"
          >
            {isGenerating ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Sparkles className="w-4 h-4" />
            )}
            {isGenerating ? "Generating..." : "Generate with AI"}
          </Button>

          <Link href={`/projects/${project.id}/blog`}>
            <Button type="button" variant="ghost" disabled={isSaving || isGenerating}>
              Cancel
            </Button>
          </Link>
        </div>
      </form>
    </div>
  );
}
