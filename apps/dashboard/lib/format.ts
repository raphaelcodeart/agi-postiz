export function formatDateTime(iso: string | null | undefined, timeZone?: string): string {
  if (!iso) return "—";
  try {
    return new Intl.DateTimeFormat("it-IT", {
      dateStyle: "medium",
      timeStyle: "short",
      timeZone,
    }).format(new Date(iso));
  } catch {
    return new Date(iso).toLocaleString("it-IT");
  }
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return "—";
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const exponent = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  const value = bytes / 1024 ** exponent;
  return `${value.toFixed(exponent === 0 ? 0 : 1)} ${units[exponent]}`;
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  const totalSeconds = Math.round(seconds);
  const minutes = Math.floor(totalSeconds / 60);
  const remaining = totalSeconds % 60;
  return `${minutes}:${remaining.toString().padStart(2, "0")}`;
}

export function formatPercentage(value: number): string {
  return `${value.toFixed(1)}%`;
}

// Only engagementRate is a 0-100 rate (developers.buffer.com/types/PostMetricUnit.html);
// every other Buffer post metric type is a plain count.
const PERCENTAGE_METRIC_TYPES = new Set(["engagementRate"]);

export function formatMetricValue(type: string, value: number): string {
  if (PERCENTAGE_METRIC_TYPES.has(type)) return `${value.toLocaleString("it-IT", { maximumFractionDigits: 1 })}%`;
  return Math.round(value).toLocaleString("it-IT");
}

/**
 * The users/campaigns/publications list endpoints cap `limit` at 100 and expose no
 * total-count. When a query returns exactly the cap, the real total may be higher,
 * so this renders "100+" instead of a falsely precise number.
 */
export function formatCappedCount(count: number | undefined, cap = 100): string {
  if (count === undefined) return "—";
  return count === cap ? `${cap}+` : String(count);
}
