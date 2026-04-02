"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { GitHubRepoSelector } from "@/components/GitHubRepoSelector";
import { projects } from "@/lib/api";
import { slugify } from "@/lib/utils";
import { toast } from "sonner";
import { ArrowLeft, Loader2, GitFork, PenLine } from "lucide-react";
import { cn } from "@/lib/utils";

type Tab = "github" | "manual";

export default function NewProjectPage() {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<Tab>("github");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [form, setForm] = useState({
    name: "",
    slug: "",
    description: "",
    github_repo: "",
    github_branch: "main",
  });
  const [slugManuallyEdited, setSlugManuallyEdited] = useState(false);

  // Auto-generate slug from name unless user has manually edited it
  useEffect(() => {
    if (!slugManuallyEdited) {
      setForm((f) => ({ ...f, slug: slugify(f.name) }));
    }
  }, [form.name, slugManuallyEdited]);

  function handleChange(
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>,
  ) {
    const { name, value } = e.target;
    if (name === "slug") {
      setSlugManuallyEdited(true);
      setForm((f) => ({ ...f, slug: slugify(value) }));
    } else {
      setForm((f) => ({ ...f, [name]: value }));
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.name.trim()) {
      toast.error("Project name is required");
      return;
    }
    if (!form.slug.trim()) {
      toast.error("Slug is required");
      return;
    }

    setIsSubmitting(true);
    try {
      const project = await projects.create({
        name: form.name.trim(),
        slug: form.slug.trim(),
        description: form.description.trim() || undefined,
        github_repo: form.github_repo.trim() || undefined,
        github_branch: form.github_branch.trim() || "main",
      });
      toast.success("Project created!");
      router.push(`/projects/${project.id}/overview`);
    } catch (err) {
      toast.error("Failed to create project", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border px-8 py-4">
        <div className="max-w-2xl mx-auto flex items-center gap-3">
          <Link href="/projects">
            <Button variant="ghost" size="sm" className="gap-1.5 text-muted-foreground">
              <ArrowLeft className="w-4 h-4" />
              Projects
            </Button>
          </Link>
          <span className="text-muted-foreground">/</span>
          <span className="text-sm font-medium">New Project</span>
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-8 py-10">
        <div className="mb-8">
          <h1 className="text-2xl font-semibold">Create a new project</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Import from GitHub or set up manually to start generating PR content.
          </p>
        </div>

        {/* Tab bar */}
        <div className="flex rounded-lg border border-border overflow-hidden mb-6">
          <button
            type="button"
            onClick={() => setActiveTab("github")}
            className={cn(
              "flex-1 flex items-center justify-center gap-2 py-2.5 text-sm font-medium transition-colors",
              activeTab === "github"
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:text-foreground hover:bg-secondary/40",
            )}
          >
            <GitFork className="w-4 h-4" />
            Import from GitHub
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("manual")}
            className={cn(
              "flex-1 flex items-center justify-center gap-2 py-2.5 text-sm font-medium transition-colors",
              activeTab === "manual"
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:text-foreground hover:bg-secondary/40",
            )}
          >
            <PenLine className="w-4 h-4" />
            Manual
          </button>
        </div>

        {/* GitHub import tab */}
        {activeTab === "github" && (
          <Card className="bg-card border-border">
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <GitFork className="w-4 h-4" />
                Select repositories to import
              </CardTitle>
            </CardHeader>
            <CardContent>
              <GitHubRepoSelector />
            </CardContent>
          </Card>
        )}

        {/* Manual creation tab */}
        {activeTab === "manual" && (
          <Card className="bg-card border-border">
            <CardHeader>
              <CardTitle className="text-base">Project details</CardTitle>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit} className="space-y-5">
                <div className="space-y-2">
                  <Label htmlFor="name">
                    Project name <span className="text-destructive">*</span>
                  </Label>
                  <Input
                    id="name"
                    name="name"
                    value={form.name}
                    onChange={handleChange}
                    placeholder="My Awesome Project"
                    className="bg-secondary/40"
                    required
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="slug">
                    Slug <span className="text-destructive">*</span>
                  </Label>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-muted-foreground shrink-0">
                      projects/
                    </span>
                    <Input
                      id="slug"
                      name="slug"
                      value={form.slug}
                      onChange={handleChange}
                      placeholder="my-awesome-project"
                      className="bg-secondary/40 font-mono text-sm"
                      required
                    />
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Auto-generated from name. Only lowercase letters, numbers, and hyphens.
                  </p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="description">Description</Label>
                  <Textarea
                    id="description"
                    name="description"
                    value={form.description}
                    onChange={handleChange}
                    placeholder="What does this project do? Who is it for?"
                    className="bg-secondary/40 resize-none"
                    rows={3}
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="github_repo">GitHub repo</Label>
                    <Input
                      id="github_repo"
                      name="github_repo"
                      value={form.github_repo}
                      onChange={handleChange}
                      placeholder="owner/repo"
                      className="bg-secondary/40 font-mono text-sm"
                    />
                    <p className="text-xs text-muted-foreground">
                      Format: owner/repository
                    </p>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="github_branch">Branch</Label>
                    <Input
                      id="github_branch"
                      name="github_branch"
                      value={form.github_branch}
                      onChange={handleChange}
                      placeholder="main"
                      className="bg-secondary/40 font-mono text-sm"
                    />
                  </div>
                </div>

                <div className="flex gap-3 pt-2">
                  <Button type="submit" disabled={isSubmitting} className="gap-2">
                    {isSubmitting && <Loader2 className="w-4 h-4 animate-spin" />}
                    {isSubmitting ? "Creating..." : "Create project"}
                  </Button>
                  <Link href="/projects">
                    <Button type="button" variant="ghost">
                      Cancel
                    </Button>
                  </Link>
                </div>
              </form>
            </CardContent>
          </Card>
        )}
      </main>
    </div>
  );
}
