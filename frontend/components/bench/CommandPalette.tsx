'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useProjects } from '@/lib/hooks/useProjects';
import { useKnowledgeNodes } from '@/lib/hooks/useKnowledge';
import {
  useSlashCommands,
  useCapabilityDispatcher,
} from '@/lib/capabilities';

interface PaletteItem {
  id: string;
  label: string;
  hint?: string;
  group: 'surfaces' | 'projects' | 'actions' | 'knowledge' | 'commands';
  run: () => void;
}

interface Props {
  open: boolean;
  onClose: () => void;
  onProjectSelect: (id: string | undefined) => void;
  onOverlayOpen: (id: 'files' | 'memory' | 'portfolio') => void;
  onNewProject: () => void;
}

export function CommandPalette({
  open, onClose, onProjectSelect, onOverlayOpen, onNewProject,
}: Props) {
  const router = useRouter();
  const [query, setQuery] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  const { data: projects = [] } = useProjects();
  const { data: nodes = [] } = useKnowledgeNodes({ limit: 50 });
  const { data: slashCommands = [] } = useSlashCommands();
  const dispatch = useCapabilityDispatcher();

  useEffect(() => {
    if (open) {
      setQuery('');
      // Focus the input when the palette opens
      setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [open, onClose]);

  if (!open) return null;

  const q = query.toLowerCase().trim();

  const items: PaletteItem[] = [
    // Off-rail surfaces
    { id: 'files',     label: 'Files',     hint: 'cross-project ingest', group: 'surfaces',
      run: () => { onOverlayOpen('files'); onClose(); } },
    { id: 'memory',    label: 'Memory',    hint: 'raw evidence',         group: 'surfaces',
      run: () => { onOverlayOpen('memory'); onClose(); } },
    { id: 'portfolio', label: 'Portfolio', hint: 'multi-project view',   group: 'surfaces',
      run: () => { onOverlayOpen('portfolio'); onClose(); } },
    { id: 'settings',  label: 'Settings',  hint: 'api keys, backups',    group: 'surfaces',
      run: () => { router.push('/settings'); onClose(); } },

    // Quick actions
    { id: 'new-project', label: 'New project', hint: 'create', group: 'actions',
      run: () => { onNewProject(); onClose(); } },

    // Dynamic slash_command capabilities from loaded extensions
    ...slashCommands.map((cmd) => ({
      id: `cmd-${cmd.id}`,
      label: cmd.label,
      hint: cmd.source_extension,
      group: 'commands' as const,
      run: async () => {
        onClose();
        await dispatch(
          cmd.handler_kind,
          cmd.handler_target,
          (path) => router.push(path),
        );
      },
    })),

    // Projects
    ...projects.map((p) => ({
      id: `project-${p.id}`, label: p.name, hint: 'switch filter', group: 'projects' as const,
      run: () => { onProjectSelect(p.id); onClose(); },
    })),

    // Knowledge nodes
    ...nodes.slice(0, 20).map((n) => ({
      id: `node-${n.id}`, label: n.title, hint: n.node_type, group: 'knowledge' as const,
      run: () => { /* could open node detail; for v1, just close */ onClose(); },
    })),
  ];

  const filtered = q
    ? items.filter((i) => i.label.toLowerCase().includes(q) || (i.hint?.toLowerCase().includes(q) ?? false))
    : items.slice(0, 30);

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 pt-24 animate-in fade-in-0 duration-150"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="w-[560px] max-w-[90vw] rounded-lg border border-border bg-card shadow-xl animate-in zoom-in-95 fade-in-0 duration-150"
        onClick={(e) => e.stopPropagation()}
      >
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search surfaces, projects, knowledge…"
          className="w-full bg-transparent px-4 py-3 text-sm text-foreground outline-none border-b border-border/60"
        />
        <ul className="max-h-[420px] overflow-y-auto p-1 text-sm">
          {filtered.length === 0 ? (
            <li className="px-3 py-4 text-center text-xs text-muted-foreground">No results</li>
          ) : (
            filtered.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={item.run}
                  className="flex w-full items-center justify-between rounded px-3 py-2 text-left hover:bg-muted/40"
                >
                  <span className="text-foreground">{item.label}</span>
                  <span className="text-xs text-muted-foreground">{item.hint}</span>
                </button>
              </li>
            ))
          )}
        </ul>
      </div>
    </div>
  );
}
