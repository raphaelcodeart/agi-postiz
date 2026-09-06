import type { UseFormReturn } from "react-hook-form";
import { Input } from "@/components/ui/input";
import { FormControl, FormField, FormItem, FormLabel, FormDescription, FormMessage } from "@/components/ui/form";
import type { CampaignWizardValues } from "@/lib/validation/campaigns";

export function StepInfo({ form }: { form: UseFormReturn<CampaignWizardValues> }) {
  return (
    <div className="space-y-4">
      <FormField
        control={form.control}
        name="title"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Titolo campagna</FormLabel>
            <FormControl>
              <Input placeholder="Es. Promozione estiva 2026" {...field} />
            </FormControl>
            <FormDescription>Uso interno: identifica la campagna negli elenchi e nei report.</FormDescription>
            <FormMessage />
          </FormItem>
        )}
      />
    </div>
  );
}
