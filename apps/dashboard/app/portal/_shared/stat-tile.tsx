import type { StatMetricTotals } from "@/types/api";
import { METRIC_TILE_CONFIG } from "@/lib/metric-config";

/**
 * La tile numerica del portale promoter, e i formati dei numeri che ci stanno
 * dentro.
 *
 * Era definita dentro la home (app/portal/(app)/page.tsx) finche' la home era
 * l'unico posto con dei numeri sopra; ora la sezione Statistiche mostra le
 * stesse cifre con lo stesso aspetto, quindi vive qui - una tile che cambia
 * stile in una pagina sola e non nell'altra e' il modo in cui due schermate
 * dello stesso prodotto smettono di sembrare lo stesso prodotto.
 *
 * Volutamente distinta dalla StatCard della dashboard amministrativa
 * (components/shared/stat-card.tsx): il portale indossa il design system della
 * landing pubblica, non quello dell'admin (vedi .portal-skin in globals.css).
 */

const numberFormat = new Intl.NumberFormat("it-IT");
const compactFormat = new Intl.NumberFormat("it-IT", { notation: "compact", maximumFractionDigits: 1 });

/** Forma compatta solo da 10.000 in su: sotto quella soglia "9.812" si legge
 *  meglio di "9,8 mila" ed e' anche piu' preciso. */
export function formatCompact(value: number): string {
  return value >= 10_000 ? compactFormat.format(value) : numberFormat.format(value);
}

export function formatExact(value: number): string {
  return numberFormat.format(value);
}

/** Il tasso di coinvolgimento e' l'unica metrica in percentuale. */
export function formatPercent(value: number): string {
  return `${value.toLocaleString("it-IT", { maximumFractionDigits: 1 })}%`;
}

// Il tasso di coinvolgimento compare con due nomi a seconda di dove lo si
// prende: "engagementRate" nei tipi di METRIC_TILE_CONFIG, "engagement_rate"
// come colonna di StatMetricTotals. Sono lo stesso valore.
const PERCENT_METRIC_TYPES = new Set(["engagementRate", "engagement_rate"]);

/** Valore di una metrica persistita, formattato secondo il suo tipo. */
export function formatMetricByType(type: string, value: number): string {
  return PERCENT_METRIC_TYPES.has(type) ? formatPercent(value) : formatCompact(value);
}

export function formatMetric(key: keyof StatMetricTotals, value: number): string {
  return formatMetricByType(key, value);
}

/** Etichetta estesa di una metrica, quella di METRIC_TILE_CONFIG (in comune con
 *  le pagine dell'amministratore, cosi' la stessa metrica non ha due nomi a
 *  seconda di chi la guarda). */
export function labelForMetric(key: keyof StatMetricTotals): string {
  const type = key === "engagement_rate" ? "engagementRate" : key;
  return METRIC_TILE_CONFIG.find((c) => c.type === type)?.label ?? key;
}

/**
 * Cifra in evidenza. L'icona ripete il significato della metrica per chi scorre
 * la riga con lo sguardo invece di leggerla.
 */
export function StatTile({
  label,
  value,
  icon: Icon,
  hint,
  tone = "default",
}: {
  label: string;
  value: string;
  icon: React.ComponentType<{ className?: string }>;
  hint?: string;
  tone?: "default" | "accent";
}) {
  return (
    <div
      className={
        "group relative overflow-hidden rounded-xl border bg-card p-4 transition-shadow hover:shadow-md " +
        (tone === "accent" ? "border-primary/30" : "")
      }
    >
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">{label}</p>
        <Icon
          className={
            "size-4 shrink-0 transition-transform group-hover:scale-110 " +
            (tone === "accent" ? "text-primary" : "text-muted-foreground")
          }
        />
      </div>
      <p className="mt-2 text-2xl font-semibold tabular-nums">{value}</p>
      {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}
