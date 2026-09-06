import { PlatformBadge } from "@/components/shared/platform-badge";

interface PlatformDistributionChartProps {
  distribution: Record<string, number>;
}

export function PlatformDistributionChart({ distribution }: PlatformDistributionChartProps) {
  const entries = Object.entries(distribution).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...entries.map(([, count]) => count));

  if (entries.length === 0) {
    return <p className="text-sm text-muted-foreground">Nessun canale di destinazione trovato.</p>;
  }

  return (
    <div className="space-y-2.5">
      {entries.map(([platform, count]) => (
        <div key={platform} className="flex items-center gap-3">
          <PlatformBadge platform={platform} className="w-28 shrink-0 justify-start" />
          <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-brand-gradient transition-[width] duration-500 ease-out"
              style={{ width: `${Math.max(4, (count / max) * 100)}%` }}
            />
          </div>
          <span className="w-8 shrink-0 text-right text-sm tabular-nums text-muted-foreground">
            {count}
          </span>
        </div>
      ))}
    </div>
  );
}
