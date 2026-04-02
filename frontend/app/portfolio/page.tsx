"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useProjects } from "@/lib/hooks/useProjects";
import { portfolio, posting } from "@/lib/api";
import type { Platform, PortfolioGenerateResponse } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Card,
  CardContent,
  CardHeader,
} from "@/components/ui/card";
import {
  ArrowLeft,
  Sparkles,
  Loader2,
  Copy,
  Check,
  GitBranch,
  ExternalLink,
  LayoutGrid,
  Send,
  FlaskConical,
} from "lucide-react";
import { PublishButton } from "@/components/publish/PublishButton";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { PLATFORM_LABELS } from "@/components/PlatformBadge";

// Platforms supported for portfolio posts (excludes github_release)
const PORTFOLIO_PLATFORMS: Platform[] = [
  "linkedin",
  "twitter",
  "xiaohongshu",
  "medium_outline",
];

const THEME_SUGGESTIONS = [
  "Monthly Update",
  "Project Roundup",
  "What I'm Building",
  "Year in Review",
];

export default function PortfolioPage() {
  const router = useRouter();
  const { data: projectList, isLoading: projectsLoading } = useProjects();

  // Form state
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [platform, setPlatform] = useState<Platform>("linkedin");
  const [theme, setTheme] = useState("");
  const [additionalContext, setAdditionalContext] = useState("");

  // Generation state
  const [isGenerating, setIsGenerating] = useState(false);
  const [result, setResult] = useState<PortfolioGenerateResponse | null>(null);
  const [editableContent, setEditableContent] = useState("");
  const [copied, setCopied] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  const myProjects = (projectList ?? []).filter((p) => p.status !== "demo");

  function toggleProject(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        if (next.size >= 5) {
          toast.error("Maximum 5 projects", {
            description: "Deselect a project before adding another.",
          });
          return prev;
        }
        next.add(id);
      }
      return next;
    });
  }

  async function handleGenerate() {
    if (selectedIds.size < 2) {
      toast.error("Select at least 2 projects", {
        description: "A portfolio post requires 2 to 5 projects.",
      });
      return;
    }

    setIsGenerating(true);
    setResult(null);
    setEditableContent("");
    const startTime = Date.now();

    // Elapsed counter
    const timer = setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - startTime) / 1000));
    }, 1000);

    try {
      const data = await portfolio.generate({
        project_ids: Array.from(selectedIds),
        platform,
        theme: theme.trim() || undefined,
        additional_context: additionalContext.trim() || undefined,
      });
      setResult(data);
      setEditableContent(data.content);
      toast.success("Portfolio post generated!", {
        description: `Covering ${data.projects_included.join(", ")}`,
      });
    } catch (err) {
      toast.error("Generation failed", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      clearInterval(timer);
      setIsGenerating(false);
    }
  }

  async function handleCopy() {
    await navigator.clipboard.writeText(editableContent);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  const formatTime = (s: number) =>
    `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

  const canGenerate = selectedIds.size >= 2 && selectedIds.size <= 5;

  return (
    <div className="min-h-screen bg-background">
      {/* Top bar */}
      <header className="border-b border-border px-8 py-4">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link href="/projects">
              <Button variant="ghost" size="sm" className="gap-1.5 text-muted-foreground hover:text-foreground">
                <ArrowLeft className="w-4 h-4" />
                Projects
              </Button>
            </Link>
            <div className="h-4 w-px bg-border" />
            <div>
              <h1 className="text-lg font-semibold tracking-tight flex items-center gap-2">
                <LayoutGrid className="w-4 h-4 text-primary" />
                Portfolio Post
              </h1>
              <p className="text-xs text-muted-foreground mt-0.5">
                Generate a single post covering multiple projects
              </p>
            </div>
          </div>

          {/* Write Paper link */}
          <Link href="/portfolio/paper">
            <Button variant="outline" size="sm" className="gap-1.5 text-muted-foreground hover:text-foreground">
              <FlaskConical className="w-4 h-4 text-violet-400" />
              Write Paper
            </Button>
          </Link>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-8 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_420px] gap-8">
          {/* Left column: project selection + options */}
          <div className="space-y-6">
            {/* Project picker */}
            <section>
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-medium text-foreground">
                  Select Projects
                </h2>
                <span
                  className={cn(
                    "text-xs tabular-nums",
                    selectedIds.size === 0
                      ? "text-muted-foreground"
                      : selectedIds.size < 2
                      ? "text-amber-400"
                      : "text-primary",
                  )}
                >
                  {selectedIds.size}/5 selected
                </span>
              </div>

              {projectsLoading && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {Array.from({ length: 4 }).map((_, i) => (
                    <div
                      key={i}
                      className="h-20 bg-secondary/40 animate-pulse rounded-lg"
                    />
                  ))}
                </div>
              )}

              {!projectsLoading && myProjects.length === 0 && (
                <div className="rounded-lg border border-border bg-secondary/20 px-4 py-8 text-center text-sm text-muted-foreground">
                  No projects yet.{" "}
                  <Link href="/projects/new" className="text-primary hover:underline">
                    Create one
                  </Link>{" "}
                  to get started.
                </div>
              )}

              {!projectsLoading && myProjects.length > 0 && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {myProjects.map((project) => {
                    const isSelected = selectedIds.has(project.id);
                    return (
                      <button
                        key={project.id}
                        type="button"
                        onClick={() => toggleProject(project.id)}
                        className={cn(
                          "text-left rounded-lg border p-3.5 transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
                          isSelected
                            ? "border-primary bg-primary/8 ring-1 ring-primary/30"
                            : "border-border bg-card hover:border-primary/40 hover:bg-card/80",
                        )}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex-1 min-w-0">
                            <p className={cn("font-medium text-sm leading-tight", isSelected && "text-primary")}>
                              {project.name}
                            </p>
                            {project.description && (
                              <p className="text-xs text-muted-foreground line-clamp-1 mt-0.5">
                                {project.description}
                              </p>
                            )}
                          </div>
                          <div
                            className={cn(
                              "flex-shrink-0 w-4 h-4 rounded border mt-0.5 flex items-center justify-center transition-colors",
                              isSelected
                                ? "bg-primary border-primary"
                                : "border-border",
                            )}
                          >
                            {isSelected && (
                              <Check className="w-2.5 h-2.5 text-primary-foreground" />
                            )}
                          </div>
                        </div>
                        {project.github_repo && (
                          <div className="flex items-center gap-1 mt-2">
                            <GitBranch className="w-3 h-3 text-muted-foreground" />
                            <span className="text-[10px] text-muted-foreground font-mono truncate">
                              {project.github_repo}
                            </span>
                          </div>
                        )}
                      </button>
                    );
                  })}
                </div>
              )}

              {selectedIds.size === 1 && (
                <p className="text-xs text-amber-400 mt-2">
                  Select at least one more project.
                </p>
              )}
            </section>

            {/* Options */}
            <section className="space-y-4">
              <h2 className="text-sm font-medium text-foreground">Options</h2>

              <div className="space-y-2">
                <Label>Platform</Label>
                <Select
                  value={platform}
                  onValueChange={(v) => setPlatform(v as Platform)}
                >
                  <SelectTrigger className="bg-secondary/40">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {PORTFOLIO_PLATFORMS.map((p) => (
                      <SelectItem key={p} value={p}>
                        {PLATFORM_LABELS[p]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>
                  Theme{" "}
                  <span className="text-muted-foreground font-normal">
                    (optional)
                  </span>
                </Label>
                <div className="flex flex-wrap gap-1.5 mb-1.5">
                  {THEME_SUGGESTIONS.map((t) => (
                    <button
                      key={t}
                      type="button"
                      onClick={() => setTheme(theme === t ? "" : t)}
                      className={cn(
                        "text-xs px-2.5 py-1 rounded-full border transition-colors",
                        theme === t
                          ? "bg-primary/15 border-primary/50 text-primary"
                          : "border-border text-muted-foreground hover:text-foreground hover:border-border/80",
                      )}
                    >
                      {t}
                    </button>
                  ))}
                </div>
                <input
                  type="text"
                  value={theme}
                  onChange={(e) => setTheme(e.target.value)}
                  placeholder="Or type a custom theme..."
                  className="w-full bg-secondary/40 border border-input rounded-md px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                />
              </div>

              <div className="space-y-2">
                <Label>
                  Additional context{" "}
                  <span className="text-muted-foreground font-normal">
                    (optional)
                  </span>
                </Label>
                <Textarea
                  value={additionalContext}
                  onChange={(e) => setAdditionalContext(e.target.value)}
                  placeholder="Any specific angle, milestone, or context to emphasise across all projects..."
                  className="bg-secondary/40 resize-none"
                  rows={3}
                />
              </div>
            </section>
          </div>

          {/* Right column: generate button + output */}
          <div className="space-y-4">
            {/* Generate button */}
            <Card className="border-border">
              <CardContent className="pt-5 space-y-3">
                <div className="space-y-1">
                  <p className="text-sm font-medium">Ready to generate</p>
                  <p className="text-xs text-muted-foreground">
                    {selectedIds.size < 2
                      ? "Select 2–5 projects to continue."
                      : `${selectedIds.size} projects selected for ${PLATFORM_LABELS[platform]}`}
                  </p>
                </div>

                {isGenerating && (
                  <div className="flex items-center gap-2 rounded-md border border-border bg-secondary/30 px-3 py-2">
                    <Loader2 className="w-3.5 h-3.5 animate-spin text-primary shrink-0" />
                    <span className="text-xs text-foreground/80 flex-1">
                      Building portfolio post...
                    </span>
                    <span className="text-xs text-muted-foreground font-mono">
                      {formatTime(elapsedSeconds)}
                    </span>
                  </div>
                )}

                <Button
                  className="w-full gap-2"
                  onClick={handleGenerate}
                  disabled={isGenerating || !canGenerate}
                >
                  {isGenerating ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Sparkles className="w-4 h-4" />
                  )}
                  {isGenerating ? "Generating..." : "Generate Portfolio Post"}
                </Button>
              </CardContent>
            </Card>

            {/* Result */}
            {result && !isGenerating && (
              <Card className="border-border">
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <div className="space-y-0.5">
                      <p className="text-sm font-medium">Generated Post</p>
                      <div className="flex flex-wrap gap-1">
                        {result.projects_included.map((name) => (
                          <Badge
                            key={name}
                            variant="outline"
                            className="text-[10px] px-1.5 py-0 bg-primary/5 border-primary/20 text-primary"
                          >
                            {name}
                          </Badge>
                        ))}
                      </div>
                    </div>
                    <Badge variant="outline" className="text-xs shrink-0">
                      {PLATFORM_LABELS[result.platform]}
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent className="space-y-3 pt-0">
                  <Textarea
                    value={editableContent}
                    onChange={(e) => setEditableContent(e.target.value)}
                    className="bg-secondary/30 resize-none font-mono text-xs leading-relaxed min-h-[280px]"
                    rows={14}
                  />

                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      className="flex-1 gap-1.5"
                      onClick={handleCopy}
                    >
                      {copied ? (
                        <>
                          <Check className="w-3.5 h-3.5 text-green-500" />
                          Copied
                        </>
                      ) : (
                        <>
                          <Copy className="w-3.5 h-3.5" />
                          Copy
                        </>
                      )}
                    </Button>

                    {result.draft_id && (
                      <Button
                        variant="outline"
                        size="sm"
                        className="flex-1 gap-1.5"
                        onClick={() => {
                          // Navigate to the draft under the first project
                          const firstId = Array.from(selectedIds)[0];
                          router.push(`/projects/${firstId}/drafts/${result.draft_id}`);
                        }}
                      >
                        <ExternalLink className="w-3.5 h-3.5" />
                        Open Draft
                      </Button>
                    )}
                  </div>

                  {/* Publish + Schedule + Mark Posted — same as single project drafts */}
                  {result.draft_id && (
                    <div className="pt-2 border-t border-border space-y-3">
                      <div>
                        <p className="text-xs text-muted-foreground mb-2">Publish</p>
                        <PublishButton
                          projectId={Array.from(selectedIds)[0]}
                          draftId={result.draft_id}
                          platform={result.platform as Platform}
                          content={editableContent}
                          onPublished={() => {
                            toast.success("Published!");
                          }}
                        />
                      </div>

                      <div className="flex gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          className="flex-1 gap-1.5 text-xs"
                          onClick={async () => {
                            const firstId = Array.from(selectedIds)[0];
                            try {
                              await posting.createSchedule(firstId, {
                                draft_id: result.draft_id!,
                                platform: result.platform,
                                scheduled_for: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(),
                                notes: `Portfolio post: ${result.projects_included.join(", ")}`,
                              });
                              toast.success("Scheduled for tomorrow");
                            } catch (e) {
                              toast.error("Failed to schedule");
                            }
                          }}
                        >
                          Schedule for Tomorrow
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          className="flex-1 gap-1.5 text-xs"
                          onClick={async () => {
                            const url = prompt("Paste the URL where you posted this:");
                            if (!url) return;
                            const firstId = Array.from(selectedIds)[0];
                            try {
                              await posting.createRecord(firstId, {
                                draft_id: result.draft_id!,
                                platform: result.platform,
                                posted_at: new Date().toISOString(),
                                post_url: url,
                                notes: `Portfolio post: ${result.projects_included.join(", ")}`,
                              });
                              toast.success("Marked as posted");
                            } catch (e) {
                              toast.error("Failed to record post");
                            }
                          }}
                        >
                          Mark as Posted
                        </Button>
                      </div>
                    </div>
                  )}

                  <p className="text-[10px] text-muted-foreground">
                    Draft saved under your first selected project. Edit it further
                    in the Drafts section, or publish directly above.
                  </p>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
