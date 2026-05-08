'use client';

import { useState, useEffect } from 'react';
import { useNarrative } from '@/lib/hooks/useNarrative';
import { narratives as narrativesApi } from '@/lib/api';
import { toast } from 'sonner';

interface Props {
  projectId: string;
}

export function InspectorNarrative({ projectId }: Props) {
  const { data: narrative, mutate } = useNarrative(projectId);
  const [oneLiner, setOneLiner] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    // Sync local edit state ONLY when the project changes. We deliberately
    // omit narrative.one_liner from the deps so background SWR revalidations
    // don't clobber in-flight user edits. After save, mutate() updates the
    // cached narrative; next time the user opens this project the textarea
    // will pick up the new value.
    setOneLiner(narrative?.one_liner ?? '');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  const save = async () => {
    setBusy(true);
    try {
      await narrativesApi.update(projectId, { one_liner: oneLiner });
      mutate();
      toast.success('Narrative saved');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Save failed');
    } finally {
      setBusy(false);
    }
  };

  const dirty = oneLiner !== (narrative?.one_liner ?? '');

  return (
    <section className="space-y-2">
      <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">One-liner</div>
      <textarea
        value={oneLiner}
        onChange={(e) => setOneLiner(e.target.value)}
        rows={2}
        className="w-full resize-none rounded-md border border-border bg-card/40 p-2 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary/40"
      />
      <button
        type="button"
        disabled={busy || !dirty}
        onClick={save}
        className="rounded-md bg-primary/80 px-2.5 py-1 text-[11px] text-primary-foreground hover:bg-primary disabled:opacity-50"
      >
        {busy ? 'Saving…' : 'Save'}
      </button>
    </section>
  );
}
