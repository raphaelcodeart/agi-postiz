"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Loader2Icon, UserCheckIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { usePlatformSettings, useUpdatePlatformSettings } from "@/hooks/use-settings";
import { ApiError } from "@/lib/api/errors";
import type { PlatformSettingsResponse } from "@/types/api";

/** Shown while the settings are still loading; never submitted. */
const EMPTY: PlatformSettingsResponse = {
  affiliate_disclosure_text: "",
  affiliate_disclosure_text_short: "",
  auto_activate_new_users: true,
};

/**
 * Platform behaviour that is a policy decision rather than a tuning parameter,
 * which is why it sits apart from the concurrency numbers below.
 *
 * Both settings here used to be code: registration hardcoded "inactive", and the
 * affiliate wording lived in a constant with no way to edit it. Both are
 * decisions somebody other than a developer has to be able to make - one
 * operational, one legal.
 */
export function PlatformSettingsCard() {
  const query = usePlatformSettings();
  const update = useUpdatePlatformSettings();

  // The form is the server value until the administrator touches it, and their
  // draft from then on. Deriving it rather than copying it into state on load
  // means a background refetch mid-edit cannot revert what they just typed, and
  // there is no effect to keep in sync in the first place.
  const [draft, setDraft] = useState<PlatformSettingsResponse | null>(null);
  const values = draft ?? query.data ?? EMPTY;
  const dirty = draft !== null;

  function edit(patch: Partial<PlatformSettingsResponse>) {
    setDraft({ ...values, ...patch });
  }

  function save() {
    update.mutate(
      {
        auto_activate_new_users: values.auto_activate_new_users,
        affiliate_disclosure_text: values.affiliate_disclosure_text,
        affiliate_disclosure_text_short: values.affiliate_disclosure_text_short,
      },
      {
        onSuccess: () => {
          setDraft(null);
          toast.success("Impostazioni della piattaforma aggiornate");
        },
        onError: (error) =>
          toast.error(error instanceof ApiError ? error.detail : "Aggiornamento non riuscito"),
      }
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Piattaforma</CardTitle>
        <CardDescription>
          Regole di funzionamento che valgono per tutti gli utenti e tutte le campagne.
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-6">
        {query.isLoading ? (
          <Skeleton className="h-40" />
        ) : (
          <>
            <div className="flex items-start justify-between gap-4 rounded-lg border p-4">
              <div className="space-y-1">
                <Label className="flex items-center gap-2">
                  <UserCheckIcon className="size-4" />
                  Attiva automaticamente i nuovi utenti
                </Label>
                <p className="text-sm text-muted-foreground">
                  {values.auto_activate_new_users
                    ? "Chi si registra dal portale è subito incluso nelle campagne. Può comunque togliersi da ogni campagna in palinsesto prima dell'avvio."
                    : "Chi si registra resta in attesa e va attivato a mano dalla pagina Utenti. Chi collega un canale viene attivato comunque."}
                </p>
              </div>
              <Switch
                checked={values.auto_activate_new_users}
                onCheckedChange={(value) => edit({ auto_activate_new_users: value })}
              />
            </div>

            <div className="space-y-4 rounded-lg border p-4">
              <div className="space-y-1">
                <Label htmlFor="disclosure">Dichiarazione di affiliazione</Label>
                <p className="text-sm text-muted-foreground">
                  Testo aggiunto in fondo ai post delle campagne che hanno attivo &quot;Includi
                  dichiarazione affiliazione&quot;.
                </p>
              </div>
              <Input
                id="disclosure"
                value={values.affiliate_disclosure_text}
                maxLength={500}
                onChange={(event) => edit({ affiliate_disclosure_text: event.target.value })}
              />

              <div className="space-y-1">
                <Label htmlFor="disclosure-short">Versione breve</Label>
                <p className="text-sm text-muted-foreground">
                  Usata dove lo spazio è poco: su X restano 280 caratteri in tutto.
                </p>
              </div>
              <Input
                id="disclosure-short"
                value={values.affiliate_disclosure_text_short}
                maxLength={120}
                onChange={(event) => edit({ affiliate_disclosure_text_short: event.target.value })}
              />
            </div>

            <Button disabled={!dirty || update.isPending} onClick={save}>
              {update.isPending && <Loader2Icon className="size-4 animate-spin" />}
              Salva impostazioni piattaforma
            </Button>
          </>
        )}
      </CardContent>
    </Card>
  );
}
