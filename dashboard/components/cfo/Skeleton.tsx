export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div
      className={`animate-pulse rounded bg-zinc-200/70 ${className}`}
      aria-hidden
    />
  );
}

export function PanelSkeleton({ lines = 3, chart = false }: { lines?: number; chart?: boolean }) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-5">
      <Skeleton className="mb-3 h-4 w-40" />
      {chart && <Skeleton className="mb-4 h-40 w-full" />}
      <div className="space-y-2">
        {Array.from({ length: lines }).map((_, i) => (
          <Skeleton key={i} className="h-3 w-full" />
        ))}
      </div>
    </div>
  );
}

export function ErrorNote({ error, onRetry }: { error: string; onRetry?: () => void }) {
  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-xs text-amber-800">
      <p>{error}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-2 rounded bg-amber-600 px-3 py-1 font-medium text-white"
        >
          Retry
        </button>
      )}
    </div>
  );
}
