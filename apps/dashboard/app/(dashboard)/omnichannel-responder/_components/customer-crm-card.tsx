"use client";

import { useState } from "react";
import { DatabaseIcon, Loader2Icon, RefreshCwIcon } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useCustomerCrmProfile } from "@/hooks/use-omnichannel";
import { ApiError } from "@/lib/api/client";
import type { OmniCustomerCrmProfileResponse } from "@/types/api";

const STATUS_LABEL: Record<OmniCustomerCrmProfileResponse["status"], { label: string; variant: "default" | "secondary" | "outline" | "destructive" }> = {
  identified: { label: "Identificato", variant: "default" },
  ambiguous: { label: "Più account", variant: "secondary" },
  not_found: { label: "Non in anagrafica", variant: "outline" },
  unverified: { label: "Identità non verificabile", variant: "outline" },
  unavailable: { label: "CRM non disponibile", variant: "destructive" },
  disabled: { label: "Integrazione spenta", variant: "outline" },
};

function asText(value: unknown): string | null {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value === "object") return null;
  return String(value);
}

function fullName(customer: Record<string, unknown> | null): string | null {
  if (!customer) return null;
  const parts = [asText(customer.first_name), asText(customer.last_name)].filter(Boolean);
  return parts.length ? parts.join(" ") : asText(customer.name);
}

function walletBalance(wallets: Record<string, unknown> | null, key: string): string | null {
  const wallet = wallets?.[key];
  if (!wallet || typeof wallet !== "object") return null;
  return asText((wallet as Record<string, unknown>).balance);
}

/**
 * Scheda CRM del contatto, caricata a richiesta: ogni lettura e' una chiamata
 * al CRM Mamify e una riga di audit (CRM_PROFILE_VIEWED), quindi non parte da
 * sola a ogni conversazione aperta. Mostra la stessa identificazione che
 * vede l'AI - e' il modo per capire perche' una bozza dice "non posso
 * fornire dati di account".
 */
export function CustomerCrmCard({ customerId, channel }: { customerId: string; channel: string }) {
  const [requested, setRequested] = useState(false);
  const { data, isFetching, error, refetch } = useCustomerCrmProfile(customerId, channel, requested);

  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between">
        <p className="flex items-center gap-1 text-xs font-medium text-muted-foreground">
          <DatabaseIcon className="size-3.5" /> CRM Mamify
        </p>
        <Button
          size="xs"
          variant="ghost"
          disabled={isFetching}
          onClick={() => {
            if (requested) void refetch();
            else setRequested(true);
          }}
        >
          {isFetching ? <Loader2Icon className="animate-spin" /> : <RefreshCwIcon />}
          {requested ? "Aggiorna" : "Consulta"}
        </Button>
      </div>

      {!requested && (
        <p className="text-xs text-muted-foreground">Anagrafica e saldi del cliente, letti dal CRM al momento.</p>
      )}

      {requested && error && (
        <p className="text-xs text-destructive">{error instanceof ApiError ? error.message : "Impossibile consultare il CRM"}</p>
      )}

      {requested && data && (
        <div className="space-y-2 text-xs">
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge variant={STATUS_LABEL[data.status].variant}>{STATUS_LABEL[data.status].label}</Badge>
            {data.identity_source && (
              <span className="text-muted-foreground">
                {data.identity_source === "channel" ? "dal numero del canale" : "dai contatti in scheda"}
              </span>
            )}
            {data.candidates ? <span className="text-muted-foreground">({data.candidates} account)</span> : null}
          </div>

          {data.status === "identified" && (
            <div className="space-y-1 rounded-md border bg-muted/30 p-2.5">
              {fullName(data.customer) && <p className="font-medium text-foreground">{fullName(data.customer)}</p>}
              {asText(data.customer?.email) && <p className="text-muted-foreground">{asText(data.customer?.email)}</p>}
              {asText(data.customer?.code ?? data.customer?.invite_code) && (
                <p className="text-muted-foreground">Codice invito: {asText(data.customer?.code ?? data.customer?.invite_code)}</p>
              )}
              {data.wallets && (
                <div className="mt-1.5 grid grid-cols-2 gap-2">
                  <div className="rounded border bg-background px-2 py-1.5">
                    <p className="text-[0.65rem] text-muted-foreground uppercase">Mamix</p>
                    <p className="font-semibold tabular-nums">{walletBalance(data.wallets, "mamix") ?? "—"}</p>
                  </div>
                  <div className="rounded border bg-background px-2 py-1.5">
                    <p className="text-[0.65rem] text-muted-foreground uppercase">MamiCash</p>
                    <p className="font-semibold tabular-nums">{walletBalance(data.wallets, "mamicash") ?? "—"}</p>
                  </div>
                </div>
              )}
              {data.customer?.network && typeof data.customer.network === "object" ? (
                <p className="text-muted-foreground">
                  Rete: {asText((data.customer.network as Record<string, unknown>).direct) ?? "—"} diretti, {asText((data.customer.network as Record<string, unknown>).total) ?? "—"} totali
                </p>
              ) : null}
            </div>
          )}

          {data.message && <p className="text-muted-foreground">{data.message}</p>}
          {data.status === "disabled" && (
            <Link href="/omnichannel-responder/settings" className="underline">Attiva il CRM nella pagina AI Agent</Link>
          )}
        </div>
      )}
    </div>
  );
}
