// Static map so Tailwind purge keeps these class strings — dynamic class
// names like `bg-${accent}-500/20` get dropped by the JIT pass and the
// rail icons end up unstyled. Maps the accent name (from scribe.yaml) to
// the on/off classes used for the rail buttons.
export const ACCENT_CLASSES: Record<string, { active: string; inactive: string }> = {
  violet: {
    active: 'bg-violet-500/20 text-violet-300 ring-1 ring-violet-500/30',
    inactive: 'text-muted-foreground hover:text-foreground hover:bg-muted/40',
  },
  orange: {
    active: 'bg-orange-500/20 text-orange-300 ring-1 ring-orange-500/30',
    inactive: 'text-muted-foreground hover:text-foreground hover:bg-muted/40',
  },
  blue: {
    active: 'bg-blue-500/20 text-blue-300 ring-1 ring-blue-500/30',
    inactive: 'text-muted-foreground hover:text-foreground hover:bg-muted/40',
  },
  teal: {
    active: 'bg-teal-500/20 text-teal-300 ring-1 ring-teal-500/30',
    inactive: 'text-muted-foreground hover:text-foreground hover:bg-muted/40',
  },
  emerald: {
    active: 'bg-emerald-500/20 text-emerald-300 ring-1 ring-emerald-500/30',
    inactive: 'text-muted-foreground hover:text-foreground hover:bg-muted/40',
  },
};

export function getAccentClasses(accent: string, active: boolean): string {
  const klass = ACCENT_CLASSES[accent] ?? ACCENT_CLASSES.blue;
  return active ? klass.active : klass.inactive;
}
