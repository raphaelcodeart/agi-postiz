interface MetricMiniStatProps {
  label: string;
  value: string;
}

/**
 * Etichetta piccola sopra, valore sotto - stesso principio dello StatCard
 * (components/shared/stat-card.tsx) ma piu' compatta di una Card intera,
 * pensata per stare dentro una cella di tabella o in fila accanto ad altre
 * (dettaglio canale/utente del modulo Statistiche). Le etichette sono quelle
 * abbreviate di METRIC_TILE_CONFIG (lib/metric-config.ts), non quelle estese
 * usate nelle StatCard in cima alla pagina.
 *
 * Fondo della card (bianco nel portale) con bordo pieno, non un grigio tenue:
 * su una riga gia' chiara il grigio spariva e il valore non si leggeva.
 */
export function MetricMiniStat({ label, value }: MetricMiniStatProps) {
  return (
    <div className="flex min-w-16 flex-col items-center gap-0.5 rounded-lg border border-border bg-card px-2.5 py-1.5 shadow-xs">
      <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">{label}</span>
      <span className="text-sm font-semibold tabular-nums text-card-foreground">{value}</span>
    </div>
  );
}
