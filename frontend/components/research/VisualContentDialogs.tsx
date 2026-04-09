"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { paper as paperApi } from "@/lib/api";
import { toast } from "sonner";
import {
  Loader2,
  Sparkles,
  Check,
  Table2,
  BarChart3,
  ImagePlus,
} from "lucide-react";
import type {
  GenerateTableResponse,
  GenerateChartResponse,
  GenerateFigureResponse,
} from "@/lib/types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type VisualDialogType = "table" | "chart" | "figure" | null;

export interface VisualContentDialogsProps {
  /** Project ID used for the visual generation API calls. */
  projectId: string;
  /** Which dialog is currently open (null = all closed). */
  activeDialog: VisualDialogType;
  /** Called when a dialog is dismissed without inserting. */
  onClose: () => void;
  /** Called with the Markdown/Mermaid content to insert into the paper. */
  onInsert: (content: string) => void;
  /** Placeholder tweaks for portfolio vs single-project context. */
  placeholders?: {
    tableDescription?: string;
    tableItems?: string;
    tableCriteria?: string;
    chartDescription?: string;
    figureArchitecture?: string;
    figureSequence?: string;
    figureFlow?: string;
    architectureHint?: string;
  };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function VisualContentDialogs({
  projectId,
  activeDialog,
  onClose,
  onInsert,
  placeholders,
}: VisualContentDialogsProps) {
  // ── Internal state ───────────────────────────────────────────────────────
  const [visualDescription, setVisualDescription] = useState("");
  const [tableItems, setTableItems] = useState("");
  const [tableCriteria, setTableCriteria] = useState("");
  const [chartType, setChartType] = useState<"bar" | "line" | "pie" | "radar">("bar");
  const [figureType, setFigureType] = useState<"architecture" | "flow" | "sequence" | "class">("flow");
  const [isGenerating, setIsGenerating] = useState(false);
  const [visualResult, setVisualResult] = useState<
    GenerateTableResponse | GenerateChartResponse | GenerateFigureResponse | null
  >(null);

  // ── Handlers ─────────────────────────────────────────────────────────────
  function handleClose() {
    setVisualResult(null);
    setIsGenerating(false);
    onClose();
  }

  async function handleGenerate() {
    if (!visualDescription.trim() && activeDialog !== "figure") {
      toast.error("Please describe what you need");
      return;
    }
    setIsGenerating(true);
    setVisualResult(null);
    try {
      if (activeDialog === "table") {
        const res = await paperApi.generateTable(projectId, {
          description: visualDescription.trim(),
          items: tableItems.trim() ? tableItems.split(",").map((s) => s.trim()) : undefined,
          criteria: tableCriteria.trim() ? tableCriteria.split(",").map((s) => s.trim()) : undefined,
        });
        setVisualResult(res);
      } else if (activeDialog === "chart") {
        const res = await paperApi.generateChart(projectId, {
          chart_type: chartType,
          description: visualDescription.trim(),
        });
        setVisualResult(res);
      } else if (activeDialog === "figure") {
        const res = await paperApi.generateFigure(projectId, {
          figure_type: figureType,
          description: visualDescription.trim() || `${figureType} diagram for this project`,
        });
        setVisualResult(res);
      }
    } catch {
      toast.error("Visual generation failed");
    } finally {
      setIsGenerating(false);
    }
  }

  function handleInsert() {
    if (!visualResult) return;
    let content = "";
    if ("markdown" in visualResult) {
      content = `\n\n${(visualResult as GenerateTableResponse).markdown}\n\n`;
    } else if ("mermaid_source" in visualResult && "data" in visualResult) {
      const chart = visualResult as GenerateChartResponse;
      content = `\n\n\`\`\`mermaid\n${chart.mermaid_source}\n\`\`\`\n\n`;
    } else if ("mermaid_source" in visualResult) {
      const fig = visualResult as GenerateFigureResponse;
      content = `\n\n\`\`\`mermaid\n${fig.mermaid_source}\n\`\`\`\n\n`;
    }
    onInsert(content);
    toast.success("Visual inserted into paper");
    handleClose();
  }

  // ── Render ───────────────────────────────────────────────────────────────
  return (
    <>
      {/* Table dialog */}
      <Dialog
        open={activeDialog === "table"}
        onOpenChange={(o) => { if (!o) handleClose(); }}
      >
        <DialogContent className="sm:max-w-[580px] bg-card border-border">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base">
              <Table2 className="w-4 h-4 text-violet-400" />
              Generate Comparison Table
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-3 py-2">
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">
                What should this table compare?
              </label>
              <Textarea
                value={visualDescription}
                onChange={(e) => setVisualDescription(e.target.value)}
                placeholder={placeholders?.tableDescription ?? "e.g. Compare this project vs existing frameworks on privacy, interoperability, and control"}
                rows={3}
                className="resize-none bg-secondary/30 focus-visible:ring-violet-500/50 text-sm"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">
                  Row items <span className="text-muted-foreground/50">(comma-separated, optional)</span>
                </label>
                <Input
                  value={tableItems}
                  onChange={(e) => setTableItems(e.target.value)}
                  placeholder={placeholders?.tableItems ?? "e.g. ProjectA, ProjectB, ProjectC"}
                  className="bg-secondary/30 text-xs h-8 focus-visible:ring-violet-500/50"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">
                  Column criteria <span className="text-muted-foreground/50">(comma-separated, optional)</span>
                </label>
                <Input
                  value={tableCriteria}
                  onChange={(e) => setTableCriteria(e.target.value)}
                  placeholder={placeholders?.tableCriteria ?? "e.g. Performance, Scalability, Cost"}
                  className="bg-secondary/30 text-xs h-8 focus-visible:ring-violet-500/50"
                />
              </div>
            </div>

            {/* Preview */}
            {visualResult && "markdown" in visualResult && (
              <div className="space-y-1.5">
                <p className="text-xs font-medium text-muted-foreground">Preview</p>
                <pre className="bg-secondary/30 border border-border rounded p-3 text-xs font-mono overflow-x-auto whitespace-pre">
                  {(visualResult as GenerateTableResponse).markdown}
                </pre>
              </div>
            )}
          </div>

          <DialogFooter className="gap-2">
            <Button variant="ghost" size="sm" onClick={handleClose} className="h-8 text-xs">
              Cancel
            </Button>
            {visualResult && "markdown" in visualResult ? (
              <Button
                size="sm"
                className="h-8 text-xs gap-1.5 bg-violet-600 hover:bg-violet-700 text-white"
                onClick={handleInsert}
              >
                <Check className="w-3.5 h-3.5" />
                Insert into Paper
              </Button>
            ) : (
              <Button
                size="sm"
                className="h-8 text-xs gap-1.5 bg-violet-600 hover:bg-violet-700 text-white"
                onClick={handleGenerate}
                disabled={isGenerating || !visualDescription.trim()}
              >
                {isGenerating ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Sparkles className="w-3.5 h-3.5" />
                )}
                Generate Table
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Chart dialog */}
      <Dialog
        open={activeDialog === "chart"}
        onOpenChange={(o) => { if (!o) handleClose(); }}
      >
        <DialogContent className="sm:max-w-[580px] bg-card border-border">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base">
              <BarChart3 className="w-4 h-4 text-violet-400" />
              Generate Chart
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-3 py-2">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">Chart Type</label>
                <Select
                  value={chartType}
                  onValueChange={(v) => setChartType(v as typeof chartType)}
                >
                  <SelectTrigger className="bg-secondary/30 h-8 text-xs focus:ring-violet-500/50">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="bar">Bar Chart</SelectItem>
                    <SelectItem value="line">Line Chart</SelectItem>
                    <SelectItem value="pie">Pie Chart</SelectItem>
                    <SelectItem value="radar">Radar Chart</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">
                What data should this chart show?
              </label>
              <Textarea
                value={visualDescription}
                onChange={(e) => setVisualDescription(e.target.value)}
                placeholder={placeholders?.chartDescription ?? "e.g. Compare key metrics across the selected projects"}
                rows={3}
                className="resize-none bg-secondary/30 focus-visible:ring-violet-500/50 text-sm"
              />
            </div>

            {/* SVG preview */}
            {visualResult && "svg" in visualResult && (visualResult as GenerateChartResponse).svg && (
              <div className="space-y-1.5">
                <p className="text-xs font-medium text-muted-foreground">Preview</p>
                <div className="bg-secondary/30 border border-border rounded p-2 overflow-hidden">
                  <img
                    src={`data:image/svg+xml;base64,${(visualResult as GenerateChartResponse).svg}`}
                    alt="Generated chart"
                    className="w-full max-h-48 object-contain"
                  />
                </div>
              </div>
            )}
          </div>

          <DialogFooter className="gap-2">
            <Button variant="ghost" size="sm" onClick={handleClose} className="h-8 text-xs">
              Cancel
            </Button>
            {visualResult && "data" in visualResult ? (
              <Button
                size="sm"
                className="h-8 text-xs gap-1.5 bg-violet-600 hover:bg-violet-700 text-white"
                onClick={handleInsert}
              >
                <Check className="w-3.5 h-3.5" />
                Insert into Paper
              </Button>
            ) : (
              <Button
                size="sm"
                className="h-8 text-xs gap-1.5 bg-violet-600 hover:bg-violet-700 text-white"
                onClick={handleGenerate}
                disabled={isGenerating || !visualDescription.trim()}
              >
                {isGenerating ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Sparkles className="w-3.5 h-3.5" />
                )}
                Generate Chart
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Figure dialog */}
      <Dialog
        open={activeDialog === "figure"}
        onOpenChange={(o) => { if (!o) handleClose(); }}
      >
        <DialogContent className="sm:max-w-[580px] bg-card border-border">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base">
              <ImagePlus className="w-4 h-4 text-violet-400" />
              Generate Figure
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-3 py-2">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">Figure Type</label>
                <Select
                  value={figureType}
                  onValueChange={(v) => setFigureType(v as typeof figureType)}
                >
                  <SelectTrigger className="bg-secondary/30 h-8 text-xs focus:ring-violet-500/50">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="architecture">System Architecture</SelectItem>
                    <SelectItem value="flow">Flow Diagram</SelectItem>
                    <SelectItem value="sequence">Sequence Diagram</SelectItem>
                    <SelectItem value="class">Class Diagram</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">
                Description <span className="text-muted-foreground/50">(optional for architecture)</span>
              </label>
              <Textarea
                value={visualDescription}
                onChange={(e) => setVisualDescription(e.target.value)}
                placeholder={
                  figureType === "architecture"
                    ? (placeholders?.figureArchitecture ?? "Leave empty to auto-generate from project file tree, or describe the components to highlight")
                    : figureType === "sequence"
                    ? (placeholders?.figureSequence ?? "e.g. User request → service A processes → service B responds → result returned")
                    : (placeholders?.figureFlow ?? "e.g. Data ingestion → processing → output pipeline")
                }
                rows={3}
                className="resize-none bg-secondary/30 focus-visible:ring-violet-500/50 text-sm"
              />
            </div>

            {figureType === "architecture" && (
              <p className="text-xs text-muted-foreground bg-secondary/30 rounded px-3 py-2 border border-border">
                {placeholders?.architectureHint ?? "Architecture diagrams use the local AI model and your project's workspace snapshot to stay accurate to the actual codebase."}
              </p>
            )}

            {/* SVG preview */}
            {visualResult && "mermaid_source" in visualResult && !("data" in visualResult) && (visualResult as GenerateFigureResponse).svg && (
              <div className="space-y-1.5">
                <p className="text-xs font-medium text-muted-foreground">Preview</p>
                <div className="bg-secondary/30 border border-border rounded p-2 overflow-hidden">
                  <img
                    src={`data:image/svg+xml;base64,${(visualResult as GenerateFigureResponse).svg}`}
                    alt="Generated figure"
                    className="w-full max-h-64 object-contain"
                  />
                </div>
              </div>
            )}
          </div>

          <DialogFooter className="gap-2">
            <Button variant="ghost" size="sm" onClick={handleClose} className="h-8 text-xs">
              Cancel
            </Button>
            {visualResult && "mermaid_source" in visualResult && !("data" in visualResult) ? (
              <Button
                size="sm"
                className="h-8 text-xs gap-1.5 bg-violet-600 hover:bg-violet-700 text-white"
                onClick={handleInsert}
              >
                <Check className="w-3.5 h-3.5" />
                Insert into Paper
              </Button>
            ) : (
              <Button
                size="sm"
                className="h-8 text-xs gap-1.5 bg-violet-600 hover:bg-violet-700 text-white"
                onClick={handleGenerate}
                disabled={isGenerating}
              >
                {isGenerating ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Sparkles className="w-3.5 h-3.5" />
                )}
                Generate Figure
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
