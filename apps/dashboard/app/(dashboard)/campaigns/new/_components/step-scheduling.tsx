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
import { publishingModeValues, type CampaignWizardValues } from "@/lib/validation/campaigns";

const MODE_LABELS: Record<(typeof publishingModeValues)[number], { label: string; description: string }> = {
  immediate: { label: "Immediata", description: "Pubblica sui canali non appena la campagna viene lanciata." },
  scheduled: { label: "Programmata", description: "Pubblica alla data e ora indicate." },
  buffer_queue: { label: "Coda Buffer", description: "Accoda i post nella coda di pubblicazione di Buffer." },
  draft: { label: "Bozza", description: "Salva la campagna senza lanciarla." },
  approval: { label: "Approvazione", description: "Richiede approvazione manuale prima della pubblicazione." },
};

const TIMEZONES: string[] =
  typeof Intl.supportedValuesOf === "function"
    ? Intl.supportedValuesOf("timeZone")
    : ["UTC", "Europe/Rome", "Europe/Lisbon", "America/New_York"];

export function StepScheduling({ form }: { form: UseFormReturn<CampaignWizardValues> }) {
  const publishingMode = form.watch("publishing_mode");

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
    </div>
  );
}
