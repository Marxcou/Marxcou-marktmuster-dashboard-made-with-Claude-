// Platzhalter beim Laden: zeigt die Form der kommenden Inhalte, ohne Werte vorzutäuschen (Grundregel 6).
export function Skeleton({ className = "h-4 w-full" }: { className?: string }) {
  return <div className={`skeleton ${className}`} aria-hidden="true" />;
}

export function CardSkeleton() {
  return (
    <div className="card space-y-3" role="status" aria-label="Lade Inhalte …">
      <Skeleton className="h-5 w-1/3" />
      <Skeleton className="h-4 w-2/3" />
      <Skeleton className="h-8 w-1/2" />
      <Skeleton className="h-4 w-full" />
    </div>
  );
}
