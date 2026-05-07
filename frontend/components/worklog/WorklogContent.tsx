"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { worklog as worklogApi, projects as projectsApi } from "@/lib/api";
import { toast } from "sonner";
import type {
  WorkLogReport,
  WorkLogGoal,
  WorkLogListResponse,
  Project,
} from "@/lib/types";
import {
  FileText,
  Plus,
  Trash2,
  Loader2,
  Download,
  Copy,
  Calendar,
  CheckCircle2,
  Circle,
  ClipboardList,
  ArrowLeft,
  ChevronDown,
  ChevronUp,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { formatDistanceToNow } from "@/lib/utils";
import { paperMarkdownToHtml } from "@/lib/markdown";

// ─── Helpers ─────────────────────────────────────────────────────────────────

type PeriodType = "weekly" | "monthly" | "quarterly";

function getDefaultDates(type: PeriodType): [string, string] {
  const now = new Date();
  if (type === "weekly") {
    const mon = new Date(now);
    mon.setDate(now.getDate() - now.getDay() + 1);
    const sun = new Date(mon);
    sun.setDate(mon.getDate() + 6);
    return [mon.toISOString().split("T")[0], sun.toISOString().split("T")[0]];
  }
  if (type === "monthly") {
    const start = new Date(now.getFullYear(), now.getMonth(), 1);
    const end = new Date(now.getFullYear(), now.getMonth() + 1, 0);
    return [start.toISOString().split("T")[0], end.toISOString().split("T")[0]];
  }
  // quarterly
  const qMonth = Math.floor(now.getMonth() / 3) * 3;
  const start = new Date(now.getFullYear(), qMonth, 1);
  const end = new Date(now.getFullYear(), qMonth + 3, 0);
  return [start.toISOString().split("T")[0], end.toISOString().split("T")[0]];
}

const PERIOD_LABELS: Record<PeriodType, string> = {
  weekly: "Weekly",
  monthly: "Monthly",
  quarterly: "Quarterly",
};

const PERIOD_BADGE_COLORS: Record<string, string> = {
  weekly: "bg-blue-900/40 text-blue-400 border-blue-700/50",
  monthly: "bg-violet-900/40 text-violet-400 border-violet-700/50",
  quarterly: "bg-amber-900/40 text-amber-400 border-amber-700/50",
};

// ─── Component ────────────────────────────────────────────────────────────────

export function WorklogContent() {
  // ── Projects ──────────────────────────────────────────────────────────────
  const [projectList, setProjectList] = useState<Project[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(true);
  const [selectedProjectIds, setSelectedProjectIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    projectsApi
      .list()
      .then((list) => {
        setProjectList(list);
        // Select all by default
        setSelectedProjectIds(new Set(list.map((p) => p.id)));
      })
      .catch(() => toast.error("Failed to load projects"))
      .finally(() => setProjectsLoading(false));
  }, []);

  // ── Form state ────────────────────────────────────────────────────────────
  const [periodType, setPeriodType] = useState<PeriodType>("weekly");
  const [periodStart, setPeriodStart] = useState(() => getDefaultDates("weekly")[0]);
  const [periodEnd, setPeriodEnd] = useState(() => getDefaultDates("weekly")[1]);
  const [goals, setGoals] = useState<WorkLogGoal[]>([]);
  const [showInstructions, setShowInstructions] = useState(false);
  const [additionalInstructions, setAdditionalInstructions] = useState("");

  // Auto-fill dates when period type changes
  function handlePeriodChange(type: PeriodType) {
    setPeriodType(type);
    const [s, e] = getDefaultDates(type);
    setPeriodStart(s);
    setPeriodEnd(e);
  }

  // ── Goals editor ──────────────────────────────────────────────────────────
  function addGoal() {
    setGoals((prev) => [...prev, { description: "", achieved: false, evidence: "" }]);
  }

  function updateGoal(index: number, field: keyof WorkLogGoal, value: string | boolean) {
    setGoals((prev) => prev.map((g, i) => (i === index ? { ...g, [field]: value } : g)));
  }

  function removeGoal(index: number) {
    setGoals((prev) => prev.filter((_, i) => i !== index));
  }

  // ── Project selection ─────────────────────────────────────────────────────
  function toggleProject(id: string) {
    setSelectedProjectIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  function toggleAllProjects() {
    if (selectedProjectIds.size === projectList.length) {
      setSelectedProjectIds(new Set());
    } else {
      setSelectedProjectIds(new Set(projectList.map((p) => p.id)));
    }
  }

  // ── Generation ────────────────────────────────────────────────────────────
  const [isGenerating, setIsGenerating] = useState(false);
  const [result, setResult] = useState<WorkLogReport | null>(null);

  async function handleGenerate() {
    if (selectedProjectIds.size === 0) {
      toast.error("Select at least one project");
      return;
    }
    setIsGenerating(true);
    setResult(null);
    try {
      const report = await worklogApi.generate({
        period_type: periodType,
        period_start: periodStart,
        period_end: periodEnd,
        project_ids: Array.from(selectedProjectIds),
        goals,
        additional_instructions: additionalInstructions || undefined,
      });
      setResult(report);
      toast.success("Work log generated");
      // Refresh history
      fetchHistory();
    } catch (err) {
      toast.error("Generation failed", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setIsGenerating(false);
    }
  }

  // ── DOCX export ───────────────────────────────────────────────────────────
  const [isExporting, setIsExporting] = useState(false);

  async function handleExportDocx() {
    if (!result) return;
    setIsExporting(true);
    try {
      const res = await worklogApi.exportDocx(result.id);
      const bytes = Uint8Array.from(atob(res.docx_base64), (c) => c.charCodeAt(0));
      const blob = new Blob([bytes], {
        type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = res.filename;
      a.click();
      URL.revokeObjectURL(url);
      toast.success("DOCX downloaded");
    } catch (err) {
      toast.error("Export failed", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setIsExporting(false);
    }
  }

  function handleCopyMarkdown() {
    if (!result) return;
    navigator.clipboard.writeText(result.content);
    toast.success("Markdown copied to clipboard");
  }

  // ── History ───────────────────────────────────────────────────────────────
  const [history, setHistory] = useState<WorkLogReport[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);

  const fetchHistory = useCallback(async () => {
    try {
      const res = await worklogApi.list(20);
      setHistory(res.reports);
    } catch {
      // silent — non-critical
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  async function handleLoadReport(id: string) {
    try {
      const report = await worklogApi.get(id);
      setResult(report);
    } catch (err) {
      toast.error("Failed to load report", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    }
  }

  async function handleDeleteReport(id: string) {
    try {
      await worklogApi.delete(id);
      setHistory((prev) => prev.filter((r) => r.id !== id));
      if (result?.id === id) setResult(null);
      toast.success("Report deleted");
    } catch (err) {
      toast.error("Delete failed", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    }
  }

  // ─── Render ───────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-border bg-card/50 backdrop-blur-sm sticky top-0 z-20">
        <div className="max-w-[1600px] mx-auto px-6 py-4 flex items-center gap-4">
          <Link
            href="/projects"
            className="text-muted-foreground hover:text-foreground transition-colors"
          >
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div className="flex items-center gap-2.5">
            <ClipboardList className="w-5 h-5 text-primary" />
            <h1 className="text-lg font-semibold text-foreground">Work Log</h1>
          </div>
          <p className="text-sm text-muted-foreground hidden sm:block">
            Generate structured reports from your project activity
          </p>
        </div>
      </header>

      {/* Main content */}
      <div className="max-w-[1600px] mx-auto px-6 py-6 flex gap-6">
        {/* ── Left panel (form + preview) ──────────────────────────────────── */}
        <div className="flex-1 min-w-0 space-y-6">
          {/* Form card */}
          <Card>
            <CardHeader className="pb-4">
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <Calendar className="w-4 h-4 text-muted-foreground" />
                Report Configuration
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              {/* Period type tabs */}
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-2 block">
                  Period
                </label>
                <div className="flex gap-2">
                  {(["weekly", "monthly", "quarterly"] as PeriodType[]).map((type) => (
                    <button
                      key={type}
                      onClick={() => handlePeriodChange(type)}
                      className={cn(
                        "px-4 py-2 rounded-md text-sm font-medium transition-colors border",
                        periodType === type
                          ? "bg-primary/15 text-primary border-primary/30"
                          : "bg-secondary/40 text-muted-foreground border-border hover:bg-secondary/60",
                      )}
                    >
                      {PERIOD_LABELS[type]}
                    </button>
                  ))}
                </div>
              </div>

              {/* Date range */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-xs font-medium text-muted-foreground mb-1.5 block">
                    Start Date
                  </label>
                  <Input
                    type="date"
                    value={periodStart}
                    onChange={(e) => setPeriodStart(e.target.value)}
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground mb-1.5 block">
                    End Date
                  </label>
                  <Input
                    type="date"
                    value={periodEnd}
                    onChange={(e) => setPeriodEnd(e.target.value)}
                  />
                </div>
              </div>

              {/* Project selector */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-xs font-medium text-muted-foreground">
                    Projects
                  </label>
                  <button
                    onClick={toggleAllProjects}
                    className="text-xs text-primary hover:text-primary/80 transition-colors"
                  >
                    {selectedProjectIds.size === projectList.length ? "Deselect All" : "Select All"}
                  </button>
                </div>
                {projectsLoading ? (
                  <div className="flex items-center gap-2 text-xs text-muted-foreground py-2">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    Loading projects...
                  </div>
                ) : projectList.length === 0 ? (
                  <p className="text-xs text-muted-foreground py-2">No projects found</p>
                ) : (
                  <div className="grid grid-cols-2 gap-2">
                    {projectList.map((project) => (
                      <label
                        key={project.id}
                        className={cn(
                          "flex items-center gap-2.5 px-3 py-2 rounded-md border cursor-pointer transition-colors text-sm",
                          selectedProjectIds.has(project.id)
                            ? "bg-primary/10 border-primary/30 text-foreground"
                            : "bg-secondary/30 border-border text-muted-foreground hover:bg-secondary/50",
                        )}
                      >
                        <input
                          type="checkbox"
                          checked={selectedProjectIds.has(project.id)}
                          onChange={() => toggleProject(project.id)}
                          className="rounded border-border accent-primary w-3.5 h-3.5"
                        />
                        <span className="truncate">{project.name}</span>
                      </label>
                    ))}
                  </div>
                )}
              </div>

              {/* Goals editor */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-xs font-medium text-muted-foreground">
                    Goals (optional)
                  </label>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={addGoal}
                    className="h-7 gap-1 text-xs"
                  >
                    <Plus className="w-3 h-3" />
                    Add Goal
                  </Button>
                </div>
                {goals.length === 0 ? (
                  <p className="text-xs text-muted-foreground/60 py-1">
                    No goals set. Goals help the AI measure your progress.
                  </p>
                ) : (
                  <div className="space-y-3">
                    {goals.map((goal, idx) => (
                      <div
                        key={idx}
                        className="border border-border rounded-md p-3 space-y-2 bg-secondary/20"
                      >
                        <div className="flex items-start gap-2">
                          <button
                            onClick={() => updateGoal(idx, "achieved", !goal.achieved)}
                            className="mt-0.5 shrink-0"
                          >
                            {goal.achieved ? (
                              <CheckCircle2 className="w-4 h-4 text-green-400" />
                            ) : (
                              <Circle className="w-4 h-4 text-muted-foreground" />
                            )}
                          </button>
                          <Input
                            placeholder="Goal description..."
                            value={goal.description}
                            onChange={(e) => updateGoal(idx, "description", e.target.value)}
                            className="flex-1 h-8 text-sm"
                          />
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => removeGoal(idx)}
                            className="h-8 w-8 p-0 text-muted-foreground hover:text-destructive"
                          >
                            <X className="w-3.5 h-3.5" />
                          </Button>
                        </div>
                        <Input
                          placeholder="Evidence / notes (optional)..."
                          value={goal.evidence}
                          onChange={(e) => updateGoal(idx, "evidence", e.target.value)}
                          className="h-8 text-sm ml-6"
                        />
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Additional instructions (collapsed by default) */}
              <div>
                <button
                  onClick={() => setShowInstructions(!showInstructions)}
                  className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
                >
                  {showInstructions ? (
                    <ChevronUp className="w-3 h-3" />
                  ) : (
                    <ChevronDown className="w-3 h-3" />
                  )}
                  Additional Instructions
                </button>
                {showInstructions && (
                  <Textarea
                    placeholder="Any specific focus areas, formatting preferences, or context to include..."
                    value={additionalInstructions}
                    onChange={(e) => setAdditionalInstructions(e.target.value)}
                    rows={3}
                    className="mt-2 text-sm"
                  />
                )}
              </div>

              {/* Generate button */}
              <Button
                onClick={handleGenerate}
                disabled={isGenerating || selectedProjectIds.size === 0}
                className="w-full gap-2"
              >
                {isGenerating ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Generating Report...
                  </>
                ) : (
                  <>
                    <FileText className="w-4 h-4" />
                    Generate Report
                  </>
                )}
              </Button>
            </CardContent>
          </Card>

          {/* Preview section */}
          {result ? (
            <Card>
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2.5">
                    <CardTitle className="text-base font-semibold">
                      {result.title}
                    </CardTitle>
                    <Badge
                      variant="outline"
                      className={cn(
                        "text-xs",
                        PERIOD_BADGE_COLORS[result.period_type] || "",
                      )}
                    >
                      {PERIOD_LABELS[result.period_type as PeriodType] || result.period_type}
                    </Badge>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleCopyMarkdown}
                      className="h-8 gap-1.5 text-xs"
                    >
                      <Copy className="w-3.5 h-3.5" />
                      Copy MD
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleExportDocx}
                      disabled={isExporting}
                      className="h-8 gap-1.5 text-xs"
                    >
                      {isExporting ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <Download className="w-3.5 h-3.5" />
                      )}
                      DOCX
                    </Button>
                  </div>
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  {result.period_start} to {result.period_end}
                </p>
              </CardHeader>
              <CardContent>
                <div
                  className="prose prose-invert prose-sm max-w-none text-sm leading-relaxed"
                  dangerouslySetInnerHTML={{
                    __html: paperMarkdownToHtml(result.content),
                  }}
                />
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardContent className="py-16 flex flex-col items-center justify-center text-center">
                <FileText className="w-10 h-10 text-muted-foreground/30 mb-3" />
                <p className="text-sm text-muted-foreground">
                  No report yet. Configure your settings and generate one.
                </p>
              </CardContent>
            </Card>
          )}
        </div>

        {/* ── Right panel (history sidebar) ────────────────────────────────── */}
        <div className="w-[320px] shrink-0 hidden lg:block">
          <Card className="sticky top-[73px]">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-semibold flex items-center gap-2">
                <ClipboardList className="w-4 h-4 text-muted-foreground" />
                Saved Reports
                {history.length > 0 && (
                  <Badge variant="secondary" className="text-xs ml-auto">
                    {history.length}
                  </Badge>
                )}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 max-h-[calc(100vh-180px)] overflow-y-auto">
              {historyLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
                </div>
              ) : history.length === 0 ? (
                <p className="text-xs text-muted-foreground/60 text-center py-8">
                  No saved reports yet
                </p>
              ) : (
                history.map((report) => (
                  <div
                    key={report.id}
                    className={cn(
                      "group border rounded-md p-3 cursor-pointer transition-colors",
                      result?.id === report.id
                        ? "border-primary/40 bg-primary/5"
                        : "border-border hover:border-border/80 hover:bg-secondary/30",
                    )}
                    onClick={() => handleLoadReport(report.id)}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-foreground truncate">
                          {report.title}
                        </p>
                        <div className="flex items-center gap-2 mt-1">
                          <Badge
                            variant="outline"
                            className={cn(
                              "text-[10px] px-1.5 py-0",
                              PERIOD_BADGE_COLORS[report.period_type] || "",
                            )}
                          >
                            {PERIOD_LABELS[report.period_type as PeriodType] || report.period_type}
                          </Badge>
                          <span className="text-[10px] text-muted-foreground">
                            {report.period_start} - {report.period_end}
                          </span>
                        </div>
                        <p className="text-[10px] text-muted-foreground/60 mt-1">
                          {formatDistanceToNow(report.created_at)}
                        </p>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDeleteReport(report.id);
                        }}
                        className="h-7 w-7 p-0 opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-destructive"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
