"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { AngleTagInput } from "@/components/AngleTagInput";
import { useProjectContext } from "@/components/ProjectContext";
import { useNarrative } from "@/lib/hooks/useNarrative";
import { narratives } from "@/lib/api";
import { toast } from "sonner";
import { Save, Loader2, Plus, Trash2, BookOpen } from "lucide-react";
import type { FAQ } from "@/lib/types";

export default function NarrativePage() {
  const { project } = useProjectContext();
  const { data: narrative, error, isLoading, mutate } = useNarrative(project.id);
  const [isSaving, setIsSaving] = useState(false);

  const [form, setForm] = useState({
    one_liner: "",
    target_audience: "",
    origin_story: "",
    tone_notes: "",
    preferred_angles: [] as string[],
    avoided_angles: [] as string[],
    faq: [] as FAQ[],
  });

  // Populate form when narrative loads
  useEffect(() => {
    if (narrative) {
      setForm({
        one_liner: narrative.one_liner ?? "",
        target_audience: narrative.target_audience ?? "",
        origin_story: narrative.origin_story ?? "",
        tone_notes: narrative.tone_notes ?? "",
        preferred_angles: narrative.preferred_angles ?? [],
        avoided_angles: narrative.avoided_angles ?? [],
        faq: narrative.faq ?? [],
      });
    }
  }, [narrative]);

  function addFaq() {
    setForm((f) => ({
      ...f,
      faq: [...f.faq, { question: "", answer: "" }],
    }));
  }

  function updateFaq(index: number, field: keyof FAQ, value: string) {
    setForm((f) => {
      const updated = [...f.faq];
      updated[index] = { ...updated[index], [field]: value };
      return { ...f, faq: updated };
    });
  }

  function removeFaq(index: number) {
    setForm((f) => ({
      ...f,
      faq: f.faq.filter((_, i) => i !== index),
    }));
  }

  async function handleSave() {
    setIsSaving(true);
    try {
      await narratives.update(project.id, {
        one_liner: form.one_liner || undefined,
        target_audience: form.target_audience || undefined,
        origin_story: form.origin_story || undefined,
        tone_notes: form.tone_notes || undefined,
        preferred_angles: form.preferred_angles,
        avoided_angles: form.avoided_angles,
        faq: form.faq.filter((f) => f.question || f.answer),
      });
      await mutate();
      toast.success("Narrative saved", {
        description: "Your project narrative has been updated.",
      });
    } catch (err) {
      toast.error("Failed to save", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setIsSaving(false);
    }
  }

  if (isLoading) {
    return (
      <div className="p-8 max-w-3xl animate-pulse space-y-6">
        <div className="flex items-start justify-between">
          <div className="space-y-2">
            <div className="h-8 w-48 bg-secondary rounded" />
            <div className="h-4 w-80 bg-secondary/60 rounded" />
          </div>
          <div className="h-9 w-20 bg-secondary rounded" />
        </div>
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-40 bg-secondary/40 rounded-lg" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8">
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          Failed to load narrative: {error.message}
        </div>
      </div>
    );
  }

  return (
    <div className="p-8 space-y-6 max-w-3xl">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Project Narrative</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Define your project&apos;s story. This context guides AI-generated content.
          </p>
        </div>
        <Button onClick={handleSave} disabled={isSaving} className="gap-2">
          {isSaving ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Save className="w-4 h-4" />
          )}
          {isSaving ? "Saving..." : "Save"}
        </Button>
      </div>

      {/* Core positioning */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium text-muted-foreground uppercase tracking-wide">
            Positioning
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="one_liner">One-liner</Label>
            <Input
              id="one_liner"
              value={form.one_liner}
              onChange={(e) => setForm((f) => ({ ...f, one_liner: e.target.value }))}
              placeholder="A single sentence that captures what your project does and for whom"
              className="bg-secondary/40"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="target_audience">Target audience</Label>
            <Textarea
              id="target_audience"
              value={form.target_audience}
              onChange={(e) =>
                setForm((f) => ({ ...f, target_audience: e.target.value }))
              }
              placeholder="Who are you building this for? Describe your ideal users."
              className="bg-secondary/40 resize-none"
              rows={3}
            />
          </div>
        </CardContent>
      </Card>

      {/* Story */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium text-muted-foreground uppercase tracking-wide">
            Story
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="origin_story">Origin story</Label>
            <Textarea
              id="origin_story"
              value={form.origin_story}
              onChange={(e) =>
                setForm((f) => ({ ...f, origin_story: e.target.value }))
              }
              placeholder="Why did you build this? What problem were you solving?"
              className="bg-secondary/40 resize-none"
              rows={4}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="tone_notes">Tone &amp; voice</Label>
            <Textarea
              id="tone_notes"
              value={form.tone_notes}
              onChange={(e) =>
                setForm((f) => ({ ...f, tone_notes: e.target.value }))
              }
              placeholder="How should the project sound? Technical? Approachable? Excited? Serious?"
              className="bg-secondary/40 resize-none"
              rows={3}
            />
          </div>
        </CardContent>
      </Card>

      {/* Angles */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium text-muted-foreground uppercase tracking-wide">
            Content Angles
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label>Preferred angles</Label>
            <p className="text-xs text-muted-foreground">
              Topics or angles you want the AI to emphasize. Press Enter to add.
            </p>
            <AngleTagInput
              tags={form.preferred_angles}
              onChange={(tags) =>
                setForm((f) => ({ ...f, preferred_angles: tags }))
              }
              placeholder="Add an angle and press Enter..."
            />
          </div>
          <Separator />
          <div className="space-y-2">
            <Label>Avoided angles</Label>
            <p className="text-xs text-muted-foreground">
              Topics or angles to avoid. Press Enter to add.
            </p>
            <AngleTagInput
              tags={form.avoided_angles}
              onChange={(tags) =>
                setForm((f) => ({ ...f, avoided_angles: tags }))
              }
              placeholder="Add an angle to avoid and press Enter..."
            />
          </div>
        </CardContent>
      </Card>

      {/* FAQ */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-medium text-muted-foreground uppercase tracking-wide">
              FAQ
            </CardTitle>
            <Button variant="ghost" size="sm" onClick={addFaq} className="gap-1.5 text-xs">
              <Plus className="w-3.5 h-3.5" />
              Add question
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {form.faq.length === 0 && (
            <p className="text-sm text-muted-foreground text-center py-4">
              No FAQ entries. Click &quot;Add question&quot; to add common questions and answers.
            </p>
          )}
          {form.faq.map((item, i) => (
            <div key={i} className="space-y-2 p-3 rounded-lg bg-secondary/20 border border-border">
              <div className="flex items-center justify-between">
                <Label className="text-xs text-muted-foreground">Q {i + 1}</Label>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => removeFaq(i)}
                  className="text-muted-foreground hover:text-destructive h-6 w-6 p-0"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </Button>
              </div>
              <Input
                value={item.question}
                onChange={(e) => updateFaq(i, "question", e.target.value)}
                placeholder="Question"
                className="bg-background/50 text-sm"
              />
              <Textarea
                value={item.answer}
                onChange={(e) => updateFaq(i, "answer", e.target.value)}
                placeholder="Answer"
                className="bg-background/50 text-sm resize-none"
                rows={2}
              />
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Bottom save button */}
      <div className="flex justify-end pb-8">
        <Button onClick={handleSave} disabled={isSaving} className="gap-2">
          {isSaving ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Save className="w-4 h-4" />
          )}
          {isSaving ? "Saving..." : "Save narrative"}
        </Button>
      </div>
    </div>
  );
}
