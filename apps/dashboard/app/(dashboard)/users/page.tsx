"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { ColumnDef } from "@tanstack/react-table";
import { PlusIcon, PencilIcon, LinkIcon, IdCardIcon, UserRoundIcon, UsersIcon, UserCheckIcon, UserMinusIcon, BanIcon } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { DataTable } from "@/components/shared/data-table";
import { SearchInput } from "@/components/shared/search-input";
import { FilterBar, FilterSelect } from "@/components/shared/filter-bar";
import { Pagination } from "@/components/shared/pagination";
import { StatCard } from "@/components/shared/stat-card";
import { StatusBadge } from "@/components/shared/status-badge";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useUsers, useUsersSummary } from "@/hooks/use-users";
import { useDebounce } from "@/hooks/use-debounce";
import { formatDateTime } from "@/lib/format";
import type { UserResponse, UserStatus } from "@/types/api";
import { UserFormDialog } from "./_components/user-form-dialog";
import { ReferralLinkDialog } from "./_components/referral-link-dialog";
import { PersonalContactsDialog } from "./_components/personal-contacts-dialog";

const LIMIT = 20;

export default function UsersPage() {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<UserStatus | "">("");
  const [skip, setSkip] = useState(0);
  const [formOpen, setFormOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<UserResponse | undefined>(undefined);
  const [referralUser, setReferralUser] = useState<UserResponse | undefined>(undefined);
  const [contactsUser, setContactsUser] = useState<UserResponse | undefined>(undefined);

  const debouncedSearch = useDebounce(search, 300);
  const usersQuery = useUsers({
    search: debouncedSearch || undefined,
    status_filter: statusFilter || undefined,
    skip,
    limit: LIMIT,
  });
  const summaryQuery = useUsersSummary();
  const summary = summaryQuery.data;

  function openCreate() {
    setEditingUser(undefined);
    setFormOpen(true);
  }

  function openEdit(user: UserResponse) {
    setEditingUser(user);
    setFormOpen(true);
  }

  const columns = useMemo<ColumnDef<UserResponse, unknown>[]>(
    () => [
      {
        accessorKey: "name",
        header: "Nome",
        cell: ({ row }) => (
          <div className="flex items-center gap-2.5">
            <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground">
              <UserRoundIcon className="size-4" />
            </span>
            <div>
              <p className="font-medium text-foreground">{row.original.name}</p>
              <p className="text-xs text-muted-foreground">{row.original.email}</p>
            </div>
          </div>
        ),
      },
      {
        accessorKey: "company_name",
        header: "Azienda",
        cell: ({ row }) => row.original.company_name || "—",
      },
      {
        accessorKey: "groups",
        header: "Gruppi",
        cell: ({ row }) =>
          row.original.groups.length > 0 ? (
            <div className="flex flex-wrap gap-1">
              {row.original.groups.map((group) => (
                <Badge key={group.id} variant="secondary">
                  {group.name}
                </Badge>
              ))}
            </div>
          ) : (
            <span className="text-muted-foreground">—</span>
          ),
      },
      {
        accessorKey: "status",
        header: "Stato",
        cell: ({ row }) => <StatusBadge status={row.original.status} />,
      },
      {
        accessorKey: "created_at",
        header: "Creato",
        cell: ({ row }) => formatDateTime(row.original.created_at),
      },
      {
        id: "actions",
        header: "",
        cell: ({ row }) => (
          <div className="flex justify-end gap-1">
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => setReferralUser(row.original)}
              aria-label="Configura referral"
              title={row.original.referral_link ? "Link referral configurato" : "Configura referral"}
              className={row.original.referral_link ? "text-primary" : undefined}
            >
              <LinkIcon className="size-3.5" />
            </Button>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => setContactsUser(row.original)}
              aria-label="Contatti personali"
              title={row.original.personal_contacts ? "Contatti personali configurati" : "Contatti personali"}
              className={row.original.personal_contacts ? "text-primary" : undefined}
            >
              <IdCardIcon className="size-3.5" />
            </Button>
            <Button variant="ghost" size="icon-sm" onClick={() => openEdit(row.original)} aria-label="Modifica">
              <PencilIcon className="size-3.5" />
            </Button>
            <Button variant="ghost" size="sm" asChild>
              <Link href={`/users/${row.original.id}`}>Dettaglio</Link>
            </Button>
          </div>
        ),
      },
    ],
    []
  );

  return (
    <div className="space-y-4">
      <PageHeader
        title="Utenti"
        description="Gestisci i clienti della piattaforma e le loro appartenenze ai gruppi"
        actions={
          <Button onClick={openCreate}>
            <PlusIcon className="size-4" />
            Nuovo utente
          </Button>
        }
      />

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard label="Totale utenti" value={summary?.total ?? "—"} icon={UsersIcon} loading={summaryQuery.isLoading} />
        <StatCard
          label="Attivi"
          value={summary?.active ?? "—"}
          icon={UserCheckIcon}
          tone="success"
          loading={summaryQuery.isLoading}
        />
        <StatCard
          label="Inattivi"
          value={summary?.inactive ?? "—"}
          icon={UserMinusIcon}
          loading={summaryQuery.isLoading}
        />
        <StatCard
          label="Sospesi"
          value={summary?.suspended ?? "—"}
          icon={BanIcon}
          tone="destructive"
          loading={summaryQuery.isLoading}
        />
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <SearchInput
          value={search}
          onChange={(value) => {
            setSearch(value);
            setSkip(0);
          }}
          placeholder="Cerca per nome, email o azienda..."
          className="sm:max-w-xs"
        />
        <FilterBar>
          <FilterSelect
            value={statusFilter}
            onChange={(value) => {
              setStatusFilter(value as UserStatus | "");
              setSkip(0);
            }}
            placeholder="Stato"
            options={[
              { value: "active", label: "Attivo" },
              { value: "inactive", label: "Inattivo" },
              { value: "suspended", label: "Sospeso" },
            ]}
          />
        </FilterBar>
      </div>

      <DataTable
        columns={columns}
        data={usersQuery.data}
        isLoading={usersQuery.isLoading}
        isError={usersQuery.isError}
        error={usersQuery.error}
        onRetry={() => usersQuery.refetch()}
        emptyTitle="Nessun utente trovato"
        emptyDescription="Prova a modificare i filtri di ricerca oppure crea un nuovo utente."
      />

      {usersQuery.data && (
        <Pagination skip={skip} limit={LIMIT} count={usersQuery.data.length} onSkipChange={setSkip} />
      )}

      <UserFormDialog open={formOpen} onOpenChange={setFormOpen} user={editingUser} />
      {referralUser && (
        <ReferralLinkDialog
          open={!!referralUser}
          onOpenChange={(open) => !open && setReferralUser(undefined)}
          user={referralUser}
        />
      )}
      {contactsUser && (
        <PersonalContactsDialog
          open={!!contactsUser}
          onOpenChange={(open) => !open && setContactsUser(undefined)}
          user={contactsUser}
        />
      )}
    </div>
  );
}
