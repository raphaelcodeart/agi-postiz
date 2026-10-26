"use client";

import { useEffect, useMemo } from "react";
import { MapPinIcon } from "lucide-react";
import type { PortalGroup } from "@/lib/portal/server";
import { PortalProfileForm } from "./profile-form";

/**
 * La finestra del primo accesso: citta', codice postale e gruppi.
 *
 * Si para davanti a chi ha confermato l'indirizzo ma non ha ancora detto da
 * dove scrive e a quali gruppi vuole partecipare. Come la finestra di conferma
 * email, non si chiude: un passaggio facoltativo verrebbe saltato, e ci
 * ritroveremmo con promoter fuori da ogni gruppo, che nessuna campagna mirata
 * raggiungerebbe mai.
 *
 * Anche qui vale la stessa avvertenza: e' una comodita', non un controllo. Il
 * blocco sta nell'API (get_verified_portal_user risponde 403 profile_incomplete
 * a ogni rotta del portale finche' il profilo non e' salvato); questa finestra
 * serve a spiegare cosa manca e a raccoglierlo in un colpo solo.
 *
 * I gruppi arrivano dal server gia' caricati (layout.tsx): la finestra si apre
 * completa, senza un secondo stato di attesa dentro il primo. Il modulo vero e'
 * PortalProfileForm, lo stesso della pagina Impostazioni: qui c'e' solo la
 * cornice e il testo del primo incontro.
 */
export function PortalProfileGate({
  userName,
  groups,
  initialCity,
  initialPostalCode,
  initialGroupIds,
}: {
  userName: string;
  groups: PortalGroup[];
  initialCity: string | null;
  initialPostalCode: string | null;
  initialGroupIds: string[];
}) {
  const firstName = useMemo(() => userName.trim().split(" ")[0] || userName, [userName]);

  // Con la finestra aperta la pagina sotto non deve scorrere: lo sfondo e'
  // decorativo, e lasciarlo scorrevole darebbe l'impressione di poterci
  // arrivare.
  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, []);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="portal-profile-gate-title"
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-[rgba(20,19,26,0.55)] px-4 py-8 backdrop-blur-sm sm:items-center"
    >
      <div className="pa-card w-full max-w-[34rem] px-6 py-8 sm:px-9">
        <div className="mb-5 flex size-14 items-center justify-center rounded-full bg-[var(--pa-bg-tint)]">
          <MapPinIcon className="size-6 text-[var(--pa-accent)]" aria-hidden />
        </div>

        <h2 id="portal-profile-gate-title" className="pa-title text-[1.45rem]">
          Ciao {firstName}, ancora due cose e sei dentro
        </h2>
        <p className="mt-3 mb-6 text-[0.95rem] leading-relaxed text-[var(--pa-ink-2)]">
          Per includerti nelle campagne giuste ci servono la tua zona e i gruppi a cui vuoi partecipare. Ci vuole un
          minuto, e lo chiediamo una volta sola.
        </p>

        <PortalProfileForm
          groups={groups}
          initialCity={initialCity}
          initialPostalCode={initialPostalCode}
          initialGroupIds={initialGroupIds}
          submitLabel="Salva e entra nel portale"
          // Ricarica piena e non router.refresh(): il layout e' un server
          // component che ha gia' deciso di mostrare la finestra, e va
          // rivalutato da capo con il profilo salvato.
          onSaved={() => window.location.reload()}
          footnote={
            <p className="text-center text-[0.8rem] leading-relaxed text-[var(--pa-muted)]">
              Finché non completi questo passaggio la tua area resta chiusa e non puoi collegare i canali social.
              Potrai cambiare zona e gruppi in qualsiasi momento dalle Impostazioni.
            </p>
          }
        />
      </div>
    </div>
  );
}
