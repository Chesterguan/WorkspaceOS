'use client';

// In-bench feedback button — opens a modal that POSTs to /api/v1/feedback.
// The backend creates a GitHub issue and returns its URL; we toast the
// link so the user can open and follow it.
//
// Floats bottom-right with a low-profile chip. Hidden when modal is open
// to keep the screenshot clean.

import { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { MessageSquareWarning, X } from 'lucide-react';

const BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:9000/api/v1';

function authHeaders(): Record<string, string> {
  const token =
    typeof window !== 'undefined' ? window.localStorage.getItem('auth_token') : null;
  const apiKey = process.env.NEXT_PUBLIC_API_KEY;
  const h: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) h['Authorization'] = `Bearer ${token}`;
  else if (apiKey) h['X-API-Key'] = apiKey;
  return h;
}

type Kind = 'bug' | 'feature' | 'question';

const KIND_LABELS: Record<Kind, string> = {
  bug: 'Something is broken',
  feature: 'I wish it did this',
  question: "I don't understand something",
};

interface CapturedContext {
  surface: string | null;
  project_id: string | null;
  url: string;
  user_agent: string;
  viewport: { w: number; h: number };
}

function captureContext(): CapturedContext {
  const url = typeof window !== 'undefined' ? window.location.href : '';
  const params = typeof window !== 'undefined'
    ? new URLSearchParams(window.location.search)
    : new URLSearchParams();
  return {
    surface: params.get('surface'),
    project_id: params.get('project'),
    url,
    user_agent: typeof navigator !== 'undefined' ? navigator.userAgent : '',
    viewport: typeof window !== 'undefined'
      ? { w: window.innerWidth, h: window.innerHeight }
      : { w: 0, h: 0 },
  };
}

export function FeedbackButton() {
  const [open, setOpen] = useState(false);

  if (open) {
    return <FeedbackModal onClose={() => setOpen(false)} />;
  }

  return (
    <button
      type="button"
      onClick={() => setOpen(true)}
      title="Send feedback to the maintainers"
      className="fixed bottom-4 right-4 z-40 flex items-center gap-2 rounded-full border border-violet-500/50 bg-violet-500/20 px-3 py-1.5 text-xs font-medium text-violet-100 backdrop-blur hover:bg-violet-500/30 transition-colors shadow-lg"
    >
      <MessageSquareWarning className="w-3.5 h-3.5" />
      Feedback
    </button>
  );
}

function FeedbackModal({ onClose }: { onClose: () => void }) {
  const [kind, setKind] = useState<Kind>('bug');
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [includeEvents, setIncludeEvents] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [showContext, setShowContext] = useState(false);
  const ctx = captureContext();

  async function submit() {
    if (title.trim().length < 3 || body.trim().length < 10) {
      toast.error('Title needs 3+ chars, body needs 10+.');
      return;
    }
    setSubmitting(true);
    try {
      const res = await fetch(`${BASE_URL}/feedback`, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({
          title: title.trim(),
          body: body.trim(),
          kind,
          include_recent_events: includeEvents,
          context: ctx,
        }),
      });
      if (!res.ok) {
        const t = await res.text();
        throw new Error(`HTTP ${res.status}: ${t.slice(0, 200)}`);
      }
      const data = await res.json();
      toast.success(
        `Filed as #${data.issue_number}`,
        {
          description: 'Click to open the issue.',
          action: {
            label: 'Open',
            onClick: () => window.open(data.issue_url, '_blank'),
          },
        },
      );
      onClose();
    } catch (err) {
      toast.error(`Couldn't file: ${(err as Error).message}`);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/40 p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="w-full max-w-lg rounded-lg border border-border bg-card shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border/60 px-4 py-3">
          <div>
            <h2 className="text-sm font-semibold">Send feedback</h2>
            <p className="text-[11px] text-muted-foreground">
              Files a GitHub issue with the current page context.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-4 space-y-3">
          {/* Kind picker */}
          <div className="flex flex-wrap gap-1.5">
            {(Object.keys(KIND_LABELS) as Kind[]).map((k) => (
              <button
                key={k}
                type="button"
                onClick={() => setKind(k)}
                className={`text-[11px] px-2.5 py-1 rounded-md border transition ${
                  kind === k
                    ? 'border-violet-500/60 bg-violet-500/15 text-violet-200'
                    : 'border-border text-muted-foreground hover:bg-muted/40'
                }`}
              >
                {KIND_LABELS[k]}
              </button>
            ))}
          </div>

          <div className="space-y-1">
            <label className="text-[11px] font-medium text-muted-foreground">Title</label>
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={kind === 'bug'
                ? "Brief summary of what's broken"
                : kind === 'feature'
                  ? "Brief summary of what you wish it did"
                  : "Your question in one line"}
              className="bg-card/40 border-border/60 h-9 text-sm"
              maxLength={140}
            />
          </div>

          <div className="space-y-1">
            <label className="text-[11px] font-medium text-muted-foreground">Details</label>
            <Textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder="What happened, what you expected, anything else useful. Markdown OK."
              rows={5}
              className="bg-card/40 border-border/60 text-sm font-mono"
              maxLength={8000}
            />
          </div>

          {/* Context disclosure */}
          <button
            type="button"
            onClick={() => setShowContext((v) => !v)}
            className="text-[11px] text-muted-foreground hover:text-foreground"
          >
            {showContext ? '↑ Hide auto-context' : '↓ Auto-context that will be attached'}
          </button>
          {showContext && (
            <div className="rounded border border-border/40 bg-card/20 p-2.5 space-y-1 text-[10px] font-mono text-muted-foreground">
              <div>surface: <span className="text-foreground">{ctx.surface ?? '-'}</span></div>
              <div>project: <span className="text-foreground">{ctx.project_id ?? '-'}</span></div>
              <div>url: <span className="text-foreground">{ctx.url}</span></div>
              <div>viewport: <span className="text-foreground">{ctx.viewport.w}×{ctx.viewport.h}</span></div>
              <div>user_agent: <span className="text-foreground line-clamp-1">{ctx.user_agent}</span></div>
            </div>
          )}

          <label className="flex items-center gap-1.5 text-[11px] text-muted-foreground cursor-pointer">
            <input
              type="checkbox"
              checked={includeEvents}
              onChange={(e) => setIncludeEvents(e.target.checked)}
              className="accent-violet-500"
            />
            Include last 10 bench events (helps reproduce)
          </label>
        </div>

        <div className="border-t border-border/60 px-4 py-3 flex items-center justify-between">
          <p className="text-[10px] text-muted-foreground">
            Files publicly to <code>Chesterguan/WorkspaceOS</code>.
          </p>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={onClose} disabled={submitting}>
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={submit}
              disabled={submitting}
              className="bg-violet-500 hover:bg-violet-600"
            >
              {submitting ? 'Filing…' : 'File issue'}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
