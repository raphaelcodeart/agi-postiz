import type { UseFormReturn } from "react-hook-form";
import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Switch } from "@/components/ui/switch";
import { publishingModeValues, type CampaignWizardValues } from "@/lib/validation/campaigns";

const MODE_LABELS: Record<(typeof publishingModeValues)[number], { label: string; description: string }> = {
  immediate: { label: "Immediata", description: "Pubblica sui canali non appena la campagna viene lanciata." },
  scheduled: { label: "Programmata", description: "Pubblica alla data e ora indicate." },
  buffer_queue: { label: "Coda Agi Post", description: "Accoda i post nella coda di pubblicazione." },
  draft: { label: "Bozza", description: "Salva la campagna senza lanciarla." },
  approval: { label: "Approvazione", description: "Richiede approvazione manuale prima della pubblicazione." },
};

const TIMEZONES: string[] =
  typeof Intl.supportedValuesOf === "function"
    ? Intl.supportedValuesOf("timeZone")
    : ["UTC", "Europe/Rome", "Europe/Lisbon", "America/New_York"];

const PARTICIPATION_MODES = [
  {
    value: "automatic" as const,
    label: "Diretta",
    description: "La campagna raggiunge tutti i destinatari selezionati, senza preavviso.",
  },
  {
    value: "opt_out" as const,
    label: "Con adesione (palinsesto)",
    description:
      "I destinatari la vedono in anticipo e possono togliersi prima dell'avvio. Altri utenti possono aggiungersi.",
  },
];

export function StepScheduling({ form }: { form: UseFormReturn<CampaignWizardValues> }) {
  const publishingMode = form.watch("publishing_mode");
  const participationMode = form.watch("participation_mode");

  return (
    <div className="space-y-4">
      <FormField
        control={form.control}
        name="publishing_mode"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Modalità di pubblicazione</FormLabel>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {publishingModeValues.map((mode) => (
                <button
                  type="button"
                  key={mode}
                  onClick={() => field.onChange(mode)}
                  className={cn(
                    "rounded-lg border p-3 text-left",
                    field.value === mode && "border-primary bg-primary/5"
                  )}
                >
                  <p className="text-sm font-medium">{MODE_LABELS[mode].label}</p>
                  <p className="text-xs text-muted-foreground">{MODE_LABELS[mode].description}</p>
                </button>
              ))}
            </div>
            <FormMessage />
          </FormItem>
        )}
      />

      {publishingMode === "scheduled" && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormField
            control={form.control}
            name="scheduled_at"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Data e ora</FormLabel>
                <FormControl>
                  <Input type="datetime-local" {...field} value={(field.value as string) ?? ""} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="timezone"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Fuso orario</FormLabel>
                <Select value={field.value} onValueChange={field.onChange}>
                  <FormControl>
                    <SelectTrigger className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent className="max-h-64">
                    {TIMEZONES.map((tz) => (
                      <SelectItem key={tz} value={tz}>
                        {tz}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>
      )}

      {/* Participation. Placed after scheduling because the deadline only makes
          sense relative to the publishing date - and because the validation ties
          the two together. */}
      <div className="border-t pt-4">
        <FormField
          control={form.control}
          name="participation_mode"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Partecipazione dei destinatari</FormLabel>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {PARTICIPATION_MODES.map((mode) => (
                  <button
                    type="button"
                    key={mode.value}
                    onClick={() => field.onChange(mode.value)}
                    className={cn(
                      "rounded-lg border p-3 text-left",
                      field.value === mode.value && "border-primary bg-primary/5"
                    )}
                  >
                    <p className="text-sm font-medium">{mode.label}</p>
                    <p className="text-xs text-muted-foreground">{mode.description}</p>
                  </button>
                ))}
              </div>
              <FormMessage />
            </FormItem>
          )}
        />
      </div>

      {participationMode === "opt_out" && (
        <div className="space-y-4 rounded-lg border border-primary/30 bg-primary/5 p-4">
          <p className="text-sm text-muted-foreground">
            La campagna resta in bozza e viene mostrata ai destinatari nel loro palinsesto.
            Nessun post viene inviato finché non la lanci.
          </p>

          <FormField
            control={form.control}
            name="opt_out_deadline_at"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Termine per ritirarsi</FormLabel>
                <FormControl>
                  <Input
                    type="datetime-local"
                    {...field}
                    value={(field.value as string) ?? ""}
                  />
                </FormControl>
                <p className="text-xs text-muted-foreground">
                  Fino a questo momento i destinatari possono togliersi dalla campagna o
                  aggiungersi. Lascia vuoto per tenere aperto fino al lancio.
                </p>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="auto_launch_at_deadline"
            render={({ field }) => (
              <FormItem className="flex items-start justify-between gap-4 rounded-lg border bg-background p-3">
                <div className="space-y-0.5">
                  <FormLabel>Avvia automaticamente alla scadenza</FormLabel>
                  <p className="text-xs text-muted-foreground">
                    {field.value
                      ? "Allo scadere del termine la campagna parte da sola con i canali rimasti."
                      : "La campagna resta ferma alla scadenza: la lanci tu con il pulsante Lancia."}
                  </p>
                </div>
                <FormControl>
                  <Switch checked={field.value} onCheckedChange={field.onChange} />
                </FormControl>
              </FormItem>
            )}
          />
        </div>
      )}
    </div>
  );
}
