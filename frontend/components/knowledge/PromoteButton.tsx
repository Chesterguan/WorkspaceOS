'use client';

import { useState } from 'react';
import { Bookmark } from 'lucide-react';
import { PromoteModal } from './PromoteModal';
import type { SourceRef } from '@/lib/types';

interface Props {
  source: SourceRef;
  projectId?: string | null;
  defaultExcerpt?: string;
  className?: string;
  title?: string;
}

export function PromoteButton({
  source, projectId, defaultExcerpt, className, title,
}: Props) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        title={title ?? 'Save as knowledge'}
        aria-label="Save as knowledge"
        onClick={() => setOpen(true)}
        className={className ?? 'inline-flex items-center justify-center w-6 h-6 rounded text-muted-foreground hover:text-foreground hover:bg-muted transition'}
      >
        <Bookmark className="w-3.5 h-3.5" />
      </button>
      <PromoteModal
        open={open}
        source={source}
        projectId={projectId}
        defaultExcerpt={defaultExcerpt}
        onClose={() => setOpen(false)}
      />
    </>
  );
}
