"use client";

import { useState, useRef, useCallback } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { research as researchApi } from "@/lib/api";
import { toast } from "sonner";
import {
  Search,
  Loader2,
  ExternalLink,
  Copy,
  MessageSquarePlus,
  Users,
  Quote,
  BookOpen,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { PaperResult } from "@/lib/types";

interface PaperSearchDialogProps {
  projectId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Called when the user clicks "Use in chat" — passes citation string */
  onUsePaper: (citationString: string) => void;
}

// Truncate a string to a max character length, appending ellipsis if needed
function truncate(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text;
  return `${text.slice(0, maxLen).trimEnd()}…`;
}

// Format authors array for display — show up to 3, then "et al."
function formatAuthors(authors: string[]): string {
  if (authors.length === 0) return "Unknown authors";
  if (authors.length <= 3) return authors.join(", ");
  return `${authors.slice(0, 3).join(", ")} et al.`;
}

function PaperCard({
  paper,
  onCopy,
  onUse,
}: {
  paper: PaperResult;
  onCopy: (paper: PaperResult) => void;
  onUse: (paper: PaperResult) => void;
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-4 space-y-2 hover:border-violet-500/30 transition-colors group">
      {/* Title row */}
      <div className="flex items-start gap-2">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium leading-snug line-clamp-2 group-hover:text-violet-400 transition-colors">
            {paper.title}
          </p>
        </div>
        {paper.year && (
          <Badge
            variant="outline"
            className="shrink-0 text-[10px] h-5 bg-violet-500/10 text-violet-400 border-violet-500/30"
          >
            {paper.year}
          </Badge>
        )}
      </div>

      {/* Authors */}
      <div className="flex items-center gap-1 text-xs text-muted-foreground">
        <Users className="w-3 h-3 shrink-0" />
        <span className="truncate">{formatAuthors(paper.authors)}</span>
      </div>

      {/* Abstract */}
      {paper.abstract && (
        <p className="text-xs text-muted-foreground leading-relaxed line-clamp-3">
          {truncate(paper.abstract, 280)}
        </p>
      )}

      {/* Footer: citation count + actions */}
      <div className="flex items-center justify-between pt-1">
        <div className="flex items-center gap-1 text-xs text-muted-foreground">
          <Quote className="w-3 h-3" />
          <span>{paper.citation_count.toLocaleString()} citations</span>
        </div>

        <div className="flex items-center gap-1.5">
          {paper.url && (
            <a
              href={paper.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 h-6 px-2 text-xs text-muted-foreground hover:text-foreground rounded-md hover:bg-accent transition-colors"
            >
              <ExternalLink className="w-3 h-3" />
              View
            </a>
          )}
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-2 text-xs text-muted-foreground hover:text-foreground gap-1"
            onClick={() => onCopy(paper)}
          >
            <Copy className="w-3 h-3" />
            Copy citation
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-6 px-2 text-xs border-violet-500/30 text-violet-400 hover:bg-violet-500/10 hover:text-violet-300 gap-1"
            onClick={() => onUse(paper)}
          >
            <MessageSquarePlus className="w-3 h-3" />
            Use in chat
          </Button>
        </div>
      </div>
    </div>
  );
}

export function PaperSearchDialog({
  projectId,
  open,
  onOpenChange,
  onUsePaper,
}: PaperSearchDialogProps) {
  const [query, setQuery] = useState("");
  const [isSearching, setIsSearching] = useState(false);
  const [results, setResults] = useState<PaperResult[]>([]);
  const [hasSearched, setHasSearched] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleSearch = useCallback(async () => {
    const q = query.trim();
    if (!q || isSearching) return;

    setIsSearching(true);
    setHasSearched(true);

    try {
      const res = await researchApi.searchPapers(projectId, q);
      setResults(res.papers);
    } catch (err) {
      toast.error("Paper search failed", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
      setResults([]);
    } finally {
      setIsSearching(false);
    }
  }, [query, isSearching, projectId]);

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      handleSearch();
    }
  }

  function handleCopy(paper: PaperResult) {
    navigator.clipboard.writeText(paper.citation_string).then(() => {
      toast.success("Citation copied to clipboard");
    });
  }

  function handleUse(paper: PaperResult) {
    onUsePaper(paper.citation_string);
    onOpenChange(false);
    toast.success("Citation added to message");
  }

  // Reset state when dialog closes
  function handleOpenChange(nextOpen: boolean) {
    if (!nextOpen) {
      setQuery("");
      setResults([]);
      setHasSearched(false);
    }
    onOpenChange(nextOpen);
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-2xl max-h-[80vh] flex flex-col gap-0 p-0 overflow-hidden">
        <DialogHeader className="px-5 pt-5 pb-4 border-b border-border shrink-0">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-violet-500/10 border border-violet-500/20 flex items-center justify-center">
              <BookOpen className="w-3.5 h-3.5 text-violet-400" />
            </div>
            <DialogTitle className="text-base">Search Academic Papers</DialogTitle>
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            Powered by Semantic Scholar — search millions of academic papers
          </p>
        </DialogHeader>

        {/* Search input */}
        <div className="flex gap-2 px-5 py-3 border-b border-border shrink-0">
          <div className="relative flex-1">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground pointer-events-none" />
            <Input
              ref={inputRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="e.g. transformer attention mechanisms, RAG retrieval augmented generation…"
              className="pl-8 text-sm bg-secondary/30 focus-visible:ring-1 focus-visible:ring-violet-500/50 focus-visible:border-violet-500/40"
              autoFocus
            />
          </div>
          <Button
            onClick={handleSearch}
            disabled={!query.trim() || isSearching}
            className="shrink-0 bg-violet-600 hover:bg-violet-700 text-white"
          >
            {isSearching ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Search className="w-4 h-4" />
            )}
            Search
          </Button>
        </div>

        {/* Results area */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
          {isSearching ? (
            // Loading skeleton — paper search can take a few seconds
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <div
                  key={i}
                  className="rounded-lg border border-border bg-card p-4 space-y-2 animate-pulse"
                >
                  <div className="h-4 bg-muted rounded w-3/4" />
                  <div className="h-3 bg-muted rounded w-1/3" />
                  <div className="h-3 bg-muted rounded w-full" />
                  <div className="h-3 bg-muted rounded w-5/6" />
                </div>
              ))}
            </div>
          ) : hasSearched && results.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 gap-3 text-center">
              <div className="w-10 h-10 rounded-xl bg-muted/50 flex items-center justify-center">
                <Search className="w-5 h-5 text-muted-foreground" />
              </div>
              <div className="space-y-1">
                <p className="text-sm font-medium">No papers found</p>
                <p className="text-xs text-muted-foreground">
                  Try different keywords or a broader search term
                </p>
              </div>
            </div>
          ) : !hasSearched ? (
            <div className="flex flex-col items-center justify-center py-12 gap-3 text-center">
              <div className="w-10 h-10 rounded-xl bg-violet-500/10 border border-violet-500/20 flex items-center justify-center">
                <BookOpen className="w-5 h-5 text-violet-400" />
              </div>
              <div className="space-y-1">
                <p className="text-sm font-medium text-muted-foreground">
                  Search for academic literature
                </p>
                <p className="text-xs text-muted-foreground">
                  Find papers to cite or add as context to your research conversation
                </p>
              </div>
            </div>
          ) : (
            results.map((paper) => (
              <PaperCard
                key={paper.paper_id}
                paper={paper}
                onCopy={handleCopy}
                onUse={handleUse}
              />
            ))
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
