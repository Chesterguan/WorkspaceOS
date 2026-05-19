'use client';

import { useState } from 'react';
import type { SlashCommandInput } from '@/lib/capabilities';

interface Props {
  title: string;
  inputs: SlashCommandInput[];
  onSubmit: (values: Record<string, unknown>) => void;
  onClose: () => void;
}

export function CapabilityInputDialog({ title, inputs, onSubmit, onClose }: Props) {
  const [values, setValues] = useState<Record<string, string>>({});

  const missingRequired = inputs.some(
    (f) => f.required && !(values[f.name] || '').trim(),
  );

  const set = (name: string, v: string) =>
    setValues((prev) => ({ ...prev, [name]: v }));

  const submit = () => {
    const payload: Record<string, unknown> = {};
    for (const f of inputs) {
      const raw = (values[f.name] || '').trim();
      if (!raw) continue;
      payload[f.name] = f.type === 'number' ? Number(raw) : raw;
    }
    onSubmit(payload);
  };

  return (
    <div
      className="fixed inset-0 z-[60] flex items-start justify-center bg-black/40 pt-24"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="w-[560px] max-w-[90vw] rounded-lg border border-border bg-card p-4 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="mb-3 text-sm font-medium text-foreground">{title}</h2>
        <div className="space-y-3">
          {inputs.map((f) => (
            <label key={f.name} className="block text-xs text-muted-foreground">
              {f.label}{f.required ? ' *' : ''}
              {f.type === 'textarea' ? (
                <textarea
                  className="mt-1 w-full rounded border border-border/60 bg-transparent px-2 py-1.5 text-sm text-foreground outline-none"
                  rows={3}
                  placeholder={f.placeholder}
                  value={values[f.name] || ''}
                  onChange={(e) => set(f.name, e.target.value)}
                />
              ) : (
                <input
                  type={f.type === 'number' ? 'number' : 'text'}
                  className="mt-1 w-full rounded border border-border/60 bg-transparent px-2 py-1.5 text-sm text-foreground outline-none"
                  placeholder={f.placeholder}
                  value={values[f.name] || ''}
                  onChange={(e) => set(f.name, e.target.value)}
                />
              )}
            </label>
          ))}
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <button
            className="rounded px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground"
            onClick={onClose}
          >
            Cancel
          </button>
          <button
            className="rounded bg-primary px-3 py-1.5 text-xs text-primary-foreground disabled:opacity-50"
            disabled={missingRequired}
            onClick={submit}
          >
            Run
          </button>
        </div>
      </div>
    </div>
  );
}
