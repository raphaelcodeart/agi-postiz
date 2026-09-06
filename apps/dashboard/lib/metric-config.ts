import type { LucideIcon } from "lucide-react";
import { HeartIcon, EyeIcon, UserPlusIcon, MousePointerClickIcon, PercentIcon, BarChart3Icon } from "lucide-react";
import type { StatMetricTotals } from "@/types/api";

// Each metric type is shown as its own tile (never summed across different
// types like views+impressions+reach - those measure different things and
// blending them would misrepresent what Buffer actually reported). Ordered so
// the ones the admin cares about most (reactions, views, new follows) lead.
export const METRIC_TILE_CONFIG: { type: string; label: string; shortLabel: string; icon: LucideIcon }[] = [
  { type: "reactions", label: "Mi piace / Reazioni", shortLabel: "Mi piace", icon: HeartIcon },
  { type: "likes", label: "Mi piace (Facebook)", shortLabel: "Like FB", icon: HeartIcon },
  { type: "views", label: "Visualizzazioni", shortLabel: "Views", icon: EyeIcon },
  { type: "impressions", label: "Impression", shortLabel: "Impression", icon: EyeIcon },
  { type: "reach", label: "Copertura (persone raggiunte)", shortLabel: "Copertura", icon: EyeIcon },
  { type: "follows", label: "Nuovi iscritti", shortLabel: "Iscritti", icon: UserPlusIcon },
  { type: "clicks", label: "Clic", shortLabel: "Clic", icon: MousePointerClickIcon },
  { type: "engagementRate", label: "Tasso di coinvolgimento (Buffer)", shortLabel: "Coinvolgimento", icon: PercentIcon },
  { type: "comments", label: "Commenti", shortLabel: "Commenti", icon: BarChart3Icon },
  { type: "shares", label: "Condivisioni", shortLabel: "Condivisioni", icon: BarChart3Icon },
];

// StatMetricTotals (modulo Statistiche, dati persistiti) usa colonne snake_case
// - stessi tipi di METRIC_TILE_CONFIG tranne engagementRate -> engagement_rate.
const TYPE_TO_STAT_COLUMN: Record<string, keyof StatMetricTotals> = {
  reactions: "reactions",
  likes: "likes",
  views: "views",
  impressions: "impressions",
  reach: "reach",
  follows: "follows",
  clicks: "clicks",
  engagementRate: "engagement_rate",
  comments: "comments",
  shares: "shares",
};

/** Le tile da mostrare per un totale persistito, nello stesso ordine/stile di
 * METRIC_TILE_CONFIG - omette i tipi mai riportati (null) invece di un fuorviante 0. */
export function statMetricTiles(
  totals: StatMetricTotals
): { type: string; label: string; shortLabel: string; icon: LucideIcon; value: number }[] {
  return METRIC_TILE_CONFIG.flatMap((config) => {
    const column = TYPE_TO_STAT_COLUMN[config.type];
    const value = column ? totals[column] : undefined;
    return value === null || value === undefined ? [] : [{ ...config, value }];
  });
}

// Le 4 metriche mostrate come mini-tile accanto a ogni riga di un elenco
// (classifica promoter in statistics/page.tsx, canali in
// statistics/users/[id]/page.tsx) - cosi' i totali sono visibili senza dover
// aprire il dettaglio. Stesso principio di statMetricTiles ma per un
// sottoinsieme fisso invece di "tutte le metriche disponibili per questo post".
export const ROW_SUMMARY_METRIC_KEYS: (keyof StatMetricTotals)[] = ["views", "reactions", "comments", "shares"];

export function shortLabelForMetric(type: string): string {
  return METRIC_TILE_CONFIG.find((c) => c.type === type)?.shortLabel ?? type;
}
