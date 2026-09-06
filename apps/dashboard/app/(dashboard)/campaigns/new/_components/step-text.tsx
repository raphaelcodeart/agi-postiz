import type { UseFormReturn } from "react-hook-form";
import { toast } from "sonner";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import {
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormDescription,
  FormMessage,
} from "@/components/ui/form";
import {
  type CampaignWizardValues,
  PLATFORM_HARD_LIMITS,
  REFERRAL_LINK_RESERVED_CHARS,
  PERSONAL_CONTACTS_RESERVED_CHARS,
} from "@/lib/validation/campaigns";
import { AIGenerateDialog } from "./ai-generate-dialog";
import type { AIGenerateTextResponse } from "@/types/api";

const PLATFORM_TABS: { value: keyof CampaignWizardValues; label: string; maxLength: number }[] = [
  { value: "instagram_text", label: "Instagram", maxLength: 5000 },
  { value: "facebook_text", label: "Facebook", maxLength: 5000 },
  { value: "linkedin_text", label: "LinkedIn", maxLength: 5000 },
  { value: "tiktok_text", label: "TikTok", maxLength: 5000 },
  { value: "x_text", label: "X", maxLength: PLATFORM_HARD_LIMITS.x_text },
  { value: "threads_text", label: "Threads", maxLength: PLATFORM_HARD_LIMITS.threads_text },
];

export function StepText({ form }: { form: UseFormReturn<CampaignWizardValues> }) {
  const includeReferralLink = form.watch("include_referral_link");
  const includePersonalContacts = form.watch("include_personal_contacts");
  const reservedChars =
    (includeReferralLink ? REFERRAL_LINK_RESERVED_CHARS : 0) +
    (includePersonalContacts ? PERSONAL_CONTACTS_RESERVED_CHARS : 0);
  function handleGenerated(result: AIGenerateTextResponse) {
    form.setValue("default_text", result.default_text, { shouldDirty: true, shouldValidate: true });
    form.setValue("instagram_text", result.instagram_text, { shouldDirty: true, shouldValidate: true });
    form.setValue("facebook_text", result.facebook_text, { shouldDirty: true, shouldValidate: true });
    form.setValue("linkedin_text", result.linkedin_text, { shouldDirty: true, shouldValidate: true });
    form.setValue("tiktok_text", result.tiktok_text, { shouldDirty: true, shouldValidate: true });
    form.setValue("x_text", result.x_text, { shouldDirty: true, shouldValidate: true });
    form.setValue("threads_text", result.threads_text, { shouldDirty: true, shouldValidate: true });
    form.setValue("youtube_title", result.youtube_title, { shouldDirty: true, shouldValidate: true });
    form.setValue("youtube_description", result.youtube_description, { shouldDirty: true, shouldValidate: true });
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          Scrivi il testo a mano oppure genera una bozza con AI da un argomento e poi modificala.
        </p>
        <AIGenerateDialog
          onGenerated={handleGenerated}
          includeReferralLink={includeReferralLink}
          includePersonalContacts={includePersonalContacts}
        />
      </div>

      <FormField
        control={form.control}
        name="default_text"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Testo predefinito</FormLabel>
            <FormControl>
              <Textarea rows={4} maxLength={5000} placeholder="Testo utilizzato per le piattaforme senza un override specifico" {...field} />
            </FormControl>
            <FormDescription>{(field.value ?? "").length}/5000 caratteri</FormDescription>
            <FormMessage />
          </FormItem>
        )}
      />

      <FormField
        control={form.control}
        name="include_referral_link"
        render={({ field }) => (
          <FormItem>
            <label className="flex items-start gap-2 rounded-md border p-3">
              <FormControl>
                <Checkbox
                  checked={field.value}
                  onCheckedChange={(checked) => {
                    field.onChange(checked);
                    if (!checked) return;
                    // Turning it on can immediately make already-typed X/Threads
                    // text too long for the new reduced limit - warn right away
                    // instead of only discovering it silently when "Avanti"
                    // doesn't advance.
                    const overLimit = (["x_text", "threads_text"] as const).filter((f) => {
                      const limit = PLATFORM_HARD_LIMITS[f] - REFERRAL_LINK_RESERVED_CHARS;
                      return (form.getValues(f) ?? "").length > limit;
                    });
                    if (overLimit.length > 0) {
                      const labels = overLimit.map((f) => (f === "x_text" ? "X" : "Threads")).join(" e ");
                      toast.warning(`Il testo per ${labels} è già troppo lungo per lasciare spazio al link referral - riducilo prima di continuare.`);
                      form.trigger(overLimit);
                    }
                  }}
                  className="mt-0.5"
                />
              </FormControl>
              <span>
                <span className="block text-sm font-medium text-foreground">Includi link referral personale</span>
                <FormDescription>
                  Se attivo, per ogni destinatario viene aggiunto in fondo al testo il suo link referral
                  personale (configurato nella pagina Utenti) — solo il suo, mai quello di altri. Chi non ha un
                  link configurato riceve il testo invariato, esattamente come con questa opzione spenta. I box
                  con un limite reale (X, Threads) si riducono di {REFERRAL_LINK_RESERVED_CHARS} caratteri per
                  lasciare sempre spazio al link.
                </FormDescription>
              </span>
            </label>
          </FormItem>
        )}
      />

      <FormField
        control={form.control}
        name="include_personal_contacts"
        render={({ field }) => (
          <FormItem>
            <label className="flex items-start gap-2 rounded-md border p-3">
              <FormControl>
                <Checkbox
                  checked={field.value}
                  onCheckedChange={(checked) => {
                    field.onChange(checked);
                    if (!checked) return;
                    // Same immediate-warning pattern as "Includi link referral" above.
                    const otherReserved = includeReferralLink ? REFERRAL_LINK_RESERVED_CHARS : 0;
                    const overLimit = (["x_text", "threads_text"] as const).filter((f) => {
                      const limit = PLATFORM_HARD_LIMITS[f] - otherReserved - PERSONAL_CONTACTS_RESERVED_CHARS;
                      return (form.getValues(f) ?? "").length > limit;
                    });
                    if (overLimit.length > 0) {
                      const labels = overLimit.map((f) => (f === "x_text" ? "X" : "Threads")).join(" e ");
                      toast.warning(`Il testo per ${labels} è già troppo lungo per lasciare spazio ai contatti personali - riducilo prima di continuare.`);
                      form.trigger(overLimit);
                    }
                  }}
                  className="mt-0.5"
                />
              </FormControl>
              <span>
                <span className="block text-sm font-medium text-foreground">Includi contatti personali</span>
                <FormDescription>
                  Se attivo, per ogni destinatario viene aggiunto in fondo al testo (subito dopo l&apos;eventuale
                  link referral) il suo blocco di contatti personali/firma (configurato nella pagina Utenti) —
                  solo il suo, mai quello di altri. Chi non ha contatti configurati riceve il testo invariato,
                  esattamente come con questa opzione spenta. I box con un limite reale (X, Threads) si riducono
                  di altri {PERSONAL_CONTACTS_RESERVED_CHARS} caratteri per lasciare sempre spazio al blocco.
                </FormDescription>
              </span>
            </label>
          </FormItem>
        )}
      />

      <div className="space-y-2">
        <p className="text-sm font-medium text-foreground">Override per piattaforma (opzionale)</p>
        <Tabs defaultValue="instagram_text">
          <TabsList>
            {PLATFORM_TABS.map((tab) => (
              <TabsTrigger key={tab.value} value={tab.value}>
                {tab.label}
              </TabsTrigger>
            ))}
            <TabsTrigger value="youtube">YouTube</TabsTrigger>
          </TabsList>
          {PLATFORM_TABS.map((tab) => {
            const hasHardLimit = tab.value === "x_text" || tab.value === "threads_text";
            const effectiveMax = hasHardLimit ? tab.maxLength - reservedChars : tab.maxLength;
            return (
              <TabsContent key={tab.value} value={tab.value} className="pt-3">
                <FormField
                  control={form.control}
                  name={tab.value}
                  render={({ field }) => (
                    <FormItem>
                      <FormControl>
                        <Textarea
                          rows={3}
                          maxLength={effectiveMax}
                          placeholder={`Testo specifico per ${tab.label} (lascia vuoto per usare il testo predefinito)`}
                          {...field}
                          value={(field.value as string) ?? ""}
                        />
                      </FormControl>
                      <FormDescription>
                        {((field.value as string) ?? "").length}/{effectiveMax} caratteri
                        {hasHardLimit && reservedChars > 0 && (
                          <> (ridotto da {tab.maxLength} per lasciare spazio a link referral e/o contatti personali)</>
                        )}
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </TabsContent>
            );
          })}
          <TabsContent value="youtube" className="space-y-3 pt-3">
            <FormField
              control={form.control}
              name="youtube_title"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Titolo YouTube</FormLabel>
                  <FormControl>
                    <Input maxLength={100} {...field} value={(field.value as string) ?? ""} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="youtube_description"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Descrizione YouTube</FormLabel>
                  <FormControl>
                    <Textarea rows={3} maxLength={5000} {...field} value={(field.value as string) ?? ""} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
