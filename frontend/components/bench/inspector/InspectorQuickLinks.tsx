'use client';

import Link from 'next/link';

interface Props {
  projectId: string;
}

export function InspectorQuickLinks({ projectId }: Props) {
  return (
    <section className="space-y-1">
      <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Quick links</div>
      <ul className="space-y-1 text-foreground">
        <li><Link className="hover:underline" href={`/bench?project=${projectId}&overlay=files`}>Project files</Link></li>
        <li><Link className="hover:underline" href={`/bench?project=${projectId}&overlay=memory`}>Memory entries</Link></li>
        <li><Link className="hover:underline" href={`/projects/${projectId}/sync`}>Sync history</Link></li>
        <li><Link className="hover:underline" href={`/projects/${projectId}/timeline`}>Activity timeline</Link></li>
      </ul>
    </section>
  );
}
