"use client";

import { useMemo, useState } from "react";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { formatMetricValue } from "@/lib/format";
import type { StatMetricTotals, StatTimeseriesPoint } from "@/types/api";

type TrendMetricKey = keyof StatMetricTotals | "post_count";

// Stesso ordine/etichette di METRIC_TILE_CONFIG (lib/metric-config.ts), con in
// testa "Post pubblicati" (l'unica metrica sempre disponibile, anche prima di
// qualunque sincronizzazione Buffer) - vedi statistics_service.timeseries per
// come i bucket vengono calcolati lato backend.
const TREND_METRIC_OPTIONS: { key: TrendMetricKey; label: string; formatType: string }[] = [
  { key: "post_count", label: "Post pubblicati", formatType: "post_count" },
  { key: "reactions", label: "Mi piace / Reazioni", formatType: "reactions" },
  { key: "likes", label: "Mi piace (Facebook)", formatType: "likes" },
  { key: "views", label: "Visualizzazioni", formatType: "views" },
  { key: "impressions", label: "Impression", formatType: "impressions" },
  { key: "reach", label: "Copertura", formatType: "reach" },
  { key: "follows", label: "Nuovi iscritti", formatType: "follows" },
  { key: "clicks", label: "Clic", formatType: "clicks" },
  { key: "comments", label: "Commenti", formatType: "comments" },
  { key: "shares", label: "Condivisioni", formatType: "shares" },
  { key: "engagement_rate", label: "Tasso di coinvolgimento", formatType: "engagementRate" },
];

const MAX_VISIBLE_MONTHS = 12;
const CHART_HEIGHT = 160;

function pointValue(point: StatTimeseriesPoint, key: TrendMetricKey): number | null {
  if (key === "post_count") return point.post_count;
  return point.totals[key] ?? null;
}

// "2026-08" -> "ago '26" ; "2026" -> "2026"
function formatPeriodLabel(period: string): string {
  if (period.length === 4) return period;
  const [year, month] = period.split("-");
  const date = new Date(Number(year), Number(month) - 1, 1);
  const monthLabel = new Intl.DateTimeFormat("it-IT", { month: "short" }).format(date);
  return `${monthLabel} '${year.slice(2)}`;
}

interface MetricTrendChartProps {
  monthly: StatTimeseriesPoint[];
  yearly: StatTimeseriesPoint[];
}

/**
 * Grafico di andamento mensile/annuale, riusato da tutti e 3 i livelli del
 * modulo Statistiche (dashboard, utente, canale) - alimentato da
 * StatDashboardResponse/StatUserDetailResponse/StatChannelDetailResponse
 * .timeseries_monthly/_yearly (bucket calcolati server-side per data di
 * pubblicazione, non di sincronizzazione, vedi statistics_service.timeseries).
 * Una sola metrica alla volta (mai due assi) - il selettore lascia scegliere
 * quale, "Post pubblicati" incluso come pseudo-metrica sempre disponibile.
 */
export function MetricTrendChart({ monthly, yearly }: MetricTrendChartProps) {
  const [granularity, setGranularity] = useState<"month" | "year">("month");
  const [metric, setMetric] = useState<TrendMetricKey>("reactions");

  const points = useMemo(
    () => (granularity === "month" ? monthly.slice(-MAX_VISIBLE_MONTHS) : yearly),
    [granularity, monthly, yearly]
  );
  const option = TREND_METRIC_OPTIONS.find((o) => o.key === metric) ?? TREND_METRIC_OPTIONS[0];
  const values = points.map((p) => pointValue(p, metric));
  const max = Math.max(1, ...values.filter((v): v is number => v !== null));

  if (monthly.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        Nessun post con una data di pubblicazione nota da mostrare in un grafico.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Select value={metric} onValueChange={(value) => setMetric(value as TrendMetricKey)}>
          <SelectTrigger className="w-56">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {TREND_METRIC_OPTIONS.map((o) => (
              <SelectItem key={o.key} value={o.key}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Tabs value={granularity} onValueChange={(value) => setGranularity(value as "month" | "year")}>
          <TabsList>
            <TabsTrigger value="month">Mensile</TabsTrigger>
            <TabsTrigger value="year">Annuale</TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      {points.length === 0 ? (
        <p className="py-8 text-center text-sm text-muted-foreground">
          Nessun dato per questa vista ({granularity === "month" ? "mensile" : "annuale"}).
        </p>
      ) : (
        <>
          <div className="flex gap-2" style={{ height: CHART_HEIGHT }}>
            <div
              className="flex w-10 shrink-0 flex-col justify-between pr-1 text-right text-[10px] tabular-nums text-muted-foreground"
              style={{ height: CHART_HEIGHT }}
            >
              <span>{formatMetricValue(option.formatType, max)}</span>
              <span>{formatMetricValue(option.formatType, max / 2)}</span>
              <span>0</span>
            </div>

            <div className="relative flex-1 border-l border-border">
              <div className="absolute inset-x-0 top-0 border-t border-border/50" />
              <div className="absolute inset-x-0 top-1/2 border-t border-border/50" />
              <div className="absolute inset-x-0 bottom-0 border-t border-border" />

              <div className="absolute inset-0 flex items-end gap-1.5 px-1.5">
                {points.map((point, index) => {
                  const value = values[index];
                  const heightPct = value === null ? 0 : Math.max(value > 0 ? 2 : 0, (value / max) * 100);
                  const isLast = index === points.length - 1;
                  const valueLabel = value === null ? "nessun dato" : formatMetricValue(option.formatType, value);

                  return (
                    <Tooltip key={point.period}>
                      <TooltipTrigger
                        className="group flex h-full flex-1 flex-col items-center justify-end gap-1 rounded-sm outline-none"
                        aria-label={`${formatPeriodLabel(point.period)}: ${valueLabel}, ${point.post_count} post`}
                      >
                        {isLast && value !== null && (
                          <span className="text-[10px] font-medium tabular-nums text-foreground">{valueLabel}</span>
                        )}
                        <div
                          className="w-full max-w-6 rounded-t-[4px] bg-chart-1 transition-opacity duration-150 group-hover:opacity-75 group-focus-visible:opacity-75 group-focus-visible:ring-2 group-focus-visible:ring-ring"
                          style={{ height: `${heightPct}%`, minHeight: value === null ? 0 : 2 }}
                        />
                      </TooltipTrigger>
                      <TooltipContent>
                        <span className="font-medium">{formatPeriodLabel(point.period)}</span>: {valueLabel}
                        {" · "}
                        {point.post_count} post
                      </TooltipContent>
                    </Tooltip>
                  );
                })}
              </div>
            </div>
          </div>

          <div className="flex gap-1.5 pl-12">
            {points.map((point) => (
              <span key={point.period} className="flex-1 truncate text-center text-[10px] text-muted-foreground">
                {formatPeriodLabel(point.period)}
              </span>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
