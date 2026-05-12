'use client';

import { Search, Settings } from 'lucide-react';
import { useDomainConfig } from '@/lib/bench/useDomainConfig';
import { getAccentClasses } from '@/lib/bench/accent-classes';
import { cn } from '@/lib/utils';
import type { SurfaceId } from '@/lib/bench/surfaces';

interface RailProps {
  active: SurfaceId | undefined;
  onSelect: (id: SurfaceId) => void;
  onPaletteOpen: () => void;
  onSettingsOpen: () => void;
}

export function Rail({ active, onSelect, onPaletteOpen, onSettingsOpen }: RailProps) {
  const { data } = useDomainConfig();
  const surfaces = data?.surfaces ?? [];

  return (
    <nav className="flex h-full flex-col items-center gap-2 py-3" aria-label="Bench surfaces">
      {surfaces.map((s) => {
        const isActive = s.id === active;
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
              getAccentClasses(s.accent, isActive),
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
