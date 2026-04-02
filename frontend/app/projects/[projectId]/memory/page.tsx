"use client";

import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { MemoryLogList } from "@/components/MemoryLogList";
import { ConsolidateMemoryButton } from "@/components/ai/ConsolidateMemoryButton";
import { useProjectContext } from "@/components/ProjectContext";
import { useMemory } from "@/lib/hooks/useMemory";
import { memory as memoryApi } from "@/lib/api";
import { toast } from "sonner";
import { Search, Plus, Brain, X, Loader2, Globe } from "lucide-react";
import type { MemoryEntryType, MemoryEntry } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Switch } from "@/components/ui/switch";

const ENTRY_TYPES: { value: MemoryEntryType; label: string }[] = [
  { value: "milestone", label: "Milestone" },
  { value: "insight", label: "Insight" },
  { value: "feedback", label: "Feedback" },
  { value: "decision", label: "Decision" },
  { value: "note", label: "Note" },
  { value: "theme_extraction", label: "Theme" },
  { value: "consolidated_summary", label: "Summary" },
  { value: "preference_pattern", label: "Preference" },
  { value: "commit_summary", label: "Commit" },
  { value: "readme_content", label: "README" },
  { value: "release_note", label: "Release" },
  { value: "user_annotation", label: "Annotation" },
];

export default function MemoryPage() {
  const { project } = useProjectContext();
  const { data: entries, error, isLoading, mutate } = useMemory(project.id);

  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<MemoryEntry[] | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [typeFilter, setTypeFilter] = useState<MemoryEntryType | "all">("all");

  const [crossProject, setCrossProject] = useState(false);
  const crossProjectRef = useRef(crossProject);
  crossProjectRef.current = crossProject;

  const [addOpen, setAddOpen] = useState(false);
  const [addForm, setAddForm] = useState({
    entry_type: "note" as MemoryEntryType,
    content: "",
    source_ref: "",
  });
  const [isAdding, setIsAdding] = useState(false);

  const searchTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  async function handleSearch(query: string) {
    setSearchQuery(query);

    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current);
    }

    if (!query.trim()) {
      setSearchResults(null);
      return;
    }

    searchTimeoutRef.current = setTimeout(async () => {
      setIsSearching(true);
      try {
        const results = crossProjectRef.current
          ? await memoryApi.searchAll(query)
          : await memoryApi.search(project.id, query);
        setSearchResults(results);
      } catch {
        toast.error("Search failed");
      } finally {
        setIsSearching(false);
      }
    }, 400);
  }

  // Re-trigger search when crossProject toggle changes
  useEffect(() => {
    if (searchQuery.trim()) {
      handleSearch(searchQuery);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [crossProject]);

  function clearSearch() {
    setSearchQuery("");
    setSearchResults(null);
  }

  async function handleAdd() {
    if (!addForm.content.trim()) {
      toast.error("Content is required");
      return;
    }
    setIsAdding(true);
    try {
      await memoryApi.create(project.id, {
        entry_type: addForm.entry_type,
        content: addForm.content.trim(),
        source_ref: addForm.source_ref.trim() || undefined,
      });
      await mutate();
      toast.success("Memory entry added");
      setAddOpen(false);
      setAddForm({ entry_type: "note", content: "", source_ref: "" });
    } catch (err) {
      toast.error("Failed to add entry", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setIsAdding(false);
    }
  }

  // Determine which entries to display
  const baseEntries = searchResults ?? entries ?? [];
  const filteredEntries =
    typeFilter === "all"
      ? baseEntries
      : baseEntries.filter((e) => e.entry_type === typeFilter);

  return (
    <div className="p-8 space-y-6 max-w-4xl">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Memory Log</h1>
          <p className="text-sm text-muted-foreground mt-1">
            AI-generated and manually added project insights, milestones, and notes.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <ConsolidateMemoryButton
            projectId={project.id}
            onConsolidated={() => mutate()}
          />
          <Button onClick={() => setAddOpen(true)} className="gap-2">
            <Plus className="w-4 h-4" />
            Add Note
          </Button>
        </div>
      </div>

      {/* Search bar + cross-project toggle */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <Switch
            id="cross-project"
            checked={crossProject}
            onCheckedChange={setCrossProject}
          />
          <Label htmlFor="cross-project" className="text-xs text-muted-foreground flex items-center gap-1 cursor-pointer whitespace-nowrap">
            <Globe className="w-3 h-3" />
            All projects
          </Label>
        </div>
      </div>
      <div className="relative">
        {isSearching ? (
          <Loader2 className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground animate-spin" />
        ) : (
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        )}
        <Input
          value={searchQuery}
          onChange={(e) => handleSearch(e.target.value)}
          placeholder="Search memory entries..."
          className="pl-9 pr-9 bg-secondary/40"
        />
        {searchQuery && (
          <button
            type="button"
            onClick={clearSearch}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Type filter pills */}
      <div className="flex items-center gap-2 flex-wrap">
        <button
          type="button"
          onClick={() => setTypeFilter("all")}
          className={cn(
            "px-3 py-1 rounded-full text-xs font-medium border transition-all",
            typeFilter === "all"
              ? "bg-primary text-primary-foreground border-primary"
              : "border-border text-muted-foreground hover:border-primary/50 hover:text-foreground",
          )}
        >
          All
        </button>
        {ENTRY_TYPES.map((t) => (
          <button
            key={t.value}
            type="button"
            onClick={() => setTypeFilter(t.value)}
            className={cn(
              "px-3 py-1 rounded-full text-xs font-medium border transition-all capitalize",
              typeFilter === t.value
                ? "bg-primary text-primary-foreground border-primary"
                : "border-border text-muted-foreground hover:border-primary/50 hover:text-foreground",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Results info */}
      {searchResults !== null && (
        <p className="text-xs text-muted-foreground">
          {filteredEntries.length} result{filteredEntries.length !== 1 ? "s" : ""} for &quot;{searchQuery}&quot;
        </p>
      )}

      {/* Content */}
      {isLoading ? (
        <div className="animate-pulse space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-20 bg-secondary/40 rounded-lg" />
          ))}
        </div>
      ) : error ? (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          Failed to load memory: {error.message}
        </div>
      ) : filteredEntries.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 gap-3">
          <div className="w-12 h-12 rounded-full bg-secondary flex items-center justify-center">
            <Brain className="w-6 h-6 text-muted-foreground" />
          </div>
          <p className="text-sm text-muted-foreground">
            {searchQuery ? "No entries match your search." : "No memory entries yet."}
          </p>
        </div>
      ) : (
        <MemoryLogList entries={filteredEntries} />
      )}

      {/* Add note dialog */}
      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent className="sm:max-w-md bg-card border-border">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Plus className="w-5 h-5 text-primary" />
              Add Memory Entry
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-4 pt-2">
            <div className="space-y-2">
              <Label>Type</Label>
              <Select
                value={addForm.entry_type}
                onValueChange={(v) =>
                  setAddForm((f) => ({ ...f, entry_type: v as MemoryEntryType }))
                }
              >
                <SelectTrigger className="bg-secondary/40">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ENTRY_TYPES.map((t) => (
                    <SelectItem key={t.value} value={t.value}>
                      {t.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Content</Label>
              <Textarea
                value={addForm.content}
                onChange={(e) =>
                  setAddForm((f) => ({ ...f, content: e.target.value }))
                }
                placeholder="Describe the insight, milestone, or note..."
                className="bg-secondary/40 resize-none"
                rows={4}
              />
            </div>

            <div className="space-y-2">
              <Label>Source reference (optional)</Label>
              <Input
                value={addForm.source_ref}
                onChange={(e) =>
                  setAddForm((f) => ({ ...f, source_ref: e.target.value }))
                }
                placeholder="URL, commit SHA, issue number..."
                className="bg-secondary/40 font-mono text-sm"
              />
            </div>

            <Button
              className="w-full gap-2"
              onClick={handleAdd}
              disabled={isAdding}
            >
              {isAdding ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Plus className="w-4 h-4" />
              )}
              {isAdding ? "Adding..." : "Add entry"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
