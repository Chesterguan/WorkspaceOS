// ─── Shared markdown renderers ────────────────────────────────────────────────
// These are used by both paper pages and the research chat window.
// All renderers are lightweight (no external deps) and safe against XSS because
// they escape raw HTML before applying pattern replacements.

/** Escape &, <, > so raw user/AI text cannot inject HTML. */
export function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

/**
 * Full-featured markdown renderer used by the paper pages.
 * Handles headings, code blocks, inline code, bold, italic,
 * citation badges, unordered lists, and paragraph breaks.
 */
export function paperMarkdownToHtml(text: string): string {
  return escapeHtml(text)
    // Headings (h1-h4)
    .replace(/^#### (.+)$/gm, '<h4 class="text-sm font-semibold mt-5 mb-1 text-foreground">$1</h4>')
    .replace(/^### (.+)$/gm, '<h3 class="text-base font-semibold mt-6 mb-2 text-foreground">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 class="text-lg font-bold mt-7 mb-2 text-foreground">$1</h2>')
    .replace(/^# (.+)$/gm, '<h1 class="text-xl font-bold mt-8 mb-3 text-foreground">$1</h1>')
    // Code blocks
    .replace(/```[\w]*\n?([\s\S]*?)```/g, '<pre class="bg-secondary/40 border border-border rounded p-3 my-3 overflow-x-auto text-xs font-mono"><code>$1</code></pre>')
    // Inline code
    .replace(/`([^`]+)`/g, '<code class="bg-secondary/60 px-1 py-0.5 rounded text-xs font-mono">$1</code>')
    // Bold
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    // Italic
    .replace(/\*([^*]+)\*/g, "<em>$1</em>")
    // Citation markers [1], [2,3] → violet badges
    .replace(
      /\[(\d[\d,\s–\-]*)\]/g,
      '<sup class="inline-flex items-baseline"><span class="inline-block px-1 py-0.5 rounded text-[10px] font-semibold bg-violet-500/15 text-violet-400 border border-violet-500/30 leading-none mx-0.5">[$1]</span></sup>',
    )
    // Unordered lists — simple top-level only
    .replace(/^[-*] (.+)$/gm, '<li class="ml-4 list-disc text-sm leading-relaxed">$1</li>')
    // Paragraphs — blank-line separated blocks
    .replace(/\n{2,}/g, "</p><p>")
    // Line breaks within paragraphs
    .replace(/\n/g, "<br />");
}

/**
 * Slimmer renderer used by the research chat window.
 * Omits headings, paragraph blocks, and list items — chat responses are
 * typically single-paragraph prose with inline citations.
 */
export function researchMarkdownToHtml(text: string): string {
  return escapeHtml(text)
    // Code blocks
    .replace(/```[\w]*\n?([\s\S]*?)```/g, '<pre class="chat-code-block"><code>$1</code></pre>')
    // Inline code
    .replace(/`([^`]+)`/g, '<code class="chat-inline-code">$1</code>')
    // Bold
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    // Italic
    .replace(/\*([^*]+)\*/g, "<em>$1</em>")
    // Citation markers like [1], [2,3], [1–3] — styled as violet badges
    .replace(
      /\[(\d[\d,\s–\-]*)\]/g,
      '<sup class="inline-flex items-baseline"><span class="inline-block px-1 py-0.5 rounded text-[10px] font-semibold bg-violet-500/15 text-violet-400 border border-violet-500/30 leading-none mx-0.5">[$1]</span></sup>',
    )
    // Line breaks
    .replace(/\n/g, "<br />");
}
