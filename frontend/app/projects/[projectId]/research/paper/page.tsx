"use client";

import { use, useState, useEffect, useRef, useCallback } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { ReviewTimeline } from "@/components/research/ReviewTimeline";
import { PaperDiffView } from "@/components/research/PaperDiffView";
import { AgentLogPanel } from "@/components/research/AgentLogPanel";
import { RoundtableReviewPanel } from "@/components/research/RoundtableReviewPanel";
import { VisualContentDialogs } from "@/components/research/VisualContentDialogs";
import type { VisualDialogType } from "@/components/research/VisualContentDialogs";
import { useProjectContext } from "@/components/ProjectContext";
import { paper as paperApi, blogPublish } from "@/lib/api";
import { toast } from "sonner";
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
  X,
  Table2,
  BarChart3,
  ImagePlus,
  Check,
  Pencil,
  Eye,
  Target,
  Minimize2,
  Maximize2,
  Plus,
  ExternalLink,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { paperMarkdownToHtml } from "@/lib/markdown";
import { PAPER_TYPE_LABELS } from "@/lib/paper-utils";
import { useElapsedTimer } from "@/lib/hooks/useElapsedTimer";
import { usePassSimulation } from "@/lib/hooks/usePassSimulation";
import { usePaperExport } from "@/lib/hooks/usePaperExport";
import type {
  PaperGenerateRequest,
  PaperGenerateResponse,
  PaperGenerateV2Response,
  PaperEditRequest,
  PaperEditResponse,
  AgentLogEntry,
  VenueGuidelines,
  PaperVersionInfo,
  TitleSuggestion,
  ReviewerFeedback,
} from "@/lib/types";

// ─── Props ────────────────────────────────────────────────────────────────────

interface PaperPageProps {
  params: Promise<{ projectId: string }>;
}

// ─── Content tab types ────────────────────────────────────────────────────────

type ContentTab = "paper" | "bibtex" | "latex";

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function PaperPage({ params }: PaperPageProps) {
  // params is a Promise in Next.js 15+ — unwrap with use()
  const { projectId } = use(params);
  const { project } = useProjectContext();

  // ── Form state ──────────────────────────────────────────────────────────────
  const [title, setTitle] = useState("");
  const [paperType, setPaperType] = useState<PaperGenerateRequest["paper_type"]>("conference");
  const [targetVenue, setTargetVenue] = useState("");
  const [additionalInstructions, setAdditionalInstructions] = useState("");

  // ── Title suggestion state ───────────────────────────────────────────────────
  const [isSuggestingTitles, setIsSuggestingTitles] = useState(false);
  const [titleSuggestions, setTitleSuggestions] = useState<TitleSuggestion[]>([]);

  // ── Visual toolbar dialog state ──────────────────────────────────────────────
  const [activeVisualDialog, setActiveVisualDialog] = useState<VisualDialogType>(null);
  const [insertedVisuals, setInsertedVisuals] = useState<string[]>([]);

  // ── Edit mode state ─────────────────────────────────────────────────────────
  type ViewMode = "view" | "edit";
  const [viewMode, setViewMode] = useState<ViewMode>("view");
  const [editInstruction, setEditInstruction] = useState("");
  const [editTargetSection, setEditTargetSection] = useState<string | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [editResult, setEditResult] = useState<PaperEditResponse | null>(null);
  // V2 response extras
  const [agentLog, setAgentLog] = useState<AgentLogEntry[]>([]);
  const [venueGuidelines, setVenueGuidelines] = useState<VenueGuidelines | null>(null);
  const [roundtableReviews, setRoundtableReviews] = useState<ReviewerFeedback[]>([]);
  // Use v2 pipeline
  const [useV2, setUseV2] = useState(true);

  // ── Generation state ────────────────────────────────────────────────────────
  const [isGenerating, setIsGenerating] = useState(false);
  const [result, setResult] = useState<PaperGenerateResponse | null>(null);
  const [genError, setGenError] = useState<string | null>(null);

  const { activePassIndex, start: startPassSimulation, stop: stopPassSimulation } = usePassSimulation();

  // ── View state ──────────────────────────────────────────────────────────────
  const [contentTab, setContentTab] = useState<ContentTab>("paper");
  // Which version number is shown in the left panel (1-based, matches PaperVersionInfo.version)
  const [selectedVersion, setSelectedVersion] = useState<number>(1);
  // Diff mode: compare selectedVersion with its predecessor
  const [showDiff, setShowDiff] = useState(false);

  const elapsedLabel = useElapsedTimer(isGenerating);

  // Auto-suggest titles on page load
  const hasSuggestedRef = useRef(false);
  useEffect(() => {
    if (!hasSuggestedRef.current && projectId) {
      hasSuggestedRef.current = true;
      handleSuggestTitles();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  // ── Derive displayed content ─────────────────────────────────────────────────
  // If a specific version is selected and we have the versions list, show that
  // version's content. The final content lives in result.final_content.
  const currentVersionContent = useCallback((): string => {
    if (!result) return "";
    // Latest version = final content
    if (selectedVersion === result.versions.length) {
      return result.final_content;
    }
    const v = result.versions.find((v) => v.version === selectedVersion);
    // Use actual per-version content if available (from BlogPostVersion)
    if (v?.content) return v.content;
    // Fallback for old papers without per-version content
    return result.final_content;
  }, [result, selectedVersion]);

  // Content for the "previous" version (selectedVersion - 1) used in diff view
  const previousVersionContent = useCallback((): string => {
    if (!result || selectedVersion <= 1) return "";
    const prev = result.versions.find((v) => v.version === selectedVersion - 1);
    // Use actual per-version content if available
    if (prev?.content) return prev.content;
    // Fallback for old papers
    return result.final_content;
  }, [result, selectedVersion]);

  // ── Suggest titles handler ────────────────────────────────────────────────────
  async function handleSuggestTitles() {
    setIsSuggestingTitles(true);
    setTitleSuggestions([]);
    try {
      const res = await paperApi.suggestTitles(projectId, {
        paper_type: paperType,
        target_venue: targetVenue.trim() || undefined,
      });
      setTitleSuggestions(res.titles);
    } catch {
      toast.error("Failed to generate title suggestions");
    } finally {
      setIsSuggestingTitles(false);
    }
  }

  function handleSelectSuggestedTitle(suggestion: TitleSuggestion) {
    setTitle(suggestion.title);
    toast.success(`Title applied: ${suggestion.style} style`);
  }

  // ── Visual content handlers ───────────────────────────────────────────────────
  function openVisualDialog(type: "table" | "chart" | "figure") {
    setActiveVisualDialog(type);
  }

  function closeVisualDialog() {
    setActiveVisualDialog(null);
  }

  function handleInsertVisual(content: string) {
    setInsertedVisuals((prev) => [...prev, content]);
    setActiveVisualDialog(null);
  }

  // ── Generate handler ─────────────────────────────────────────────────────────
  async function handleGenerate() {
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
      const reqData = {
        title: title.trim(),
        paper_type: paperType,
        target_venue: targetVenue.trim() || undefined,
        additional_instructions: additionalInstructions.trim() || undefined,
      };
      const res = useV2
        ? await paperApi.generateV2(projectId, reqData)
        : await paperApi.generate(projectId, reqData);

      stopPassSimulation();
      setResult(res);
      // Capture v2 extras if available
      if ("agent_log" in res) {
        const v2Res = res as PaperGenerateV2Response;
        setAgentLog(v2Res.agent_log);
        setVenueGuidelines(v2Res.venue_guidelines);
      }
      if ("roundtable_reviews" in res) {
        const v2Res = res as PaperGenerateV2Response;
        setRoundtableReviews(v2Res.roundtable_reviews || []);
      }
      // Default to the latest version
      setSelectedVersion(res.versions.length || 1);
      toast.success("Paper generated successfully");
    } catch (err) {
      stopPassSimulation();
      const msg = err instanceof Error ? err.message : "Generation failed";
      setGenError(msg);
      toast.error("Paper generation failed", { description: msg });
    } finally {
      setIsGenerating(false);
    }
  }

  // ── Edit handler ──────────────────────────────────────────────────────────
  async function handleEditPaper(instruction: string, targetSection?: string | null) {
    if (!result || !instruction.trim()) return;
    setIsEditing(true);
    setEditResult(null);
    try {
      const res = await paperApi.editPaper(projectId, result.blog_post_id, {
        instruction: instruction.trim(),
        target_section: targetSection || undefined,
        target_venue: targetVenue.trim() || undefined,
      });
      setEditResult(res);
      setAgentLog(res.agent_log);
      // Update the main result's final_content with the edit
      setResult((prev) =>
        prev ? { ...prev, final_content: res.updated_content } : prev
      );
      toast.success(res.changes_summary);
    } catch {
      toast.error("Edit failed");
    } finally {
      setIsEditing(false);
      setEditInstruction("");
    }
  }

  // ── Version / diff helpers ────────────────────────────────────────────────
  function handleSelectVersion(version: number) {
    setSelectedVersion(version);
    setShowDiff(false);
  }

  function handleCompareWithPrevious(version: number) {
    setSelectedVersion(version);
    setShowDiff(true);
  }

  // ── Export handlers ──────────────────────────────────────────────────────
  const {
    handleCopyMarkdown,
    handleCopyLatex,
    handleCopyBibtex,
    handleDownloadTex,
    handleDownloadBib,
  } = usePaperExport(result, title);

  async function handleDownloadPdf() {
    if (!result) return;
    try {
      const res = await paperApi.exportPdf(projectId, {
        blog_post_id: result.blog_post_id,
        template: "arxiv",
      });
      const bytes = Uint8Array.from(atob(res.pdf_base64), (c) => c.charCodeAt(0));
      const blob = new Blob([bytes], { type: "application/pdf" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = res.filename;
      a.click();
      URL.revokeObjectURL(url);
      toast.success("PDF downloaded");
    } catch {
      toast.error("PDF export failed — pdflatex may not be available");
    }
  }

  // ── Publish handlers ─────────────────────────────────────────────────────────
  async function handlePublishDevto() {
    if (!result) return;
    try {
      const res = await blogPublish.devto(projectId, result.blog_post_id);
      if (res.success) {
        toast.success("Published to Dev.to", { description: res.post_url || "" });
      } else {
        toast.error("Dev.to publish failed", { description: res.error || "" });
      }
    } catch {
      toast.error("Dev.to publish failed");
    }
  }

  async function handlePublishHashnode() {
    if (!result) return;
    try {
      const res = await blogPublish.hashnode(projectId, result.blog_post_id);
      if (res.success) {
        toast.success("Published to Hashnode", { description: res.post_url || "" });
      } else {
        toast.error("Hashnode publish failed", { description: res.error || "" });
      }
    } catch {
      toast.error("Hashnode publish failed");
    }
  }

  // ── Cleanup on unmount ──────────────────────────────────────────────────────
  useEffect(() => {
    return () => stopPassSimulation();
  }, []);

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col h-full">
      {/* ── Toolbar ─────────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-3 px-6 py-3 border-b border-border bg-card shrink-0 flex-wrap">
        <Link href={`/projects/${project.id}/research`}>
          <Button variant="ghost" size="sm" className="gap-1.5 text-muted-foreground h-8">
            <ArrowLeft className="w-3.5 h-3.5" />
            Research
          </Button>
        </Link>

        <span className="text-muted-foreground text-sm hidden sm:block">/</span>

        <div className="flex items-center gap-2">
          <FlaskConical className="w-4 h-4 text-violet-400 shrink-0" />
          <span className="text-sm font-semibold">Paper Writer</span>
          <div className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-violet-500/10 border border-violet-500/25 text-violet-500 dark:text-violet-400">
            <FlaskConical className="w-3 h-3" />
            <span className="text-[10px] font-semibold tracking-wide uppercase">Adaptive Review</span>
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
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-xs gap-1.5 text-muted-foreground"
              onClick={handleDownloadPdf}
            >
              <Download className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">.pdf</span>
            </Button>
            <Separator orientation="vertical" className="h-4 mx-1" />
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-xs gap-1.5 text-muted-foreground"
              onClick={handlePublishDevto}
            >
              <ExternalLink className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Dev.to</span>
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-xs gap-1.5 text-muted-foreground"
              onClick={handlePublishHashnode}
            >
              <ExternalLink className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Hashnode</span>
            </Button>
          </div>
        )}
      </div>

      {/* ── Main two-panel layout ──────────────────────────────────────────── */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* ── Left panel (60%) ───────────────────────────────────────────────── */}
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
            {/* ── Form state: before generation ── */}
            {!result && !isGenerating && (
              <div className="p-8 max-w-2xl mx-auto space-y-6">
                <div className="space-y-1">
                  <h2 className="text-lg font-bold">New Academic Paper</h2>
                  <p className="text-sm text-muted-foreground">
                    Generate a full paper with adaptive review — 5 aspects scored independently,
                    each retried until 8+/10. Typically 5-12 rounds depending on quality.
                  </p>
                </div>

                {/* Title — auto-suggested on load, pick one or type your own */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                      Paper Title <span className="text-destructive">*</span>
                    </label>
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 h-6 px-2 text-[11px] rounded font-medium text-violet-400 hover:text-violet-300 hover:bg-violet-500/10 transition-colors disabled:opacity-50"
                      onClick={handleSuggestTitles}
                      disabled={isSuggestingTitles}
                    >
                      {isSuggestingTitles ? (
                        <Loader2 className="w-3 h-3 animate-spin" />
                      ) : (
                        <Sparkles className="w-3 h-3" />
                      )}
                      Regenerate
                    </button>
                  </div>

                  {/* Inline title suggestions */}
                  {isSuggestingTitles && titleSuggestions.length === 0 && (
                    <div className="rounded-lg border border-violet-500/20 bg-violet-500/5 p-4">
                      <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <Loader2 className="w-4 h-4 animate-spin text-violet-400" />
                        Generating title suggestions for {project.name}...
                      </div>
                    </div>
                  )}

                  {titleSuggestions.length > 0 && (
                    <div className="rounded-lg border border-violet-500/20 bg-violet-500/5 divide-y divide-violet-500/10">
                      <div className="px-3 py-2 flex items-center gap-2">
                        <Sparkles className="w-3.5 h-3.5 text-violet-400" />
                        <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">
                          Pick a title or type your own below
                        </span>
                      </div>
                      {titleSuggestions.map((suggestion, idx) => (
                        <button
                          key={idx}
                          type="button"
                          onClick={() => handleSelectSuggestedTitle(suggestion)}
                          className={cn(
                            "w-full text-left px-3 py-2.5 hover:bg-violet-500/10 transition-colors group",
                            title === suggestion.title && "bg-violet-500/10",
                          )}
                        >
                          <div className="flex items-start gap-2">
                            <div className="flex-1 space-y-0.5">
                              <p className={cn(
                                "text-sm font-medium leading-snug transition-colors",
                                title === suggestion.title
                                  ? "text-violet-300"
                                  : "text-foreground group-hover:text-violet-300",
                              )}>
                                {title === suggestion.title && (
                                  <Check className="w-3.5 h-3.5 inline mr-1.5 text-green-400" />
                                )}
                                {suggestion.title}
                              </p>
                              <p className="text-xs text-muted-foreground">
                                {suggestion.rationale}
                              </p>
                            </div>
                            <span className="shrink-0 mt-0.5 px-1.5 py-0.5 rounded text-[9px] font-semibold uppercase tracking-wide bg-violet-500/15 text-violet-400 border border-violet-500/25">
                              {suggestion.style}
                            </span>
                          </div>
                        </button>
                      ))}
                    </div>
                  )}

                  <Input
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    placeholder={titleSuggestions.length > 0 ? "Or type a custom title..." : "Generating suggestions..."}
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
                    onValueChange={(v) => setPaperType(v as PaperGenerateRequest["paper_type"])}
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
                    placeholder="e.g. NeurIPS 2025, IEEE Transactions on Knowledge and Data Engineering"
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
                    placeholder="Specific sections, methodology focus, writing style, related work to cite…"
                    rows={4}
                    className="resize-none bg-secondary/30 focus-visible:ring-violet-500/50 focus-visible:border-violet-500/40"
                  />
                </div>

                {/* V2 pipeline toggle */}
                <label className="flex items-center gap-2 text-sm text-muted-foreground cursor-pointer">
                  <input
                    type="checkbox"
                    checked={useV2}
                    onChange={(e) => setUseV2(e.target.checked)}
                    className="rounded border-border"
                  />
                  Use v2 multi-agent pipeline (section-by-section with backtracking)
                </label>

                {/* Generate button */}
                <Button
                  size="lg"
                  className="w-full gap-2 bg-violet-600 hover:bg-violet-700 text-white"
                  onClick={handleGenerate}
                  disabled={!title.trim()}
                >
                  <Sparkles className="w-4 h-4" />
                  Generate Paper (adaptive review)
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
                {/* Animated paper icon */}
                <div className="w-16 h-16 rounded-2xl bg-violet-500/10 border border-violet-500/20 flex items-center justify-center">
                  <Loader2 className="w-8 h-8 text-violet-400 animate-spin" />
                </div>

                <div className="text-center space-y-2">
                  <p className="font-semibold">Generating your paper…</p>
                  <p className="text-sm text-muted-foreground max-w-xs">
                    Running 5 automated review rounds to refine structure, arguments, and academic
                    rigour. This typically takes 2–4 minutes.
                  </p>
                </div>

                {/* Elapsed timer */}
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
                    {/* Paper header */}
                    <div className="mb-6 pb-5 border-b border-border space-y-2">
                      <h1 className="text-2xl font-bold leading-tight">{result.title}</h1>
                      <div className="flex items-center gap-2 flex-wrap">
                        <Badge variant="outline" className="bg-violet-500/10 border-violet-500/30 text-violet-400 text-xs">
                          {PAPER_TYPE_LABELS[paperType]}
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

                    {/* View/Edit mode toggle */}
                    <div className="flex items-center gap-2 mb-4">
                      <Button
                        variant={viewMode === "view" ? "default" : "outline"}
                        size="sm"
                        onClick={() => setViewMode("view")}
                      >
                        <Eye className="h-4 w-4 mr-1" /> View
                      </Button>
                      <Button
                        variant={viewMode === "edit" ? "default" : "outline"}
                        size="sm"
                        onClick={() => setViewMode("edit")}
                      >
                        <Pencil className="h-4 w-4 mr-1" /> Edit
                      </Button>
                    </div>

                    {/* Venue guidelines display */}
                    {venueGuidelines && venueGuidelines.source !== "manual" && (
                      <div className="flex items-center gap-3 text-sm text-muted-foreground mb-4 p-3 rounded-lg bg-secondary/30 border border-border">
                        <Target className="h-4 w-4 shrink-0 text-violet-400" />
                        <span>
                          {venueGuidelines.venue_name}
                          {venueGuidelines.page_limit && ` · ${venueGuidelines.page_limit} pages`}
                          {venueGuidelines.anonymization && " · Double-blind"}
                          {venueGuidelines.deadline && ` · Due: ${venueGuidelines.deadline}`}
                          <span className="text-muted-foreground/60 ml-1">({venueGuidelines.source})</span>
                        </span>
                      </div>
                    )}

                    {/* Edit mode panel */}
                    {viewMode === "edit" && (
                      <div className="space-y-3 border rounded-lg p-4 bg-muted/30 mb-4">
                        <div className="flex gap-2 flex-wrap">
                          <Button size="sm" variant="outline" onClick={() => setEditInstruction(`Condense to ${venueGuidelines?.page_limit || 8} pages`)}>
                            <Minimize2 className="h-3 w-3 mr-1" /> Condense
                          </Button>
                          <Button size="sm" variant="outline" onClick={() => setEditInstruction("Expand with more detail and examples")}>
                            <Maximize2 className="h-3 w-3 mr-1" /> Expand
                          </Button>
                          <Button size="sm" variant="outline" onClick={() => setEditInstruction("Add a section on ")}>
                            <Plus className="h-3 w-3 mr-1" /> Add Section
                          </Button>
                        </div>
                        <div className="flex gap-2">
                          <Textarea
                            value={editInstruction}
                            onChange={(e) => setEditInstruction(e.target.value)}
                            placeholder="Enter edit instruction (e.g., 'Rewrite the introduction to emphasize the governance gap')"
                            className="min-h-[60px]"
                          />
                          <Button
                            onClick={() => handleEditPaper(editInstruction, editTargetSection)}
                            disabled={isEditing || !editInstruction.trim()}
                            className="shrink-0 bg-violet-600 hover:bg-violet-700 text-white"
                          >
                            {isEditing ? <Loader2 className="h-4 w-4 animate-spin" /> : "Apply"}
                          </Button>
                        </div>
                        {editResult && (
                          <p className="text-xs text-muted-foreground">
                            {editResult.changes_summary}
                            {editResult.sections_modified.length > 0 && (
                              <span className="ml-1">· Modified: {editResult.sections_modified.join(", ")}</span>
                            )}
                          </p>
                        )}
                      </div>
                    )}

                    <AgentLogPanel entries={agentLog} />
                    <RoundtableReviewPanel reviews={roundtableReviews} />

                    {/* Rendered markdown */}
                    <div
                      className="prose-paper text-sm leading-8 text-foreground/90"
                      dangerouslySetInnerHTML={{
                        __html: `<p>${paperMarkdownToHtml(
                          currentVersionContent() +
                            (insertedVisuals.length > 0
                              ? "\n\n---\n\n**Inserted Visuals**\n" + insertedVisuals.join("\n")
                              : ""),
                        )}</p>`,
                      }}
                    />

                    {/* ── Visual content toolbar ── */}
                    <div className="mt-8 pt-6 border-t border-border">
                      <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70 mb-3">
                        Insert Visual Content
                      </p>
                      <div className="flex items-center gap-2 flex-wrap">
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-8 text-xs gap-1.5 border-border hover:border-violet-500/40 hover:bg-violet-500/5 hover:text-violet-300"
                          onClick={() => openVisualDialog("table")}
                        >
                          <Table2 className="w-3.5 h-3.5" />
                          Add Table
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-8 text-xs gap-1.5 border-border hover:border-violet-500/40 hover:bg-violet-500/5 hover:text-violet-300"
                          onClick={() => openVisualDialog("chart")}
                        >
                          <BarChart3 className="w-3.5 h-3.5" />
                          Add Chart
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-8 text-xs gap-1.5 border-border hover:border-violet-500/40 hover:bg-violet-500/5 hover:text-violet-300"
                          onClick={() => openVisualDialog("figure")}
                        >
                          <ImagePlus className="w-3.5 h-3.5" />
                          Add Figure
                        </Button>
                      </div>
                    </div>
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

        {/* ── Right panel (40%) ──────────────────────────────────────────────── */}
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

      {/* ── Visual content dialogs ─────────────────────────────────────────── */}
      <VisualContentDialogs
        projectId={projectId}
        activeDialog={activeVisualDialog}
        onClose={closeVisualDialog}
        onInsert={handleInsertVisual}
        placeholders={{
          tableDescription: "e.g. Compare this project vs existing health data frameworks on privacy, interoperability, and patient control",
          tableItems: "e.g. HAVEN, HL7 FHIR, Blue Button",
          tableCriteria: "e.g. Privacy, Scalability, Cost",
          chartDescription: "e.g. User adoption rates across 5 health systems over 12 months after deploying patient-controlled consent",
          figureArchitecture: "Leave empty to auto-generate from project file tree, or describe the components to highlight",
          figureSequence: "e.g. Patient requests data access → Smart contract evaluates consent → Data released to provider",
          figureFlow: "e.g. Data ingestion → normalization → consent check → release pipeline",
          architectureHint: "Architecture diagrams use the local AI model and your project's workspace snapshot to stay accurate to the actual codebase.",
        }}
      />
    </div>
  );
}
