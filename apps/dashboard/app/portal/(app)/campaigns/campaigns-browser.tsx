"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { MinusCircleIcon, SearchIcon, XIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { PortalCampaign } from "@/lib/portal/server";

/**
 * Lo storico campagne del promoter, con ricerca e filtri.
 *
 * Filtra in locale e non via API di proposito: `GET /portal/campaigns`
 * restituisce gia' tutte le campagne di questo utente in una volta - sono le
 * sue, non quelle della piattaforma - quindi ogni filtro sarebbe una chiamata
 * di rete per riordinare dati che il browser ha gia'. Scrivere nella casella di
 * ricerca resta cosi' istantaneo anche da telefono con la rete mobile, che e'
 * da dove questa pagina si apre.
 *
 * Schede e non tabella (come la vecchia versione): la tabella a sette colonne
 * si leggeva solo scorrendo di lato su uno schermo stretto.
 */

const STATUS_LABELS: Record<string, string> = {
  draft: "Bozza",
  announced: "In programma",
  preparing: "In preparazione",
  queued: "In coda",
  running: "In corso",
  paused: "In pausa",
  partially_completed: "Completata in parte",
  completed: "Completata",
  failed: "Non riuscita",
  cancelled: "Annullata",
};

/**
 * Quattro gruppi invece dei dieci stati veri. Un promoter non ha motivo di
 * distinguere "in coda" da "in preparazione" - sono dettagli della macchina di
 * pubblicazione - mentre gli interessa moltissimo separare cio' a cui ha
 * partecipato da cio' a cui ha rinunciato.
 */
type Bucket = "all" | "published" | "upcoming" | "declined";

const BUCKETS: { value: Bucket; label: string }[] = [
  { value: "all", label: "Tutte" },
  { value: "upcoming", label: "In programma" },
  { value: "published", label: "Pubblicate" },
  { value: "declined", label: "Non partecipate" },
];

const numberFormat = new Intl.NumberFormat("it-IT");
const dateFormat = new Intl.DateTimeFormat("it-IT", { dateStyle: "medium" });

/**
 * Mai pubblicata su nessun canale di questo promoter - ma il perche' cambia, e
 * la differenza conta per chi legge: "hai scelto di non partecipare" non va mai
 * mostrato a qualcuno che un amministratore ha escluso.
 */
type NonParticipation = "declined" | "removed" | null;

function nonParticipation(campaign: PortalCampaign): NonParticipation {
  if (campaign.participation_included > 0 || campaign.channels_targeted > 0) return null;
  if (campaign.participation_withdrawn > 0) return "declined";
  if (campaign.participation_removed > 0) return "removed";
  return null;
}

function bucketOf(campaign: PortalCampaign): Exclude<Bucket, "all"> {
  if (nonParticipation(campaign) !== null) return "declined";
  if (campaign.status === "announced" || campaign.status === "draft") return "upcoming";
  return "published";
}

export function PortalCampaignsBrowser({ campaigns }: { campaigns: PortalCampaign[] }) {
  const [search, setSearch] = useState("");
  const [bucket, setBucket] = useState<Bucket>("all");
  const [newestFirst, setNewestFirst] = useState(true);

  const counts = useMemo(() => {
    const result: Record<Bucket, number> = { all: campaigns.length, published: 0, upcoming: 0, declined: 0 };
    for (const campaign of campaigns) result[bucketOf(campaign)] += 1;
    return result;
  }, [campaigns]);

  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase();
    const filtered = campaigns.filter((campaign) => {
      if (bucket !== "all" && bucketOf(campaign) !== bucket) return false;
      return !needle || campaign.title.toLowerCase().includes(needle);
    });
    return filtered.sort((a, b) => {
      const delta = new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
      return newestFirst ? delta : -delta;
    });
  }, [campaigns, search, bucket, newestFirst]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-3">
        <div className="relative">
          <SearchIcon className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Cerca per titolo"
            className="pl-9"
            aria-label="Cerca fra le tue campagne"
          />
          {search && (
            <button
              type="button"
              onClick={() => setSearch("")}
              aria-label="Cancella la ricerca"
              className="absolute top-1/2 right-2 -translate-y-1/2 rounded p-1 text-muted-foreground hover:text-foreground"
            >
              <XIcon className="size-4" />
            </button>
          )}
        </div>

        <div className="flex flex-wrap gap-2">
          {BUCKETS.map((option) => {
            const active = bucket === option.value;
            return (
              <button
                key={option.value}
                type="button"
                onClick={() => setBucket(option.value)}
                aria-pressed={active}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-sm font-medium shadow-xs transition-colors focus-visible:ring-3 focus-visible:ring-primary/30 focus-visible:outline-none",
                  active
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-border bg-card text-card-foreground hover:border-primary/40 hover:bg-primary/10 hover:text-primary"
                )}
              >
                {option.label}
                <span
                  className={cn(
                    "rounded-full px-1.5 text-xs leading-5 tabular-nums",
                    active ? "bg-white/25 text-primary-foreground" : "bg-primary/10 text-primary"
                  )}
                >
                  {counts[option.value]}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          {visible.length === campaigns.length
            ? `${numberFormat.format(campaigns.length)} ${campaigns.length === 1 ? "campagna" : "campagne"}`
            : `${numberFormat.format(visible.length)} su ${numberFormat.format(campaigns.length)}`}
        </p>
        <Button variant="ghost" size="sm" onClick={() => setNewestFirst((value) => !value)}>
          {newestFirst ? "Più recenti prima" : "Più vecchie prima"}
        </Button>
      </div>

      {visible.length === 0 ? (
        <Card>
          <CardContent className="p-6 text-sm text-muted-foreground">
            Nessuna campagna corrisponde a questa ricerca.
          </CardContent>
        </Card>
      ) : (
        <div className="flex flex-col gap-2">
          {visible.map((campaign) => (
            <CampaignRow key={campaign.id} campaign={campaign} />
          ))}
        </div>
      )}
    </div>
  );
}

function CampaignRow({ campaign }: { campaign: PortalCampaign }) {
  const reason = nonParticipation(campaign);
  const declined = reason !== null;
  const openForChanges = campaign.status === "announced";

  const body = (
    <CardContent className="flex flex-col gap-2 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className={cn("min-w-0 flex-1 truncate font-medium", declined && "text-muted-foreground")}>
          {campaign.title}
        </p>
        <Badge variant="outline">{STATUS_LABELS[campaign.status] ?? campaign.status}</Badge>
      </div>

      {declined ? (
        <p className="flex items-center gap-1 text-sm text-muted-foreground">
          <MinusCircleIcon className="size-3.5" />
          {reason === "declined" ? "hai scelto di non partecipare" : "escluso da un amministratore"}
        </p>
      ) : (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm tabular-nums">
          <span className="text-muted-foreground">
            {numberFormat.format(campaign.channels_targeted)}{" "}
            {campaign.channels_targeted === 1 ? "canale" : "canali"}
          </span>
          <span className="text-emerald-600 dark:text-emerald-400">
            {numberFormat.format(campaign.published)} pubblicati
          </span>
          {campaign.pending > 0 && (
            <span className="text-amber-600 dark:text-amber-400">
              {numberFormat.format(campaign.pending)} in corso
            </span>
          )}
          {campaign.failed > 0 && (
            <span className="text-destructive">{numberFormat.format(campaign.failed)} non riusciti</span>
          )}
        </div>
      )}

      <p className="text-xs text-muted-foreground">{dateFormat.format(new Date(campaign.created_at))}</p>
    </CardContent>
  );

  // Solo una campagna ancora in palinsesto porta da qualche parte: per le altre
  // il link aprirebbe una pagina dove non c'e' piu' niente da decidere.
  return openForChanges ? (
    <Card className="transition-shadow hover:shadow-md">
      <Link href={`/portal/lineup/${campaign.id}`} className="block">
        {body}
      </Link>
    </Card>
  ) : (
    <Card>{body}</Card>
  );
}
