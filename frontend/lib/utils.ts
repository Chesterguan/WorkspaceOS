import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Returns a human-readable relative time string (e.g. "3 hours ago").
 * Uses Intl.RelativeTimeFormat for locale-aware output.
 */
export function formatDistanceToNow(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSecs = Math.floor(diffMs / 1000);

  if (diffSecs < 60) return "just now";

  const diffMins = Math.floor(diffSecs / 60);
  if (diffMins < 60) return `${diffMins}m ago`;

  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;

  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 30) return `${diffDays}d ago`;

  const diffMonths = Math.floor(diffDays / 30);
  if (diffMonths < 12) return `${diffMonths}mo ago`;

  const diffYears = Math.floor(diffMonths / 12);
  return `${diffYears}y ago`;
}

/**
 * Formats a date string as a human-readable local date/time.
 */
export function formatDate(dateString: string): string {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(dateString));
}

/**
 * Generates a URL-safe slug from a string.
 */
export function slugify(str: string): string {
  return str
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-");
}

/**
 * Returns character limit for a given platform.
 */
export function platformCharLimit(platform: string): number | null {
  const limits: Record<string, number> = {
    twitter: 280,
    linkedin: 3000,
    xiaohongshu: 1000,
  };
  return limits[platform] ?? null;
}

/**
 * Safe localStorage wrappers — return gracefully when storage is unavailable
 * (e.g. SSR, private browsing quota exceeded, or SecurityError in iframes).
 */
export function safeGetItem(key: string): string | null {
  try { return localStorage.getItem(key); } catch { return null; }
}

export function safeSetItem(key: string, value: string): void {
  try { localStorage.setItem(key, value); } catch { /* storage unavailable */ }
}

export function safeRemoveItem(key: string): void {
  try { localStorage.removeItem(key); } catch { /* storage unavailable */ }
}

/**
 * Group consecutive assistant messages by roundtable_group for rendering.
 */
export function groupMessages<T extends { role: string; metadata_?: Record<string, unknown> | null }>(
  msgs: T[],
): Array<{ type: "single"; message: T } | { type: "roundtable"; messages: T[]; group: string }> {
  const groups: Array<{ type: "single"; message: T } | { type: "roundtable"; messages: T[]; group: string }> = [];
  let i = 0;
  while (i < msgs.length) {
    const msg = msgs[i];
    const group = msg.metadata_?.roundtable_group as string | undefined;

    if (msg.role === "assistant" && group) {
      const roundtableMessages: T[] = [msg];
      while (
        i + 1 < msgs.length &&
        msgs[i + 1].metadata_?.roundtable_group === group
      ) {
        i++;
        roundtableMessages.push(msgs[i]);
      }
      if (roundtableMessages.length > 1) {
        groups.push({ type: "roundtable", messages: roundtableMessages, group });
      } else {
        groups.push({ type: "single", message: msg });
      }
    } else {
      groups.push({ type: "single", message: msg });
    }
    i++;
  }
  return groups;
}
