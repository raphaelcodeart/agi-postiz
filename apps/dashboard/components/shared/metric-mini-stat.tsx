interface MetricMiniStatProps {
  label: string;
  value: string;
}

/**
 * Etichetta piccola sopra, valore sotto - stesso principio dello StatCard
 * (components/shared/stat-card.tsx) ma senza bordo/padding di una Card intera,
 * pensato per stare dentro una cella di tabella o in fila accanto ad altri
 * (dettaglio canale/utente del modulo Statistiche). Le etichette sono quelle
 * abbreviate di METRIC_TILE_CONFIG (lib/metric-config.ts), non quelle estese
 * usate nelle StatCard in cima alla pagina.
 */
export function MetricMiniStat({ label, value }: MetricMiniStatProps) {
  return (
    <div className="flex min-w-14 flex-col items-center gap-0.5 rounded-md bg-muted/50 px-2 py-1">
      <span className="text-[9px] font-medium uppercase tracking-wide text-muted-foreground">{label}</span>
      <span className="text-xs font-semibold tabular-nums text-foreground">{value}</span>
    </div>
  );
}
