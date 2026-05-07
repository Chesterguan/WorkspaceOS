'use client';

import { Search, Settings } from 'lucide-react';
import { SURFACES, type SurfaceId } from '@/lib/bench/surfaces';
import { cn } from '@/lib/utils';

interface RailProps {
  active: SurfaceId;
  onSelect: (id: SurfaceId) => void;
  onPaletteOpen: () => void;
  onSettingsOpen: () => void;
}

const ACCENT_CLASS: Record<string, { active: string; inactive: string }> = {
  violet:  { active: 'bg-violet-500/20 text-violet-300 ring-1 ring-violet-500/30',  inactive: 'text-muted-foreground hover:text-foreground hover:bg-muted/40' },
  orange:  { active: 'bg-orange-500/20 text-orange-300 ring-1 ring-orange-500/30',  inactive: 'text-muted-foreground hover:text-foreground hover:bg-muted/40' },
  blue:    { active: 'bg-blue-500/20 text-blue-300 ring-1 ring-blue-500/30',        inactive: 'text-muted-foreground hover:text-foreground hover:bg-muted/40' },
  teal:    { active: 'bg-teal-500/20 text-teal-300 ring-1 ring-teal-500/30',        inactive: 'text-muted-foreground hover:text-foreground hover:bg-muted/40' },
  emerald: { active: 'bg-emerald-500/20 text-emerald-300 ring-1 ring-emerald-500/30', inactive: 'text-muted-foreground hover:text-foreground hover:bg-muted/40' },
};

export function Rail({ active, onSelect, onPaletteOpen, onSettingsOpen }: RailProps) {
  return (
    <nav className="flex h-full flex-col items-center gap-2 py-3" aria-label="Bench surfaces">
      {SURFACES.map((s) => {
        const isActive = s.id === active;
        const klass = ACCENT_CLASS[s.accent] ?? ACCENT_CLASS.blue;
        return (
          <button
            key={s.id}
            type="button"
            title={s.label}
            aria-label={s.label}
            aria-current={isActive ? 'page' : undefined}
            onClick={() => onSelect(s.id)}
            className={cn(
              'h-8 w-8 rounded-md flex items-center justify-center font-semibold text-xs transition',
              isActive ? klass.active : klass.inactive,
            )}
          >
            {s.letter}
          </button>
        );
      })}

      <div className="my-1 h-px w-7 bg-border" />

      <button
        type="button"
        title="Search (⌘K)"
        aria-label="Open command palette"
        onClick={onPaletteOpen}
        className="h-8 w-8 rounded-md flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted/40 transition"
      >
        <Search className="w-4 h-4" />
      </button>

      <div className="flex-1" />

      <button
        type="button"
        title="Settings"
        aria-label="Open settings"
        onClick={onSettingsOpen}
        className="h-8 w-8 rounded-md flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted/40 transition"
      >
        <Settings className="w-4 h-4" />
      </button>
    </nav>
  );
}
