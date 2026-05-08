'use client';

import { useState, useEffect } from 'react';
import { projects as projectsApi } from '@/lib/api';
import { toast } from 'sonner';
import { mutate as globalMutate } from 'swr';

interface Props {
  open: boolean;
  onClose: () => void;
  onCreated: (projectId: string) => void;
}

/** Convert a display name to a URL-safe slug. */
function toSlug(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

export function NewProjectModal({ open, onClose, onCreated }: Props) {
  const [name, setName] = useState('');
  const [repo, setRepo] = useState('');
  const [busy, setBusy] = useState(false);

  // Reset fields each time the modal opens.
  useEffect(() => {
    if (open) {
      setName('');
      setRepo('');
    }
  }, [open]);

  // Escape key closes the modal.
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [open, onClose]);

  if (!open) return null;

  const submit = async () => {
    if (!name.trim()) return;
    setBusy(true);
    try {
      const project = await projectsApi.create({
        name: name.trim(),
        // slug is required by ProjectCreate — derive it from the name.
        slug: toSlug(name),
        github_repo: repo.trim() || undefined,
      });
      // Invalidate the SWR '/projects' cache so ProjectFilter picks up the new entry.
      await globalMutate('/projects');
      toast.success(`Created ${project.name}`);
      onCreated(project.id);
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Create failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 animate-in fade-in-0 duration-150"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="w-[440px] max-w-[90vw] rounded-lg border border-border bg-card p-5 shadow-xl space-y-4 animate-in zoom-in-95 fade-in-0 duration-150"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-base font-semibold">New project</h2>

        <label className="block">
          <div className="mb-1 text-xs font-medium text-muted-foreground">Name</div>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') submit(); }}
            autoFocus
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
          />
        </label>

        <label className="block">
          <div className="mb-1 text-xs font-medium text-muted-foreground">GitHub repo (optional)</div>
          <input
            value={repo}
            onChange={(e) => setRepo(e.target.value)}
            placeholder="owner/repo"
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
          />
        </label>

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-border px-3 py-1.5 text-xs hover:bg-muted/40"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={busy || !name.trim()}
            className="rounded-md bg-primary px-3 py-1.5 text-xs text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {busy ? 'Creating…' : 'Create'}
          </button>
        </div>
      </div>
    </div>
  );
}
