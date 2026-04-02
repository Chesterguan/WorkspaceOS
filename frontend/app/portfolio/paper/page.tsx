"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import Link from "next/link";
import { useProjects } from "@/lib/hooks/useProjects";
import { portfolio, posting } from "@/lib/api";
import { PublishButton } from "@/components/publish/PublishButton";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ReviewTimeline } from "@/components/research/ReviewTimeline";
import { PaperDiffView } from "@/components/research/PaperDiffView";
import {
  ArrowLeft,
  Loader2,
  Sparkles,
  Copy,
  Download,
  FileCode2,
  BookMarked,
  BookText,
  GitCompareArrows,
  Timer,
  FlaskConical,
  AlertCircle,
  Check,
  GitBranch,
  LayoutGrid,
  X,
} from "lucide-react";
import type {
  PaperGenerateResponse,
  PaperVersionInfo,
  PortfolioPaperGenerateRequest,
} from "@/lib/types";

// ─── Types ────────────────────────────────────────────────────────────────────

type PaperType = PortfolioPaperGenerateRequest["paper_type"];
type ContentTab = "paper" | "bibtex" | "latex";

const PAPER_TYPE_LABELS: Record<PaperType, string> = {
  conference: "Conference Paper",
  journal: "Journal Article",
  technical_report: "Technical Report",
  white_paper: "White Paper",
};

// ─── Lightweight markdown renderer ────────────────────────────────────────────
// Identical to the one in the single-project paper page so rendering is consistent.

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function paperMarkdownToHtml(text: string): string {
  return escapeHtml(text)
    .replace(/^#### (.+)$/gm, '<h4 class="text-sm font-semibold mt-5 mb-1 text-foreground">$1</h4>')
    .replace(/^### (.+)$/gm, '<h3 class="text-base font-semibold mt-6 mb-2 text-foreground">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 class="text-lg font-bold mt-7 mb-2 text-foreground">$1</h2>')
    .replace(/^# (.+)$/gm, '<h1 class="text-xl font-bold mt-8 mb-3 text-foreground">$1</h1>')
    .replace(/```[\w]*\n?([\s\S]*?)```/g, '<pre class="bg-secondary/40 border border-border rounded p-3 my-3 overflow-x-auto text-xs font-mono"><code>$1</code></pre>')
    .replace(/`([^`]+)`/g, '<code class="bg-secondary/60 px-1 py-0.5 rounded text-xs font-mono">$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>")
    .replace(
      /\[(\d[\d,\s–\-]*)\]/g,
      '<sup class="inline-flex items-baseline"><span class="inline-block px-1 py-0.5 rounded text-[10px] font-semibold bg-violet-500/15 text-violet-400 border border-violet-500/30 leading-none mx-0.5">[$1]</span></sup>',
    )
    .replace(/^[-*] (.+)$/gm, '<li class="ml-4 list-disc text-sm leading-relaxed">$1</li>')
    .replace(/\n{2,}/g, "</p><p>")
    .replace(/\n/g, "<br />");
}

// ─── Elapsed timer hook ────────────────────────────────────────────────────────

function useElapsedTimer(running: boolean): string {
  const [elapsed, setElapsed] = useState(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (running) {
      setElapsed(0);
      intervalRef.current = setInterval(() => setElapsed((s) => s + 1), 1000);
    } else {
      if (intervalRef.current) clearInterval(intervalRef.current);
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [running]);

  const mm = String(Math.floor(elapsed / 60)).padStart(2, "0");
  const ss = String(elapsed % 60).padStart(2, "0");
  return `${mm}:${ss}`;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function copyToClipboard(text: string, label: string) {
  navigator.clipboard
    .writeText(text)
    .then(() => toast.success(`${label} copied to clipboard`))
    .catch(() => toast.error("Failed to copy"));
}

function downloadFile(content: string, filename: string, mimeType = "text/plain") {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function PortfolioPaperPage() {
  const { data: projectList, isLoading: projectsLoading } = useProjects();

  // ── Project selector state ──────────────────────────────────────────────────
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  // ── Form state ──────────────────────────────────────────────────────────────
  const [title, setTitle] = useState("");
  const [paperType, setPaperType] = useState<PaperType>("technical_report");
  const [targetVenue, setTargetVenue] = useState("");
  const [additionalInstructions, setAdditionalInstructions] = useState("");

  // ── Generation state ────────────────────────────────────────────────────────
  const [isGenerating, setIsGenerating] = useState(false);
  const [result, setResult] = useState<PaperGenerateResponse | null>(null);
  const [genError, setGenError] = useState<string | null>(null);

  // Simulated active-pass index during generation
  const [activePassIndex, setActivePassIndex] = useState<number | null>(null);
  const passTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── View state ──────────────────────────────────────────────────────────────
  const [contentTab, setContentTab] = useState<ContentTab>("paper");
  const [selectedVersion, setSelectedVersion] = useState<number>(1);
  const [showDiff, setShowDiff] = useState(false);

  const elapsedLabel = useElapsedTimer(isGenerating);

  const myProjects = (projectList ?? []).filter((p) => p.status !== "demo");
  const canGenerate = selectedIds.size >= 2 && selectedIds.size <= 5 && title.trim().length >= 3;

  // ── Project selection ─────────────────────────────────────────────────────
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

  // ── Derive displayed content ──────────────────────────────────────────────
  const currentVersionContent = useCallback((): string => {
    if (!result) return "";
    if (selectedVersion === result.versions.length) {
      return result.final_content;
    }
    const v = result.versions.find((v) => v.version === selectedVersion);
    return v ? `[Version ${v.version} — ${v.changes_made}]\n\n${result.final_content}` : result.final_content;
  }, [result, selectedVersion]);

  const previousVersionContent = useCallback((): string => {
    if (!result || selectedVersion <= 1) return "";
    const prev = result.versions.find((v) => v.version === selectedVersion - 1);
    return prev ? `[Version ${prev.version} — ${prev.changes_made}]\n\n${result.final_content}` : result.final_content;
  }, [result, selectedVersion]);

  // ── Simulate pass progression ──────────────────────────────────────────────
  function startPassSimulation() {
    let idx = 0;
    setActivePassIndex(0);
    passTimerRef.current = setInterval(() => {
      idx++;
      if (idx < 5) {
        setActivePassIndex(idx);
      } else {
        if (passTimerRef.current) clearInterval(passTimerRef.current);
      }
    }, 12_000);
  }

  function stopPassSimulation() {
    if (passTimerRef.current) clearInterval(passTimerRef.current);
    setActivePassIndex(null);
  }

  // ── Generate handler ──────────────────────────────────────────────────────
  async function handleGenerate() {
    if (selectedIds.size < 2) {
      toast.error("Select at least 2 projects", {
        description: "A portfolio paper requires 2 to 5 projects.",
      });
      return;
    }
    if (!title.trim()) {
      toast.error("Please enter a paper title");
      return;
    }

    setIsGenerating(true);
    setGenError(null);
    setResult(null);
    setContentTab("paper");
    startPassSimulation();

    try {
      const res = await portfolio.generatePaper({
        project_ids: Array.from(selectedIds),
        title: title.trim(),
        paper_type: paperType,
        target_venue: targetVenue.trim() || undefined,
        additional_instructions: additionalInstructions.trim() || undefined,
      });

      stopPassSimulation();
      setResult(res);
      setSelectedVersion(res.versions.length || 1);
      toast.success("Portfolio paper generated successfully");
    } catch (err) {
      stopPassSimulation();
      const msg = err instanceof Error ? err.message : "Generation failed";
      setGenError(msg);
      toast.error("Paper generation failed", { description: msg });
    } finally {
      setIsGenerating(false);
    }
  }

  // ── Version / diff handlers ────────────────────────────────────────────────
  function handleSelectVersion(version: number) {
    setSelectedVersion(version);
    setShowDiff(false);
  }

  function handleCompareWithPrevious(version: number) {
    setSelectedVersion(version);
    setShowDiff(true);
  }

  // ── Export handlers ───────────────────────────────────────────────────────
  function handleCopyMarkdown() {
    if (!result) return;
    copyToClipboard(result.final_content, "Markdown");
  }

  function handleCopyLatex() {
    if (!result?.latex) return;
    copyToClipboard(result.latex, "LaTeX");
  }

  function handleCopyBibtex() {
    if (!result) return;
    copyToClipboard(result.bibtex, "BibTeX");
  }

  function handleDownloadTex() {
    if (!result?.latex) return;
    const safeName = title.toLowerCase().replace(/\s+/g, "_").replace(/[^\w]/g, "").slice(0, 40) || "portfolio_paper";
    downloadFile(result.latex, `${safeName}.tex`, "application/x-latex");
  }

  function handleDownloadBib() {
    if (!result) return;
    const safeName = title.toLowerCase().replace(/\s+/g, "_").replace(/[^\w]/g, "").slice(0, 40) || "portfolio_paper";
    downloadFile(result.bibtex, `${safeName}.bib`, "text/plain");
  }

  // ── Cleanup ───────────────────────────────────────────────────────────────
  useEffect(() => {
    return () => stopPassSimulation();
  }, []);

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col h-screen bg-background">
      {/* ── Toolbar ──────────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-3 px-6 py-3 border-b border-border bg-card shrink-0 flex-wrap">
        <Link href="/portfolio">
          <Button variant="ghost" size="sm" className="gap-1.5 text-muted-foreground h-8">
            <ArrowLeft className="w-3.5 h-3.5" />
            Portfolio
          </Button>
        </Link>

        <span className="text-muted-foreground text-sm hidden sm:block">/</span>

        <div className="flex items-center gap-2">
          <LayoutGrid className="w-4 h-4 text-primary shrink-0" />
          <span className="text-sm font-semibold">Portfolio Paper</span>
          <div className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-violet-500/10 border border-violet-500/25 text-violet-500 dark:text-violet-400">
            <FlaskConical className="w-3 h-3" />
            <span className="text-[10px] font-semibold tracking-wide uppercase">5-Round Review</span>
          </div>
        </div>

        {result && (
          <div className="ml-auto flex items-center gap-1 flex-wrap">
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-xs gap-1.5 text-muted-foreground"
              onClick={handleCopyMarkdown}
            >
              <Copy className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Copy Markdown</span>
            </Button>
            {result.latex && (
              <>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 text-xs gap-1.5 text-muted-foreground"
                  onClick={handleCopyLatex}
                >
                  <Copy className="w-3.5 h-3.5" />
                  <span className="hidden sm:inline">Copy LaTeX</span>
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 text-xs gap-1.5 text-muted-foreground"
                  onClick={handleDownloadTex}
                >
                  <Download className="w-3.5 h-3.5" />
                  <span className="hidden sm:inline">.tex</span>
                </Button>
              </>
            )}
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-xs gap-1.5 text-muted-foreground"
              onClick={handleCopyBibtex}
            >
              <Copy className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Copy BibTeX</span>
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-xs gap-1.5 text-muted-foreground"
              onClick={handleDownloadBib}
            >
              <Download className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">.bib</span>
            </Button>
          </div>
        )}
      </div>

      {/* ── Main two-panel layout ─────────────────────────────────────────────── */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* ── Left panel (60%) ─────────────────────────────────────────────────── */}
        <div className="flex flex-col w-[60%] min-w-0 border-r border-border">
          {/* Content tabs — only shown after generation */}
          {result && (
            <div className="flex items-center gap-0.5 px-4 pt-3 pb-0 shrink-0">
              {(
                [
                  { id: "paper", label: "Paper", icon: BookText },
                  { id: "bibtex", label: "BibTeX", icon: BookMarked },
                  { id: "latex", label: "LaTeX", icon: FileCode2 },
                ] as { id: ContentTab; label: string; icon: React.ElementType }[]
              ).map(({ id, label, icon: Icon }) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => setContentTab(id)}
                  className={cn(
                    "flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-t-md border-b-2 transition-colors",
                    contentTab === id
                      ? "border-violet-500 text-violet-400 bg-violet-500/5"
                      : "border-transparent text-muted-foreground hover:text-foreground",
                  )}
                >
                  <Icon className="w-3.5 h-3.5" />
                  {label}
                </button>
              ))}

              {showDiff && (
                <div className="flex items-center gap-0.5 ml-1">
                  <button
                    type="button"
                    onClick={() => setShowDiff(false)}
                    className={cn(
                      "flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-tl-md border-b-2 transition-colors",
                      "border-orange-500 text-orange-400 bg-orange-500/5",
                    )}
                  >
                    <GitCompareArrows className="w-3.5 h-3.5" />
                    Diff v{selectedVersion - 1} → v{selectedVersion}
                  </button>
                  {/* Explicit close button so the diff view is easy to dismiss */}
                  <button
                    type="button"
                    onClick={() => setShowDiff(false)}
                    title="Close diff view"
                    className="flex items-center justify-center w-6 h-6 rounded hover:bg-orange-500/20 text-orange-400 transition-colors"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Content body */}
          <div className="flex-1 overflow-y-auto">
            {/* ── Form: before generation ── */}
            {!result && !isGenerating && (
              <div className="p-8 max-w-2xl mx-auto space-y-8">
                <div className="space-y-1">
                  <h2 className="text-lg font-bold">New Portfolio Paper</h2>
                  <p className="text-sm text-muted-foreground">
                    Generate a multi-project academic paper — survey, technical report, or
                    comparison paper — through the 5-round automated review pipeline.
                  </p>
                </div>

                {/* Project selector */}
                <section className="space-y-3">
                  <div className="flex items-center justify-between">
                    <h3 className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                      Select Projects <span className="text-destructive">*</span>
                    </h3>
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
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      {Array.from({ length: 4 }).map((_, i) => (
                        <div
                          key={i}
                          className="h-16 bg-secondary/40 animate-pulse rounded-lg"
                        />
                      ))}
                    </div>
                  )}

                  {!projectsLoading && myProjects.length === 0 && (
                    <div className="rounded-lg border border-border bg-secondary/20 px-4 py-6 text-center text-sm text-muted-foreground">
                      No projects yet.{" "}
                      <Link href="/projects/new" className="text-primary hover:underline">
                        Create one
                      </Link>{" "}
                      to get started.
                    </div>
                  )}

                  {!projectsLoading && myProjects.length > 0 && (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      {myProjects.map((project) => {
                        const isSelected = selectedIds.has(project.id);
                        return (
                          <button
                            key={project.id}
                            type="button"
                            onClick={() => toggleProject(project.id)}
                            className={cn(
                              "text-left rounded-lg border p-3 transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
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
                              <div className="flex items-center gap-1 mt-1.5">
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
                    <p className="text-xs text-amber-400">
                      Select at least one more project.
                    </p>
                  )}
                </section>

                {/* Paper title */}
                <div className="space-y-1.5">
                  <label className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                    Paper Title <span className="text-destructive">*</span>
                  </label>
                  <Input
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    placeholder="e.g. A Survey of Modern Developer Tooling: From Local IDE to AI-Augmented Workflows"
                    className="bg-secondary/30 focus-visible:ring-violet-500/50 focus-visible:border-violet-500/40"
                  />
                </div>

                {/* Paper type */}
                <div className="space-y-1.5">
                  <label className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                    Paper Type
                  </label>
                  <Select
                    value={paperType}
                    onValueChange={(v) => setPaperType(v as PaperType)}
                  >
                    <SelectTrigger className="bg-secondary/30 focus:ring-violet-500/50">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="conference">Conference Paper</SelectItem>
                      <SelectItem value="journal">Journal Article</SelectItem>
                      <SelectItem value="technical_report">Technical Report</SelectItem>
                      <SelectItem value="white_paper">White Paper</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {/* Target venue */}
                <div className="space-y-1.5">
                  <label className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                    Target Venue <span className="text-muted-foreground/50">(optional)</span>
                  </label>
                  <Input
                    value={targetVenue}
                    onChange={(e) => setTargetVenue(e.target.value)}
                    placeholder="e.g. NeurIPS 2025, IEEE Software, ACM SIGSOFT"
                    className="bg-secondary/30 focus-visible:ring-violet-500/50 focus-visible:border-violet-500/40"
                  />
                </div>

                {/* Additional instructions */}
                <div className="space-y-1.5">
                  <label className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                    Additional Instructions <span className="text-muted-foreground/50">(optional)</span>
                  </label>
                  <Textarea
                    value={additionalInstructions}
                    onChange={(e) => setAdditionalInstructions(e.target.value)}
                    placeholder="Shared themes to emphasise, methodology comparisons, writing style, related work to cite…"
                    rows={4}
                    className="resize-none bg-secondary/30 focus-visible:ring-violet-500/50 focus-visible:border-violet-500/40"
                  />
                </div>

                {/* Generate button */}
                <Button
                  size="lg"
                  className="w-full gap-2 bg-violet-600 hover:bg-violet-700 text-white"
                  onClick={handleGenerate}
                  disabled={!canGenerate}
                >
                  <Sparkles className="w-4 h-4" />
                  Generate Paper (5-round review)
                </Button>

                {/* Error */}
                {genError && (
                  <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                    <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                    <span>{genError}</span>
                  </div>
                )}
              </div>
            )}

            {/* ── Generating state ── */}
            {isGenerating && (
              <div className="flex flex-col items-center justify-center h-full gap-6 p-8">
                <div className="w-16 h-16 rounded-2xl bg-violet-500/10 border border-violet-500/20 flex items-center justify-center">
                  <Loader2 className="w-8 h-8 text-violet-400 animate-spin" />
                </div>
                <div className="text-center space-y-2">
                  <p className="font-semibold">Generating your portfolio paper…</p>
                  <p className="text-sm text-muted-foreground max-w-xs">
                    Assembling context from {selectedIds.size} projects, then running 5
                    automated review rounds. This typically takes 3–6 minutes.
                  </p>
                </div>
                <div className="flex items-center gap-2 px-4 py-2 rounded-full bg-secondary/50 border border-border">
                  <Timer className="w-4 h-4 text-violet-400" />
                  <span className="font-mono text-sm tabular-nums">{elapsedLabel}</span>
                </div>
              </div>
            )}

            {/* ── Generated paper content ── */}
            {result && !isGenerating && (
              <>
                {/* Paper tab */}
                {contentTab === "paper" && !showDiff && (
                  <div className="px-8 py-6">
                    <div className="mb-6 pb-5 border-b border-border space-y-2">
                      <h1 className="text-2xl font-bold leading-tight">{result.title}</h1>
                      <div className="flex items-center gap-2 flex-wrap">
                        <Badge variant="outline" className="bg-violet-500/10 border-violet-500/30 text-violet-400 text-xs">
                          {PAPER_TYPE_LABELS[paperType]}
                        </Badge>
                        <Badge variant="outline" className="bg-primary/5 border-primary/20 text-primary text-xs">
                          Portfolio
                        </Badge>
                        {targetVenue && (
                          <Badge variant="outline" className="text-xs">
                            {targetVenue}
                          </Badge>
                        )}
                        <span className="text-xs text-muted-foreground">
                          v{selectedVersion} of {result.versions.length}
                        </span>
                      </div>
                      {result.review_summary && (
                        <p className="text-xs text-muted-foreground italic border-l-2 border-violet-500/30 pl-3">
                          {result.review_summary}
                        </p>
                      )}
                    </div>
                    <div
                      className="prose-paper text-sm leading-8 text-foreground/90"
                      dangerouslySetInnerHTML={{
                        __html: `<p>${paperMarkdownToHtml(currentVersionContent())}</p>`,
                      }}
                    />
                  </div>
                )}

                {/* Diff tab */}
                {contentTab === "paper" && showDiff && result.versions.length > 1 && (
                  <PaperDiffView
                    oldText={previousVersionContent()}
                    newText={currentVersionContent()}
                    oldLabel={`v${selectedVersion - 1}`}
                    newLabel={`v${selectedVersion}`}
                    className="h-full"
                  />
                )}

                {/* BibTeX tab */}
                {contentTab === "bibtex" && (
                  <div className="p-6 h-full flex flex-col gap-3">
                    <div className="flex items-center justify-between shrink-0">
                      <p className="text-xs text-muted-foreground">
                        BibTeX references for all cited works in this paper.
                      </p>
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-7 text-xs gap-1.5"
                        onClick={handleCopyBibtex}
                      >
                        <Copy className="w-3 h-3" />
                        Copy
                      </Button>
                    </div>
                    <pre className="flex-1 overflow-auto bg-secondary/30 border border-border rounded-lg p-4 text-xs font-mono text-muted-foreground whitespace-pre-wrap break-all">
                      {result.bibtex || "No BibTeX available."}
                    </pre>
                  </div>
                )}

                {/* LaTeX tab */}
                {contentTab === "latex" && (
                  <div className="p-6 h-full flex flex-col gap-3">
                    <div className="flex items-center justify-between shrink-0">
                      <p className="text-xs text-muted-foreground">
                        Full LaTeX source including preamble, document body, and bibliography.
                      </p>
                      <div className="flex items-center gap-1">
                        {result.latex && (
                          <>
                            <Button
                              variant="outline"
                              size="sm"
                              className="h-7 text-xs gap-1.5"
                              onClick={handleCopyLatex}
                            >
                              <Copy className="w-3 h-3" />
                              Copy
                            </Button>
                            <Button
                              variant="outline"
                              size="sm"
                              className="h-7 text-xs gap-1.5"
                              onClick={handleDownloadTex}
                            >
                              <Download className="w-3 h-3" />
                              .tex
                            </Button>
                          </>
                        )}
                      </div>
                    </div>
                    <pre className="flex-1 overflow-auto bg-secondary/30 border border-border rounded-lg p-4 text-xs font-mono text-muted-foreground whitespace-pre-wrap break-all">
                      {result.latex ?? "LaTeX export was not returned by the server. Try re-generating or using the export endpoint."}
                    </pre>
                  </div>
                )}
              </>
            )}
          </div>
        </div>

        {/* ── Right panel (40%) ─────────────────────────────────────────────────── */}
        <div className="flex flex-col w-[40%] min-w-0 overflow-y-auto">
          <div className="p-5 space-y-5">
            {/* ── Review timeline ── */}
            <ReviewTimeline
              versions={result?.versions ?? []}
              totalPasses={5}
              activePassIndex={isGenerating ? activePassIndex : null}
              selectedVersion={selectedVersion}
              onSelectVersion={handleSelectVersion}
              onCompareWithPrevious={handleCompareWithPrevious}
            />

            {/* ── Version selector ── */}
            {result && result.versions.length > 0 && (
              <>
                <Separator />
                <div className="space-y-2">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">
                    Jump to Version
                  </p>
                  <Select
                    value={String(selectedVersion)}
                    onValueChange={(v) => handleSelectVersion(Number(v))}
                  >
                    <SelectTrigger className="bg-secondary/30 text-xs h-8 focus:ring-violet-500/50">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {result.versions.map((v) => (
                        <SelectItem key={v.version} value={String(v.version)}>
                          v{v.version} — {v.review_name}
                          {v.score !== null ? ` (${v.score}/10)` : ""}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>

                  {selectedVersion > 1 && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="w-full h-7 text-xs gap-1.5"
                      onClick={() => handleCompareWithPrevious(selectedVersion)}
                    >
                      <GitCompareArrows className="w-3.5 h-3.5" />
                      Compare v{selectedVersion - 1} → v{selectedVersion}
                    </Button>
                  )}
                </div>
              </>
            )}

            {/* ── Export actions ── */}
            {result && (
              <>
                <Separator />
                <div className="space-y-2">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">
                    Export
                  </p>
                  <div className="grid grid-cols-2 gap-1.5">
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-7 text-xs gap-1.5 justify-start"
                      onClick={handleCopyMarkdown}
                    >
                      <Copy className="w-3 h-3" />
                      Copy Markdown
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-7 text-xs gap-1.5 justify-start"
                      onClick={handleCopyBibtex}
                    >
                      <Copy className="w-3 h-3" />
                      Copy BibTeX
                    </Button>
                    {result.latex && (
                      <>
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-7 text-xs gap-1.5 justify-start"
                          onClick={handleCopyLatex}
                        >
                          <Copy className="w-3 h-3" />
                          Copy LaTeX
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-7 text-xs gap-1.5 justify-start"
                          onClick={handleDownloadTex}
                        >
                          <Download className="w-3 h-3" />
                          Download .tex
                        </Button>
                      </>
                    )}
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-7 text-xs gap-1.5 justify-start"
                      onClick={handleDownloadBib}
                    >
                      <Download className="w-3 h-3" />
                      Download .bib
                    </Button>
                  </div>
                </div>
              </>
            )}

            {/* ── Publish / Schedule / Mark Posted ── */}
            {result && !isGenerating && result.blog_post_id && (
              <div className="space-y-3">
                <Separator />
                <div>
                  <p className="text-xs text-muted-foreground mb-2">Share</p>
                  <PublishButton
                    projectId={Array.from(selectedIds)[0]}
                    draftId={result.blog_post_id}
                    platform="medium_outline"
                    content={result.final_content}
                    onPublished={() => toast.success("Shared!")}
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
                          draft_id: result.blog_post_id!,
                          platform: "medium_outline",
                          scheduled_for: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString(),
                          notes: `Portfolio paper: ${result.title}`,
                        });
                        toast.success("Scheduled for next week");
                      } catch {
                        toast.error("Failed to schedule");
                      }
                    }}
                  >
                    Schedule
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    className="flex-1 gap-1.5 text-xs"
                    onClick={async () => {
                      const url = prompt("Paste the URL where you published this paper:");
                      if (!url) return;
                      const firstId = Array.from(selectedIds)[0];
                      try {
                        await posting.createRecord(firstId, {
                          draft_id: result.blog_post_id!,
                          platform: "medium_outline",
                          posted_at: new Date().toISOString(),
                          post_url: url,
                          notes: `Portfolio paper: ${result.title}`,
                        });
                        toast.success("Marked as published");
                      } catch {
                        toast.error("Failed to record");
                      }
                    }}
                  >
                    Mark Published
                  </Button>
                </div>
              </div>
            )}

            {/* ── Empty state ── */}
            {!result && !isGenerating && (
              <div className="flex flex-col items-center justify-center gap-4 py-12 text-center">
                <div className="w-12 h-12 rounded-xl bg-violet-500/10 border border-violet-500/20 flex items-center justify-center">
                  <FlaskConical className="w-6 h-6 text-violet-400" />
                </div>
                <div className="space-y-1">
                  <p className="text-sm font-medium">Review pipeline</p>
                  <p className="text-xs text-muted-foreground max-w-[200px]">
                    Each of the 5 passes will appear here as the paper is generated.
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
