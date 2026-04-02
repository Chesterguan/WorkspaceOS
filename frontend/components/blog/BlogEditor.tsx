"use client";

import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

interface BlogEditorProps {
  content: string;
  onChange: (value: string) => void;
  className?: string;
}

// Minimal markdown-to-HTML renderer for preview (no external deps)
function renderMarkdown(md: string): string {
  let html = md
    // Escape HTML entities first
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  // Headings
  html = html.replace(/^###### (.+)$/gm, "<h6>$1</h6>");
  html = html.replace(/^##### (.+)$/gm, "<h5>$1</h5>");
  html = html.replace(/^#### (.+)$/gm, "<h4>$1</h4>");
  html = html.replace(/^### (.+)$/gm, "<h3>$1</h3>");
  html = html.replace(/^## (.+)$/gm, "<h2>$1</h2>");
  html = html.replace(/^# (.+)$/gm, "<h1>$1</h1>");

  // Bold and italic
  html = html.replace(/\*\*\*(.+?)\*\*\*/g, "<strong><em>$1</em></strong>");
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");

  // Inline code
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");

  // Blockquotes
  html = html.replace(/^&gt; (.+)$/gm, "<blockquote>$1</blockquote>");

  // Unordered lists — wrap groups of - lines in <ul>
  html = html.replace(/((?:^[-*] .+\n?)+)/gm, (match) => {
    const items = match
      .trim()
      .split("\n")
      .map((line) => `<li>${line.replace(/^[-*] /, "")}</li>`)
      .join("");
    return `<ul>${items}</ul>`;
  });

  // Ordered lists
  html = html.replace(/((?:^\d+\. .+\n?)+)/gm, (match) => {
    const items = match
      .trim()
      .split("\n")
      .map((line) => `<li>${line.replace(/^\d+\. /, "")}</li>`)
      .join("");
    return `<ol>${items}</ol>`;
  });

  // Horizontal rules
  html = html.replace(/^---$/gm, "<hr />");

  // Paragraphs — lines not already wrapped in block elements
  html = html
    .split("\n\n")
    .map((block) => {
      const trimmed = block.trim();
      if (!trimmed) return "";
      // Already a block element
      if (/^<(h[1-6]|ul|ol|blockquote|hr|li|p)/.test(trimmed)) return trimmed;
      return `<p>${trimmed.replace(/\n/g, "<br />")}</p>`;
    })
    .join("\n");

  return html;
}

export function BlogEditor({ content, onChange, className }: BlogEditorProps) {
  const wordCount = content.trim()
    ? content.trim().split(/\s+/).length
    : 0;

  return (
    <div className={cn("grid grid-cols-2 gap-0 h-full", className)}>
      {/* Editor pane */}
      <div className="flex flex-col border-r border-border">
        <div className="px-4 py-2 border-b border-border bg-secondary/20 flex items-center justify-between">
          <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            Editor
          </span>
          <span className="text-xs text-muted-foreground tabular-nums">
            {wordCount} word{wordCount !== 1 ? "s" : ""}
          </span>
        </div>
        <Textarea
          value={content}
          onChange={(e) => onChange(e.target.value)}
          className="flex-1 min-h-0 resize-none rounded-none border-0 bg-transparent font-mono text-sm leading-relaxed focus-visible:ring-0 focus-visible:ring-offset-0"
          placeholder="# Your blog post title&#10;&#10;Start writing in Markdown..."
        />
      </div>

      {/* Preview pane */}
      <div className="flex flex-col overflow-hidden">
        <div className="px-4 py-2 border-b border-border bg-secondary/20">
          <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            Preview
          </span>
        </div>
        <div
          className="flex-1 overflow-y-auto px-6 py-4 prose-blog text-sm"
          // eslint-disable-next-line react/no-danger
          dangerouslySetInnerHTML={{ __html: renderMarkdown(content) }}
        />
      </div>
    </div>
  );
}
