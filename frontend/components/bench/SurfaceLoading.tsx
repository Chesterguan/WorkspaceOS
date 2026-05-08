interface Props {
  rows?: number;
}

export function SurfaceLoading({ rows = 3 }: Props) {
  return (
    <div className="space-y-2 p-6">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-12 rounded-md bg-muted/30 animate-pulse" />
      ))}
    </div>
  );
}
