"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Copy, Check } from "lucide-react";
import { toast } from "sonner";

interface CopyDraftButtonProps {
  content: string;
  platformLabel: string;
  className?: string;
  size?: "sm" | "default" | "lg" | "icon";
  variant?: "default" | "outline" | "ghost" | "secondary";
}

export function CopyDraftButton({
  content,
  platformLabel,
  className,
  size = "sm",
  variant = "outline",
}: CopyDraftButtonProps) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      toast.success(`Copied for ${platformLabel}!`, {
        description: `Paste into ${platformLabel} to post.`,
      });
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error("Copy failed", {
        description: "Could not access clipboard. Try selecting and copying manually.",
      });
    }
  }

  return (
    <Button
      variant={variant}
      size={size}
      onClick={handleCopy}
      className={`gap-1.5 transition-colors ${className ?? ""}`}
    >
      {copied ? (
        <Check className="w-3.5 h-3.5 text-green-400" />
      ) : (
        <Copy className="w-3.5 h-3.5" />
      )}
      {copied ? "Copied!" : "Copy to Clipboard"}
    </Button>
  );
}
