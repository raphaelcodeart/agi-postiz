"use client";

import { useMemo, useState } from "react";
import { CheckIcon, Loader2Icon, SearchIcon, UsersRoundIcon, XIcon } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { PortalGroup, PortalUser } from "@/lib/portal/server";

/**
 * Citta', codice postale e gruppi: il modulo del profilo del promoter.
 *
 * Lo usano in due il popup del primo accesso (profile-gate.tsx) e la pagina
 * Impostazioni (settings/): stessi campi, stessa chiamata, stesse regole di
 * validazione. Tenerne una copia sola vuol dire che un campo aggiunto domani
 * compare in entrambi i posti, e che il popup non puo' accettare qualcosa che
 * le impostazioni poi rifiutano.
 *
 * Il salvataggio passa da POST /portal/profile, che sostituisce i gruppi
 * dell'utente con quelli scelti e imposta profile_completed_at solo la prima
 * volta: e' la stessa rotta sia per compilare che per correggere.
 *
 * I gruppi possono essere decine. Per questo l'elenco scorre dentro un
 * riquadro ad altezza fissa invece di allungare il popup, sopra c'e' una
 * ricerca che filtra per nome e descrizione (senza badare a maiuscole e
 * accenti), e i gruppi scelti restano riepilogati in chip sopra l'elenco:
 * cosi' una scelta fatta prima di filtrare non sparisce dalla vista, e si
 * puo' togliere da li' senza doverla ricercare.
 */

/** Sopra questa soglia compare la ricerca; sotto, un elenco corto basta. */
const SEARCH_THRESHOLD = 6;

/** "Città" e "citta" devono trovarsi a vicenda: via accenti e maiuscole. */
function normalize(text: string): string {
  return text
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}
export function PortalProfileForm({
  groups,
  initialCity,
  initialPostalCode,
  initialGroupIds,
  submitLabel,
  footnote,
  onSaved,
}: {
  groups: PortalGroup[];
  initialCity: string | null;
  initialPostalCode: string | null;
  initialGroupIds: string[];
  submitLabel: string;
  footnote?: React.ReactNode;
  /** Chiamato con il profilo aggiornato restituito dall'API. */
  onSaved: (user: PortalUser) => void | Promise<void>;
}) {
  const [city, setCity] = useState(initialCity ?? "");
  const [postalCode, setPostalCode] = useState(initialPostalCode ?? "");
  const [selected, setSelected] = useState<Set<string>>(() => new Set(initialGroupIds));
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  const searchable = groups.length > SEARCH_THRESHOLD;
  const visibleGroups = useMemo(() => {
    const needle = normalize(query);
    if (!needle) return groups;
    return groups.filter(
      (group) => normalize(group.name).includes(needle) || normalize(group.description ?? "").includes(needle)
    );
  }, [groups, query]);
  const selectedGroups = useMemo(() => groups.filter((group) => selected.has(group.id)), [groups, selected]);

  const canSubmit = city.trim().length >= 2 && postalCode.trim().length >= 3 && selected.size > 0;

  function toggle(groupId: string) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(groupId)) next.delete(groupId);
      else next.add(groupId);
      return next;
    });
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!canSubmit || pending) return;
    setPending(true);
    setError(null);
    try {
      const response = await fetch("/api/portal/backend/profile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          city: city.trim(),
          postal_code: postalCode.trim(),
          group_ids: Array.from(selected),
        }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        const detail = payload?.detail;
        setError(
          typeof detail === "string"
            ? detail
            : "Controlla i dati inseriti: città e codice postale devono essere compilati e serve almeno un gruppo."
        );
        return;
      }
      await onSaved(payload as PortalUser);
    } catch {
      setError("Servizio non raggiungibile. Riprova fra poco.");
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={onSubmit} noValidate>
      <div className="grid gap-4">
        <div className="grid gap-3 sm:grid-cols-[1fr_9rem]">
          <div className="grid gap-1.5">
            <Label htmlFor="profile-city">Città</Label>
            <Input
              id="profile-city"
              autoComplete="address-level2"
              required
              minLength={2}
              maxLength={120}
              value={city}
              onChange={(event) => setCity(event.target.value)}
              placeholder="Es. Torino"
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="profile-postal-code">Codice postale</Label>
            <Input
              id="profile-postal-code"
              autoComplete="postal-code"
              inputMode="numeric"
              required
              minLength={3}
              maxLength={20}
              value={postalCode}
              onChange={(event) => setPostalCode(event.target.value)}
              placeholder="Es. 10121"
            />
          </div>
        </div>

        <fieldset className="grid gap-2">
          <legend className="flex items-center gap-2 text-sm font-medium">
            <UsersRoundIcon className="size-4 text-[var(--pa-accent)]" aria-hidden />
            Gruppi a cui vuoi partecipare
            <span className="font-normal text-[var(--pa-muted)]">(almeno uno)</span>
          </legend>
          <p className="text-[0.82rem] leading-relaxed text-[var(--pa-muted)]">
            Le campagne vengono proposte ai gruppi: scegliendoli qui ti trovi già dentro quelli giusti. Puoi
            sceglierne più di uno.
          </p>

          {groups.length === 0 ? (
            <p className="pa-notice pa-notice--error mt-1">
              Al momento non ci sono gruppi disponibili: scrivici e li creiamo insieme a te.
            </p>
          ) : (
            <div className="mt-1 grid gap-2">
              {/* Riepilogo delle scelte: vive fuori dall'elenco filtrato, cosi'
                  non dipende da cosa si sta cercando in quel momento. */}
              <div
                className="flex flex-wrap items-center gap-1.5 text-[0.82rem]"
                aria-live="polite"
              >
                <span className="font-medium text-[var(--pa-ink)]">
                  {selectedGroups.length === 0
                    ? "Nessun gruppo scelto"
                    : selectedGroups.length === 1
                      ? "1 gruppo scelto"
                      : `${selectedGroups.length} gruppi scelti`}
                </span>
                {selectedGroups.map((group) => (
                  <button
                    key={group.id}
                    type="button"
                    onClick={() => toggle(group.id)}
                    className="inline-flex max-w-full items-center gap-1 rounded-full border border-[var(--pa-accent)] bg-[var(--pa-bg-tint)] py-0.5 pr-1.5 pl-2.5 text-[0.78rem] font-medium text-[var(--pa-ink)] transition-colors hover:bg-[var(--pa-accent)] hover:text-white"
                    aria-label={`Togli ${group.name}`}
                  >
                    <span className="truncate">{group.name}</span>
                    <XIcon className="size-3.5 shrink-0" aria-hidden />
                  </button>
                ))}
              </div>

              {searchable && (
                <div className="relative">
                  <SearchIcon
                    className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-[var(--pa-muted)]"
                    aria-hidden
                  />
                  <Input
                    type="search"
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder={`Cerca tra ${groups.length} gruppi…`}
                    aria-label="Cerca un gruppo"
                    className="pl-9"
                  />
                </div>
              )}

              {/* Altezza fissa e scorrimento interno: il popup resta della
                  stessa misura con 6 gruppi o con 60, e il bottone di
                  salvataggio non scappa in fondo a una pagina lunghissima. */}
              <div
                className={`rounded-xl border border-[var(--pa-line)] ${
                  searchable ? "max-h-[16rem] overflow-y-auto" : ""
                }`}
              >
                {visibleGroups.length === 0 ? (
                  <p className="px-4 py-6 text-center text-[0.86rem] text-[var(--pa-muted)]">
                    Nessun gruppo corrisponde a «{query.trim()}».{" "}
                    <button
                      type="button"
                      className="pa-link font-medium"
                      onClick={() => setQuery("")}
                    >
                      Mostra tutti
                    </button>
                  </p>
                ) : (
                  <ul className="divide-y divide-[var(--pa-line)]">
                    {visibleGroups.map((group) => {
                      const checked = selected.has(group.id);
                      return (
                        <li key={group.id}>
                          <label
                            className={`flex cursor-pointer items-start gap-3 px-4 py-2.5 transition-colors ${
                              checked ? "bg-[var(--pa-bg-tint)]" : "hover:bg-[var(--pa-bg-tint)]/60"
                            }`}
                          >
                            <input
                              type="checkbox"
                              className="peer sr-only"
                              checked={checked}
                              onChange={() => toggle(group.id)}
                            />
                            <span
                              aria-hidden
                              className={`mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-md border ${
                                checked
                                  ? "border-[var(--pa-accent)] bg-[var(--pa-accent)] text-white"
                                  : "border-[var(--pa-line)] bg-white"
                              }`}
                            >
                              {checked && <CheckIcon className="size-3.5" />}
                            </span>
                            <span className="min-w-0">
                              <span className="block text-[0.95rem] font-semibold text-[var(--pa-ink)]">
                                {group.name}
                              </span>
                              {group.description && (
                                <span className="mt-0.5 block text-[0.84rem] leading-relaxed text-[var(--pa-muted)]">
                                  {group.description}
                                </span>
                              )}
                            </span>
                          </label>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>

              {searchable && query.trim() && visibleGroups.length > 0 && (
                <p className="text-[0.78rem] text-[var(--pa-muted)]">
                  {visibleGroups.length} di {groups.length} gruppi
                </p>
              )}
            </div>
          )}
        </fieldset>
      </div>

      {error && (
        <p role="alert" className="pa-notice pa-notice--error mt-5">
          {error}
        </p>
      )}

      <div className="mt-6 grid gap-3">
        <button type="submit" className="pa-btn" disabled={!canSubmit || pending || groups.length === 0}>
          {pending ? <Loader2Icon className="size-4 animate-spin" /> : <CheckIcon className="size-4" />}
          {submitLabel}
        </button>
        {footnote}
      </div>
    </form>
  );
}
