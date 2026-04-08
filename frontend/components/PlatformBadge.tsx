"use client";

import { Badge } from "@/components/ui/badge";
import type { Platform } from "@/lib/types";

const PLATFORM_LABELS: Record<Platform, string> = {
  linkedin: "LinkedIn",
  twitter: "Twitter / X",
  xiaohongshu: "Xiaohongshu",
  medium_outline: "Medium",
  github_release: "GitHub Release",
  devto: "Dev.to",
  hashnode: "Hashnode",
};

const PLATFORM_COLORS: Record<Platform, string> = {
  linkedin: "bg-blue-600/20 text-blue-400 border-blue-600/30",
  twitter: "bg-sky-600/20 text-sky-400 border-sky-600/30",
  xiaohongshu: "bg-red-600/20 text-red-400 border-red-600/30",
  medium_outline: "bg-emerald-600/20 text-emerald-400 border-emerald-600/30",
  github_release: "bg-purple-600/20 text-purple-400 border-purple-600/30",
  devto: "bg-violet-600/20 text-violet-400 border-violet-600/30",
  hashnode: "text-blue-400 bg-blue-400/10 border-blue-400/30",
};

interface PlatformBadgeProps {
  platform: Platform;
  className?: string;
}

export function PlatformBadge({ platform, className }: PlatformBadgeProps) {
  return (
    <Badge
      variant="outline"
      className={`text-xs font-medium ${PLATFORM_COLORS[platform]} ${className ?? ""}`}
    >
      {PLATFORM_LABELS[platform]}
    </Badge>
  );
}

export { PLATFORM_LABELS };
