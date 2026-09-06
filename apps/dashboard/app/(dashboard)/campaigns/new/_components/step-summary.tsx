import { useEffect } from "react";
import type { UseFormReturn } from "react-hook-form";
import { AlertTriangleIcon } from "lucide-react";
import { PlatformDistributionChart } from "@/components/shared/platform-distribution-chart";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { usePreviewCampaignTargets } from "@/hooks/use-campaigns";
import { toCampaignCreatePayload, type CampaignWizardValues } from "@/lib/validation/campaigns";
import { formatDateTime } from "@/lib/format";

export function StepSummary({ form }: { form: UseFormReturn<CampaignWizardValues> }) {
  const preview = usePreviewCampaignTargets();
  const values = form.watch();

  useEffect(() => {
    preview.mutate(toCampaignCreatePayload(values));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="space-y-1 rounded-lg border p-3">
          <p className="text-xs text-muted-foreground">Titolo</p>
          <p className="text-sm font-medium">{values.title || "—"}</p>
        </div>
        <div className="space-y-1 rounded-lg border p-3">
          <p className="text-xs text-muted-foreground">Modalità di pubblicazione</p>
          <p className="text-sm font-medium capitalize">{values.publishing_mode}</p>
        </div>
        {values.publishing_mode === "scheduled" && (
          <div className="space-y-1 rounded-lg border p-3 sm:col-span-2">
            <p className="text-xs text-muted-foreground">Programmata per</p>
            <p className="text-sm font-medium">
              {values.scheduled_at ? formatDateTime(new Date(values.scheduled_at).toISOString(), values.timezone) : "—"}{" "}
              ({values.timezone})
            </p>
          </div>
        )}
        <div className="space-y-1 rounded-lg border p-3 sm:col-span-2">
          <p className="text-xs text-muted-foreground">Testo predefinito</p>
          <p className="line-clamp-3 text-sm">{values.default_text || "—"}</p>
        </div>
      </div>

      <div className="space-y-3 rounded-lg border p-4">
        <p className="text-sm font-medium">Anteprima destinatari</p>
        {preview.isPending && <p className="text-sm text-muted-foreground">Calcolo dei destinatari in corso...</p>}
        {preview.isError && (
          <Alert variant="destructive">
            <AlertDescription>Impossibile calcolare l&apos;anteprima dei destinatari.</AlertDescription>
          </Alert>
        )}
        {preview.data && (
          <>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <div>
                <p className="text-2xl font-semibold tabular-nums">{preview.data.estimated_publications_count}</p>
                <p className="text-xs text-muted-foreground">Pubblicazioni stimate</p>
              </div>
              <div>
                <p className="text-2xl font-semibold tabular-nums">{preview.data.total_users_targeted}</p>
                <p className="text-xs text-muted-foreground">Utenti coinvolti</p>
              </div>
              <div>
                <p className="text-2xl font-semibold tabular-nums">
                  {preview.data.channels_requiring_notification_approval}
                </p>
                <p className="text-xs text-muted-foreground">Richiedono approvazione</p>
              </div>
            </div>
            <PlatformDistributionChart distribution={preview.data.platform_distribution} />
            {preview.data.excluded_channels_count > 0 && (
              <Alert>
                <AlertTriangleIcon className="size-4" />
                <AlertDescription>
                  {preview.data.excluded_channels_count} canali attivi non riceveranno questa campagna in base ai
                  criteri di targeting selezionati.
                </AlertDescription>
              </Alert>
            )}
            {preview.data.estimated_publications_count === 0 && (
              <Alert variant="destructive">
                <AlertDescription>
                  Nessun canale corrisponde ai criteri selezionati. La campagna non potrà essere lanciata finché non
                  modifichi i destinatari.
                </AlertDescription>
              </Alert>
            )}
          </>
        )}
      </div>
    </div>
  );
}
