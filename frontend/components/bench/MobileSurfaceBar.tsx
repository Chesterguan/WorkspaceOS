'use client';

import { Search } from 'lucide-react';
import { SURFACES, type SurfaceId } from '@/lib/bench/surfaces';
import { cn } from '@/lib/utils';

interface Props {
  active: SurfaceId;
  onSelect: (id: SurfaceId) => void;
  onPaletteOpen: () => void;
}

const ACCENT: Record<string, string> = {
  violet:  'bg-violet-500/20 text-violet-300',
  orange:  'bg-orange-500/20 text-orange-300',
  blue:    'bg-blue-500/20 text-blue-300',
  teal:    'bg-teal-500/20 text-teal-300',
  emerald: 'bg-emerald-500/20 text-emerald-300',
};

export function MobileSurfaceBar({ active, onSelect, onPaletteOpen }: Props) {
  return (
    <nav className="flex items-stretch divide-x divide-border/60" aria-label="Surfaces">
      {SURFACES.map((s) => {
        const isActive = s.id === active;
        return (
          <button
            key={s.id}
            type="button"
            onClick={() => onSelect(s.id)}
            aria-current={isActive ? 'page' : undefined}
            className={cn(
              'flex-1 py-2 text-[11px] font-medium text-center',
              isActive ? ACCENT[s.accent] : 'text-muted-foreground hover:bg-muted/30',
            )}
          >
            {s.label}
          </button>
        );
      })}
      <button
        type="button"
        onClick={onPaletteOpen}
        aria-label="Open command palette"
        className="px-3 py-2 text-muted-foreground hover:bg-muted/30"
      >
        <Search className="h-4 w-4" />
      </button>
    </nav>
  );
}
