"use client";

import { CheckIcon, ChevronDownIcon, LayersIcon, XIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import { ChannelIcon, channelLabel } from "./channel-icon";
import type { OmniChannelAccountResponse } from "@/types/api";

/** "+39 333 1234567" per i numeri WhatsApp; gli altri id esterni restano com'erano. */
export function accountSubtitle(account: OmniChannelAccountResponse): string {
  const ext = account.external_account_id?.trim();
  if (ext && /^\d{9,15}$/.test(ext) && account.channel.startsWith("whatsapp")) {
    return `+${ext.slice(0, 2)} ${ext.slice(2, 5)} ${ext.slice(5)}`;
  }
  return ext || channelLabel(account.channel);
}

function PendingBadge({ count, active }: { count: number; active?: boolean }) {
  if (count <= 0) return null;
  return (
    <span
      title={`${count} da gestire`}
      className={cn(
        "ml-auto rounded-full px-1.5 py-0.5 text-[0.65rem] font-semibold tabular-nums",
        active ? "bg-primary text-primary-foreground" : "bg-amber-500/15 text-amber-700 dark:text-amber-400"
      )}
    >
      {count}
    </span>
  );
}

interface AccountSwitcherProps {
  accounts: OmniChannelAccountResponse[] | undefined;
  value: string;
  onChange: (accountId: string) => void;
}

/**
 * "Su quale numero sto lavorando": un selettore unico al posto delle pillole,
 * che regge anche dieci numeri collegati. Il bottone mostra sempre la scelta
 * corrente (nome + numero + quante conversazioni da gestire), la tendina
 * elenca tutti i canali con lo stesso dettaglio, cosi' si vede a colpo
 * d'occhio dove c'e' lavoro prima ancora di cambiare filtro. La "X" accanto
 * torna a "Tutti i canali" senza aprire il menu.
 */
export function AccountSwitcher({ accounts, value, onChange }: AccountSwitcherProps) {
  const list = accounts ?? [];
  const selected = list.find((a) => a.id === value);
  const totalPending = list.reduce((sum, a) => sum + (a.pending_count ?? 0), 0);
  // Il filtro punta a un canale che non esiste piu' (link vecchio, account
  // eliminato): lo diciamo invece di mostrare una lista vuota senza motivo.
  const stale = value !== "" && accounts !== undefined && !selected;

  return (
    <div className="flex items-center gap-1">
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button
              variant={selected ? "default" : "outline"}
              size="sm"
              className={cn("max-w-72 justify-start gap-2 pr-2", stale && "border-destructive text-destructive")}
              title="Scegli su quale numero o canale lavorare"
            />
          }
        >
          {selected ? <ChannelIcon channel={selected.channel} className="size-5 bg-background/20 text-current" /> : <LayersIcon className="size-4" />}
          <span className="flex min-w-0 flex-col items-start leading-none">
            <span className="truncate text-xs font-semibold">{selected ? selected.name : stale ? "Canale non trovato" : "Tutti i canali"}</span>
            <span className={cn("truncate text-[0.65rem] font-normal", selected ? "text-primary-foreground/80" : "text-muted-foreground")}>
              {selected ? accountSubtitle(selected) : stale ? "Scegli un altro numero" : `${list.length} collegati`}
            </span>
          </span>
          <PendingBadge count={selected ? selected.pending_count : totalPending} active={!!selected} />
          <ChevronDownIcon className="size-3.5 shrink-0 opacity-70" />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-80">
          <DropdownMenuGroup>
            <DropdownMenuLabel className="text-xs text-muted-foreground">Sto lavorando su</DropdownMenuLabel>
            <DropdownMenuItem onClick={() => onChange("")} className="gap-2.5 py-2">
              <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-muted">
                <LayersIcon className="size-4 text-muted-foreground" />
              </span>
              <span className="flex min-w-0 flex-1 flex-col">
                <span className="text-sm font-medium">Tutti i canali</span>
                <span className="text-[0.7rem] text-muted-foreground">Ogni numero e canale collegato</span>
              </span>
              <PendingBadge count={totalPending} />
              {value === "" && <CheckIcon className="size-4 text-primary" />}
            </DropdownMenuItem>
          </DropdownMenuGroup>
          <DropdownMenuSeparator />
          <DropdownMenuGroup>
            {list.length === 0 && <DropdownMenuItem disabled>Nessun canale collegato</DropdownMenuItem>}
            {list.map((account) => (
              <DropdownMenuItem key={account.id} onClick={() => onChange(account.id)} className="gap-2.5 py-2">
                <ChannelIcon channel={account.channel} className="size-7" />
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="flex items-center gap-1.5">
                    <span className="truncate text-sm font-medium">{account.name}</span>
                    {account.status === "disabled" && <span className="text-[0.65rem] text-muted-foreground">(sospeso)</span>}
                  </span>
                  <span className="truncate text-[0.7rem] text-muted-foreground">
                    {accountSubtitle(account)} · {account.conversation_count} conversazioni
                  </span>
                </span>
                <PendingBadge count={account.pending_count} />
                {value === account.id && <CheckIcon className="size-4 text-primary" />}
              </DropdownMenuItem>
            ))}
          </DropdownMenuGroup>
        </DropdownMenuContent>
      </DropdownMenu>
      {value !== "" && (
        <Button size="icon-sm" variant="ghost" title="Torna a tutti i canali" onClick={() => onChange("")}>
          <XIcon />
        </Button>
      )}
    </div>
  );
}
