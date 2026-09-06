import { Progress } from "@/components/ui/progress";
import type { PublicationStatsMap } from "@/types/api";

interface CampaignProgressProps {
  progressPercentage: number;
  stats: PublicationStatsMap;
}

// "Riuscite" merges published + scheduled: both mean Buffer accepted the post
// successfully, immediate vs scheduled is just a timing detail, not a different
// outcome.
const SEGMENTS: { key: string; label: string; className: string; value: (stats: PublicationStatsMap) => number }[] = [
  { key: "success", label: "Riuscite", className: "text-success", value: (s) => s.published + s.scheduled },
  { key: "failed", label: "Fallite", className: "text-destructive", value: (s) => s.failed },
  { key: "retry_wait", label: "In retry", className: "text-warning", value: (s) => s.retry_wait },
  { key: "pending", label: "In attesa", className: "text-muted-foreground", value: (s) => s.pending },
];

export function CampaignProgress({ progressPercentage, stats }: CampaignProgressProps) {
  const total = Object.values(stats).reduce((sum, value) => sum + value, 0);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium text-foreground">Avanzamento</span>
        <span className="tabular-nums text-muted-foreground">{progressPercentage.toFixed(1)}%</span>
      </div>
      <Progress value={progressPercentage} />
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {SEGMENTS.map((segment) => (
          <div key={segment.key} className="space-y-0.5">
            <p className={`text-lg font-semibold tabular-nums ${segment.className}`}>
              {segment.value(stats)}
            </p>
            <p className="text-xs text-muted-foreground">{segment.label}</p>
          </div>
        ))}
      </div>
      <p className="text-xs text-muted-foreground">{total} destinazioni totali</p>
    </div>
  );
}
