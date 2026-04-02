"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Layers, Loader2 } from "lucide-react";
import { ai } from "@/lib/api";
import { toast } from "sonner";

interface ConsolidateMemoryButtonProps {
  projectId: string;
  onConsolidated?: () => void;
  variant?: "default" | "outline" | "secondary";
  size?: "default" | "sm" | "lg";
}

export function ConsolidateMemoryButton({
  projectId,
  onConsolidated,
  variant = "outline",
  size = "sm",
}: ConsolidateMemoryButtonProps) {
  const [isConsolidating, setIsConsolidating] = useState(false);

  async function handleConsolidate() {
    setIsConsolidating(true);
    try {
      await ai.consolidateMemory(projectId);
      toast.success("Memory consolidated", {
        description:
          "A consolidated summary has been added to your memory log.",
      });
      onConsolidated?.();
    } catch (err) {
      toast.error("Consolidation failed", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setIsConsolidating(false);
    }
  }

  return (
    <Button
      variant={variant}
      size={size}
      onClick={handleConsolidate}
      disabled={isConsolidating}
      className="gap-2"
    >
      {isConsolidating ? (
        <Loader2 className="w-4 h-4 animate-spin" />
      ) : (
        <Layers className="w-4 h-4" />
      )}
      {isConsolidating ? "Consolidating..." : "Consolidate Memory"}
    </Button>
  );
}
