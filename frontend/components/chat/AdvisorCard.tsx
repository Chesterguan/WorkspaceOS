'use client';

import { cn } from '@/lib/utils';
import { PersonaAvatar } from '@/components/personas/PersonaAvatar';
import type { PersonaInfo } from '@/lib/personas';

interface AdvisorCardProps {
  advisor: PersonaInfo;
  size: 'sm' | 'lg';
  selected?: boolean;
  onClick?: () => void;
}

// Renders a roundtable advisor card. The persona source (legacy hardcoded
// vs. wizard-generated) doesn't matter here — PersonaInfo is the
// normalized shape and PersonaAvatar handles missing images.
export function AdvisorCard({ advisor, size, selected, onClick }: AdvisorCardProps) {
  if (size === 'sm') {
    return (
      <div className="flex items-center gap-2">
        <div
          className="shrink-0 rounded-full border-2"
          style={{ borderColor: advisor.color }}
        >
          <PersonaAvatar
            name={advisor.name}
            color={advisor.color}
            avatar={advisor.avatar}
            size={28}
          />
        </div>
        <div className="min-w-0">
          <p className="text-xs font-semibold truncate" style={{ color: advisor.color }}>
            {advisor.name}
          </p>
          {advisor.tagline && (
            <p className="text-[10px] text-muted-foreground truncate">{advisor.tagline}</p>
          )}
        </div>
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'flex flex-col items-center gap-1.5 px-3 py-2.5 rounded-lg border transition-all text-center shrink-0',
        'hover:bg-secondary/50',
        selected ? 'border-2 bg-secondary/30' : 'border-border',
      )}
      style={selected ? { borderColor: advisor.color } : undefined}
    >
      <div className="rounded-full border-2" style={{ borderColor: advisor.color }}>
        <PersonaAvatar
          name={advisor.name}
          color={advisor.color}
          avatar={advisor.avatar}
          size={48}
        />
      </div>
      <p className="text-xs font-semibold truncate max-w-[80px]">{advisor.name}</p>
      {advisor.tagline && (
        <p className="text-[9px] text-muted-foreground truncate max-w-[80px]">
          {advisor.tagline}
        </p>
      )}
    </button>
  );
}
