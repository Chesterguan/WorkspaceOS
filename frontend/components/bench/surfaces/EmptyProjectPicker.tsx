'use client';

import { ArrowUpRight } from 'lucide-react';

interface Props {
  surfaceLabel: string;
  hint?: string;
}

export function EmptyProjectPicker({ surfaceLabel, hint }: Props) {
  return (
    <div className="flex flex-1 items-center justify-center p-12 text-center">
      <div className="max-w-md space-y-3">
        <div className="text-base text-foreground">Pick a project to see {surfaceLabel.toLowerCase()}.</div>
        <p className="text-xs text-muted-foreground">
          {hint ?? `${surfaceLabel} are project-scoped today. Use the project filter in the top right.`}
        </p>
        <ArrowUpRight className="mx-auto h-5 w-5 text-muted-foreground/60" />
      </div>
    </div>
  );
}
