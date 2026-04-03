// ─── Paper export hook ────────────────────────────────────────────────────────
// Provides clipboard copy and file download handlers for all paper output
// formats. Both paper pages share identical export logic, so it lives here.

import { copyToClipboard, downloadFile } from "@/lib/paper-utils";
import type { PaperGenerateResponse } from "@/lib/types";

export interface UsePaperExportReturn {
  handleCopyMarkdown: () => void;
  handleCopyLatex: () => void;
  handleCopyBibtex: () => void;
  handleDownloadTex: () => void;
  handleDownloadBib: () => void;
}

/**
 * Returns export handlers derived from `result`.
 * When `result` is null every handler is a no-op.
 * The `title` parameter is used to build safe filenames for downloads.
 */
export function usePaperExport(
  result: PaperGenerateResponse | null,
  title: string,
): UsePaperExportReturn {
  // Derive a filesystem-safe base name from the paper title
  const safeName = () =>
    title.toLowerCase().replace(/\s+/g, "_").replace(/[^\w]/g, "").slice(0, 40) || "paper";

  function handleCopyMarkdown() {
    if (!result) return;
    copyToClipboard(result.final_content, "Markdown");
  }

  function handleCopyLatex() {
    if (!result?.latex) return;
    copyToClipboard(result.latex, "LaTeX");
  }

  function handleCopyBibtex() {
    if (!result) return;
    copyToClipboard(result.bibtex, "BibTeX");
  }

  function handleDownloadTex() {
    if (!result?.latex) return;
    downloadFile(result.latex, `${safeName()}.tex`, "application/x-latex");
  }

  function handleDownloadBib() {
    if (!result) return;
    downloadFile(result.bibtex, `${safeName()}.bib`, "text/plain");
  }

  return {
    handleCopyMarkdown,
    handleCopyLatex,
    handleCopyBibtex,
    handleDownloadTex,
    handleDownloadBib,
  };
}
