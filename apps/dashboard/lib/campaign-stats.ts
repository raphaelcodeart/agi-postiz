import type { PublicationStatsMap, PublicationStatus } from "@/types/api";

// A publication in one of these statuses hasn't reached its final outcome
// yet - a manual retry (POST /publications/{id}/retry) only flips it to
// "pending" synchronously, the actual publish happens later in a Celery
// task. Shared by the per-campaign stats check below and the single-
// publication detail page, so a one-off refetch right after clicking retry
// doesn't leave either view stuck showing a stale mid-flight state once the
// real outcome (published/failed) lands.
const UNRESOLVED_STATUSES: PublicationStatus[] = ["pending", "queued", "processing", "submitted", "retry_wait"];

export function isUnresolvedPublicationStatus(status: PublicationStatus): boolean {
  return UNRESOLVED_STATUSES.includes(status);
}

export function hasUnresolvedPublications(stats: PublicationStatsMap): boolean {
  return UNRESOLVED_STATUSES.some((status) => stats[status] > 0);
}
