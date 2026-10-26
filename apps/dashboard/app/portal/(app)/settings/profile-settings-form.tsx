"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { PortalGroup } from "@/lib/portal/server";
import { PortalProfileForm } from "../profile-form";

/**
 * Il modulo del profilo dentro le Impostazioni.
 *
 * Rispetto al popup cambia solo cosa succede dopo il salvataggio: niente
 * ricarica, un avviso di conferma e un router.refresh() perche' il layout
 * (che legge /me sul server) rifletta i nuovi dati senza far perdere la
 * posizione nella pagina.
 */
export function ProfileSettingsForm({
  groups,
  initialCity,
  initialPostalCode,
  initialGroupIds,
}: {
  groups: PortalGroup[];
  initialCity: string | null;
  initialPostalCode: string | null;
  initialGroupIds: string[];
}) {
  const router = useRouter();
  const [saved, setSaved] = useState(false);

  return (
    <div className="grid gap-4">
      {saved && (
        <p role="status" className="pa-notice pa-notice--ok">
          Profilo aggiornato. Da ora le campagne ti raggiungono attraverso i gruppi che hai scelto.
        </p>
      )}
      <PortalProfileForm
        groups={groups}
        initialCity={initialCity}
        initialPostalCode={initialPostalCode}
        initialGroupIds={initialGroupIds}
        submitLabel="Salva modifiche"
        onSaved={() => {
          setSaved(true);
          router.refresh();
        }}
        footnote={
          <p className="text-[0.8rem] leading-relaxed text-[var(--pa-muted)]">
            I gruppi scelti sostituiscono quelli attuali: togliendone uno non riceverai più le campagne rivolte
            solo a quel gruppo.
          </p>
        }
      />
    </div>
  );
}
