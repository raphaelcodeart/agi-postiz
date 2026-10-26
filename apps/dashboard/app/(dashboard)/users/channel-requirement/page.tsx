"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { ColumnDef } from "@tanstack/react-table";
import { toast } from "sonner";
import {
  ArrowLeftIcon,
  BellRingIcon,
  CheckCircle2Icon,
  MailIcon,
  MailWarningIcon,
  Share2Icon,
  TriangleAlertIcon,
  UserRoundIcon,
  UsersIcon,
} from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { DataTable } from "@/components/shared/data-table";
import { SearchInput } from "@/components/shared/search-input";
import { FilterBar, FilterSelect } from "@/components/shared/filter-bar";
import { StatCard } from "@/components/shared/stat-card";
import { StatusBadge } from "@/components/shared/status-badge";
import { PlatformBadge } from "@/components/shared/platform-badge";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useChannelRequirement, useNotifyAllChannelRequirement, useNotifyChannelRequirement } from "@/hooks/use-users";
import { useDebounce } from "@/hooks/use-debounce";
import { ApiError } from "@/lib/api/client";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { ChannelRequirementUser, UserStatus } from "@/types/api";

const DAY_MS = 24 * 60 * 60 * 1000;

function notifiedWithin(user: ChannelRequirementUser, days: number): boolean {
  if (!user.last_notified_at || days <= 0) return false;
  return Date.now() - new Date(user.last_notified_at).getTime() < days * DAY_MS;
}

export default function ChannelRequirementPage() {
  const [search, setSearch] = useState("");
  // "active" di default: sono gli utenti che le campagne cercano. Inattivi e
  // sospesi restano raggiungibili dal filtro, ma non vanno avvisati per sbaglio.
  const [statusFilter, setStatusFilter] = useState<UserStatus | "">("active");
  const [includeRecent, setIncludeRecent] = useState(false);
  const [confirmAllOpen, setConfirmAllOpen] = useState(false);
  const [pendingUserId, setPendingUserId] = useState<string | null>(null);

  const debouncedSearch = useDebounce(search, 300);
  const query = useChannelRequirement({ status_filter: statusFilter, search: debouncedSearch || undefined });
  const data = query.data;
  const notifyOne = useNotifyChannelRequirement();
  const notifyAll = useNotifyAllChannelRequirement();

  const emailEnabled = data?.email_enabled ?? false;
  const required = data?.required_channels ?? 2;
  const cooldownDays = data?.cooldown_days ?? 7;
  const users = data?.users ?? [];
  const recentCount = users.filter((u) => notifiedWithin(u, cooldownDays)).length;
  const bulkTargets = includeRecent ? users.length : users.length - recentCount;

  function errorMessage(err: unknown, fallback: string) {
    return err instanceof ApiError ? err.message : fallback;
  }

  function handleNotifyOne(user: ChannelRequirementUser) {
    setPendingUserId(user.id);
    notifyOne.mutate(user.id, {
      onSuccess: (result) => {
        toast.success(`Avviso inviato a ${user.name}`, {
          description: `${result.email} · ${result.notifications_count}° avviso`,
        });
      },
      onError: (err) => toast.error(errorMessage(err, `Impossibile inviare l'avviso a ${user.name}`)),
      onSettled: () => setPendingUserId(null),
    });
  }

  function handleNotifyAll() {
    notifyAll.mutate(
      { status_filter: statusFilter || null, skip_notified_within_days: includeRecent ? 0 : null },
      {
        onSuccess: (result) => {
          setConfirmAllOpen(false);
          const parts = [`${result.sent} ${result.sent === 1 ? "avviso inviato" : "avvisi inviati"}`];
          if (result.skipped_recent > 0) parts.push(`${result.skipped_recent} saltati perché avvisati di recente`);
          if (result.failed > 0) parts.push(`${result.failed} non riusciti`);
          const notify = result.failed > 0 ? toast.warning : toast.success;
          notify("Notifica a tutti completata", { description: parts.join(" · ") });
        },
        onError: (err) => toast.error(errorMessage(err, "Impossibile inviare gli avvisi")),
      }
    );
  }

  const columns = useMemo<ColumnDef<ChannelRequirementUser, unknown>[]>(
    () => [
      {
        accessorKey: "name",
        header: "Utente",
        cell: ({ row }) => (
          <div className="flex items-center gap-2.5">
            <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground">
              <UserRoundIcon className="size-4" />
            </span>
            <div className="min-w-0">
              <p className="truncate font-medium text-foreground">{row.original.name}</p>
              <p className="truncate text-xs text-muted-foreground">
                {row.original.email}
                {row.original.company_name ? ` · ${row.original.company_name}` : ""}
              </p>
            </div>
          </div>
        ),
      },
      {
        accessorKey: "status",
        header: "Stato",
        cell: ({ row }) => <StatusBadge status={row.original.status} />,
      },
      {
        accessorKey: "connected_channels_count",
        header: "Canali collegati",
        cell: ({ row }) => {
          const count = row.original.connected_channels_count;
          return (
            <div className="flex flex-wrap items-center gap-1.5">
              <Badge variant={count === 0 ? "destructive" : "secondary"} className="tabular-nums">
                {count} / {required}
              </Badge>
              {row.original.connected_channels.length === 0 ? (
                <span className="text-xs text-muted-foreground">Nessun canale utilizzabile</span>
              ) : (
                row.original.connected_channels.map((channel) => (
                  <Tooltip key={`${channel.platform}-${channel.name}`}>
                    <TooltipTrigger className="inline-flex">
                      <PlatformBadge platform={channel.platform} />
                    </TooltipTrigger>
                    <TooltipContent>{channel.name}</TooltipContent>
                  </Tooltip>
                ))
              )}
            </div>
          );
        },
      },
      {
        accessorKey: "has_portal_access",
        header: "Portale",
        cell: ({ row }) =>
          row.original.has_portal_access ? (
            <span className="text-sm text-muted-foreground">Registrato</span>
          ) : (
            <Tooltip>
              <TooltipTrigger className="text-sm text-warning-foreground dark:text-warning">Mai entrato</TooltipTrigger>
              <TooltipContent className="max-w-64">
                Creato dall&apos;amministrazione, non ha ancora una password. L&apos;email gli spiega di registrarsi con
                questo stesso indirizzo per ritrovare il suo account.
              </TooltipContent>
            </Tooltip>
          ),
      },
      {
        accessorKey: "last_notified_at",
        header: "Ultimo avviso",
        cell: ({ row }) => {
          const user = row.original;
          if (!user.last_notified_at) return <span className="text-sm text-muted-foreground">Mai avvisato</span>;
          const recent = notifiedWithin(user, cooldownDays);
          return (
            <div className="text-sm">
              <p className={cn(recent && "text-foreground")}>{formatDateTime(user.last_notified_at)}</p>
              <p className="text-xs text-muted-foreground">
                {user.notifications_count} {user.notifications_count === 1 ? "avviso inviato" : "avvisi inviati"}
                {recent ? " · recente" : ""}
              </p>
            </div>
          );
        },
      },
      {
        id: "actions",
        header: "",
        cell: ({ row }) => {
          const user = row.original;
          const isPending = pendingUserId === user.id && notifyOne.isPending;
          return (
            <div className="flex justify-end">
              <Button
                size="sm"
                variant="outline"
                disabled={!emailEnabled || isPending || notifyAll.isPending}
                onClick={() => handleNotifyOne(user)}
                title={emailEnabled ? `Invia l'avviso a ${user.email}` : "Invio email non configurato"}
              >
                <MailIcon className={cn("size-3.5", isPending && "animate-pulse")} />
                {user.notifications_count > 0 ? "Invia di nuovo" : "Invia avviso"}
              </Button>
            </div>
          );
        },
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [required, cooldownDays, emailEnabled, pendingUserId, notifyOne.isPending, notifyAll.isPending]
  );

  return (
    <div className="space-y-4">
      <PageHeader
        title="Canali insufficienti"
        description={`Promoter con meno di ${required} canali social collegati e utilizzabili. Il progetto ne richiede almeno ${required}: da qui li avvisi via email, uno per uno o tutti insieme.`}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="ghost" asChild>
              <Link href="/users">
                <ArrowLeftIcon className="size-4" />
                Utenti
              </Link>
            </Button>
            <Button
              size="lg"
              disabled={!emailEnabled || query.isLoading || bulkTargets === 0 || notifyAll.isPending}
              onClick={() => setConfirmAllOpen(true)}
              title={emailEnabled ? undefined : "Invio email non configurato"}
            >
              <BellRingIcon className={cn("size-4", notifyAll.isPending && "animate-pulse")} />
              Notifica a tutti
              {data && (
                <Badge variant="secondary" className="ml-1 bg-background/20 text-primary-foreground">
                  {bulkTargets}
                </Badge>
              )}
            </Button>
          </div>
        }
      />

      {data && !emailEnabled && (
        <Alert variant="destructive">
          <MailWarningIcon />
          <AlertTitle>Invio email non configurato</AlertTitle>
          <AlertDescription>
            Il server non ha SMTP_HOST ed EMAIL_FROM_ADDRESS impostati: la lista funziona, ma nessun avviso può
            partire. Configura l&apos;invio nel file .env dell&apos;API (vedi docs/DEPLOYMENT.md) e riavvia api e worker.
          </AlertDescription>
        </Alert>
      )}

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard label="Sotto soglia" value={data?.total ?? "—"} icon={UsersIcon} loading={query.isLoading} />
        <StatCard
          label="Senza nessun canale"
          value={data?.without_channels ?? "—"}
          icon={TriangleAlertIcon}
          tone="destructive"
          loading={query.isLoading}
        />
        <StatCard label="Mai avvisati" value={data?.never_notified ?? "—"} icon={MailIcon} loading={query.isLoading} />
        <StatCard
          label="Canali richiesti"
          value={required}
          icon={Share2Icon}
          hint="per ogni promoter"
          loading={query.isLoading}
        />
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <SearchInput value={search} onChange={setSearch} placeholder="Cerca per nome, email o azienda..." className="sm:max-w-xs" />
        <FilterBar>
          <FilterSelect
            value={statusFilter}
            onChange={(value) => setStatusFilter(value as UserStatus | "")}
            placeholder="Tutti gli stati"
            options={[
              { value: "active", label: "Attivi" },
              { value: "inactive", label: "Inattivi" },
              { value: "suspended", label: "Sospesi" },
            ]}
          />
          <div className="flex items-center gap-2 rounded-md border px-3 py-1.5">
            <Switch id="include-recent" checked={includeRecent} onCheckedChange={setIncludeRecent} />
            <Label htmlFor="include-recent" className="cursor-pointer text-xs font-normal text-muted-foreground">
              Includi chi è stato avvisato negli ultimi {cooldownDays} giorni
              {recentCount > 0 ? ` (${recentCount})` : ""}
            </Label>
          </div>
        </FilterBar>
      </div>

      <DataTable
        columns={columns}
        data={data?.users}
        isLoading={query.isLoading}
        isError={query.isError}
        error={query.error}
        onRetry={() => query.refetch()}
        emptyTitle="Tutti a posto"
        emptyDescription={`Nessun utente ${statusFilter ? "con questo stato " : ""}ha meno di ${required} canali social collegati.`}
      />

      {data && users.length === 0 && !query.isLoading && !search && (
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <CheckCircle2Icon className="size-3.5 text-success" /> Il requisito è rispettato da tutti gli utenti filtrati.
        </p>
      )}

      <ConfirmDialog
        open={confirmAllOpen}
        onOpenChange={setConfirmAllOpen}
        title={`Inviare l'avviso a ${bulkTargets} ${bulkTargets === 1 ? "utente" : "utenti"}?`}
        description={
          `Ogni destinatario riceverà un'email che spiega che il progetto richiede almeno ${required} canali social collegati, ` +
          `mostra quali ha già e come aggiungere quelli mancanti. ` +
          (includeRecent
            ? `Verranno avvisati anche i ${recentCount} utenti che hanno già ricevuto il messaggio negli ultimi ${cooldownDays} giorni.`
            : recentCount > 0
              ? `${recentCount} ${recentCount === 1 ? "utente che ha" : "utenti che hanno"} già ricevuto il messaggio negli ultimi ${cooldownDays} giorni ${recentCount === 1 ? "verrà saltato" : "verranno saltati"}.`
              : `Nessuno è stato avvisato negli ultimi ${cooldownDays} giorni.`) +
          (statusFilter ? ` Riguarda solo gli utenti con stato "${statusFilter === "active" ? "attivo" : statusFilter === "inactive" ? "inattivo" : "sospeso"}".` : " Riguarda gli utenti di ogni stato.")
        }
        confirmLabel={`Invia ${bulkTargets} ${bulkTargets === 1 ? "avviso" : "avvisi"}`}
        loading={notifyAll.isPending}
        onConfirm={handleNotifyAll}
      />
    </div>
  );
}
