'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { BenchLayout } from '@/components/bench/BenchLayout';
import { Rail } from '@/components/bench/Rail';
import type { SurfaceId } from '@/lib/bench/surfaces';

export default function BenchPage() {
  const router = useRouter();
  const [active, setActive] = useState<SurfaceId>('r');

  return (
    <BenchLayout
      rail={
        <Rail
          active={active}
          onSelect={setActive}
          onPaletteOpen={() => { /* Task 11 */ }}
          onSettingsOpen={() => router.push('/settings')}
        />
      }
      inspector={null}
      main={
        <div className="p-6 text-sm text-muted-foreground">
          Active surface: <span className="text-foreground font-medium">{active}</span>
        </div>
      }
      log={
        <div className="p-2 text-xs text-muted-foreground font-mono">events</div>
      }
    />
  );
}
