import type { PortalLineupCampaign, PortalLineupChannel } from "@/lib/portal/server";

/**
 * Wording shared by the line-up list and the campaign detail, so a campaign
 * never describes itself two different ways depending on which page you are on.
 */

const dateTimeFormat = new Intl.DateTimeFormat("it-IT", {
  dateStyle: "medium",
  timeStyle: "short",
});

const dateFormat = new Intl.DateTimeFormat("it-IT", { dateStyle: "medium" });

export function formatDateTime(value: string | null | undefined): string {
  return value ? dateTimeFormat.format(new Date(value)) : "—";
}

export function formatDate(value: string | null | undefined): string {
  return value ? dateFormat.format(new Date(value)) : "—";
}

/** Whole days left, rounded up - "meno di un giorno" is still a day to act in. */
export function daysUntil(value: string | null): number | null {
  if (!value) return null;
  const ms = new Date(value).getTime() - Date.now();
  if (Number.isNaN(ms)) return null;
  return Math.ceil(ms / 86_400_000);
}

export type LineupState =
  | "participating"
  | "declined"
  | "removed"
  | "available"
  | "closed"
  | "no_channels";

/**
 * The single question the user is asking when they look at a campaign card:
 * am I in this, and can I still change it?
 *
 * Derived in one place because the answer drives the badge, the button and the
 * explanatory line all at once, and computing it three times is how those three
 * end up disagreeing.
 */
export function lineupState(campaign: PortalLineupCampaign): LineupState {
  if (campaign.included_count > 0) return "participating";
  if (campaign.channels.length === 0) return "no_channels";
  if (campaign.channels.some((c) => c.participation_status === "removed")) return "removed";
  if (campaign.withdrawn_count > 0 && !campaign.window_open) return "declined";
  if (campaign.withdrawn_count > 0) return "declined";
  if (!campaign.window_open) return "closed";
  return "available";
}

export const STATE_LABELS: Record<LineupState, string> = {
  participating: "Partecipi",
  declined: "Non partecipi",
  removed: "Escluso",
  available: "Puoi partecipare",
  closed: "Termine scaduto",
  no_channels: "Nessun canale collegato",
};

/** Channels this user could still add to the campaign. */
export function joinableChannels(campaign: PortalLineupCampaign): PortalLineupChannel[] {
  if (!campaign.window_open) return [];
  return campaign.channels.filter(
    (channel) => channel.participation_status === null || channel.can_rejoin
  );
}

/** Channels currently in the campaign for this user. */
export function activeChannels(campaign: PortalLineupCampaign): PortalLineupChannel[] {
  return campaign.channels.filter((channel) => channel.participation_status === "included");
}
