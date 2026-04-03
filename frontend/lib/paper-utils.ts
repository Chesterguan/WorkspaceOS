// ─── Shared paper utilities ───────────────────────────────────────────────────
// Used by both the per-project paper page and the portfolio paper page.

import { toast } from "sonner";
import type { PaperGenerateRequest } from "@/lib/types";

/** Human-readable labels for every supported paper_type value. */
export const PAPER_TYPE_LABELS: Record<PaperGenerateRequest["paper_type"], string> = {
  conference: "Conference Paper",
  journal: "Journal Article",
  technical_report: "Technical Report",
  white_paper: "White Paper",
};

/** Copy `text` to the clipboard and show a toast notification. */
export function copyToClipboard(text: string, label: string): void {
  navigator.clipboard
    .writeText(text)
    .then(() => toast.success(`${label} copied to clipboard`))
    .catch(() => toast.error("Failed to copy"));
}

/** Trigger a browser download for `content` as a file. */
export function downloadFile(
  content: string,
  filename: string,
  mimeType = "text/plain",
): void {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
