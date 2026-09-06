// Raggruppa i conteggi grezzi per-status (StatusCountsSummaryResponse.by_status,
// vedi services/campaigns.ts::getCampaignsSummary / services/publications.ts::
// getPublicationsSummary) in poche card riassuntive - troppi status individuali
// (9 per le campagne, 11 per le pubblicazioni) affollerebbero la fila di
// StatCard sopra la tabella. Un raggruppamento sbagliato non rompe nulla (sono
// solo card informative, non un vincolo di somma), quindi qui si privilegia
// la leggibilità sulla completezza esaustiva di ogni singolo status raro.

function sumStatuses(byStatus: Record<string, number>, statuses: string[]): number {
  return statuses.reduce((sum, s) => sum + (byStatus[s] ?? 0), 0);
}

export interface StatusBucket {
  key: string;
  label: string;
  value: number;
}

export function campaignStatusBuckets(total: number, byStatus: Record<string, number>): StatusBucket[] {
  return [
    { key: "total", label: "Totale campagne", value: total },
    { key: "draft", label: "Bozze", value: sumStatuses(byStatus, ["draft"]) },
    { key: "active", label: "In corso", value: sumStatuses(byStatus, ["preparing", "queued", "running", "paused"]) },
    { key: "completed", label: "Completate", value: sumStatuses(byStatus, ["completed", "partially_completed"]) },
    { key: "failed", label: "Fallite", value: sumStatuses(byStatus, ["failed", "cancelled"]) },
  ];
}

export function publicationStatusBuckets(total: number, byStatus: Record<string, number>): StatusBucket[] {
  return [
    { key: "total", label: "Totale pubblicazioni", value: total },
    { key: "published", label: "Pubblicate", value: sumStatuses(byStatus, ["published"]) },
    {
      key: "active",
      label: "In corso",
      value: sumStatuses(byStatus, ["pending", "queued", "processing", "submitted", "scheduled", "retry_wait"]),
    },
    { key: "failed", label: "Fallite", value: sumStatuses(byStatus, ["failed"]) },
    { key: "cancelled", label: "Annullate", value: sumStatuses(byStatus, ["cancelled", "skipped", "unknown"]) },
  ];
}
