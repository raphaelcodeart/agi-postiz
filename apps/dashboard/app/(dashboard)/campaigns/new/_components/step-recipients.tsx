import type { UseFormReturn } from "react-hook-form";
import { cn } from "@/lib/utils";
import { Checkbox } from "@/components/ui/checkbox";
import { PlatformBadge } from "@/components/shared/platform-badge";
import { FormField, FormItem, FormMessage } from "@/components/ui/form";
import { useUsers, useGroups } from "@/hooks/use-users";
import { useChannels } from "@/hooks/use-channels";
import { targetingModeValues, type CampaignWizardValues } from "@/lib/validation/campaigns";

const MODE_LABELS: Record<(typeof targetingModeValues)[number], { label: string; description: string }> = {
  all_active_channels: {
    label: "Tutti i canali attivi",
    description: "Pubblica su tutti i canali social attivi con connessione Buffer valida.",
  },
  selected_users: { label: "Utenti selezionati", description: "Scegli manualmente uno o più utenti." },
  selected_groups: { label: "Gruppi selezionati", description: "Scegli uno o più gruppi di utenti." },
  selected_channels: { label: "Canali selezionati", description: "Scegli manualmente i singoli canali social." },
  selected_platforms: { label: "Piattaforme selezionate", description: "Pubblica solo su determinate piattaforme." },
};

const PLATFORMS = ["instagram", "facebook", "linkedin", "tiktok", "youtube", "twitter", "threads"];

function PlatformCheckboxList({
  selected,
  onToggle,
}: {
  selected: string[];
  onToggle: (platform: string, checked: boolean) => void;
}) {
  return (
    <div className="flex flex-wrap gap-3 rounded-md border p-3">
      {PLATFORMS.map((platform) => (
        <label key={platform} className="flex items-center gap-2 text-sm">
          <Checkbox checked={selected.includes(platform)} onCheckedChange={(value) => onToggle(platform, !!value)} />
          <PlatformBadge platform={platform} />
        </label>
      ))}
    </div>
  );
}

function CheckboxList<T extends { id: string }>({
  items,
  selected,
  onToggle,
  renderLabel,
}: {
  items: T[];
  selected: string[];
  onToggle: (id: string, checked: boolean) => void;
  renderLabel: (item: T) => React.ReactNode;
}) {
  return (
    <div className="max-h-64 space-y-2 overflow-y-auto rounded-md border p-3">
      {items.length === 0 && <p className="text-sm text-muted-foreground">Nessun elemento disponibile.</p>}
      {items.map((item) => (
        <label key={item.id} className="flex items-center gap-2 text-sm">
          <Checkbox
            checked={selected.includes(item.id)}
            onCheckedChange={(checked) => onToggle(item.id, !!checked)}
          />
          {renderLabel(item)}
        </label>
      ))}
    </div>
  );
}

// These three modes select *who* is targeted; the platform filter below then
// optionally narrows *which* of their channels get included. The other two
// modes don't combine with it: "selected_channels" is already an explicit
// channel-by-channel pick, and "selected_platforms" already is the filter.
const PLATFORM_FILTER_COMPATIBLE_MODES = new Set(["all_active_channels", "selected_users", "selected_groups"]);

export function StepRecipients({ form }: { form: UseFormReturn<CampaignWizardValues> }) {
  const targetingMode = form.watch("targeting_mode");
  const usersQuery = useUsers({ status_filter: "active", limit: 100 });
  const groupsQuery = useGroups();
  const channelsQuery = useChannels({});

  const userNames = new Map((usersQuery.data ?? []).map((user) => [user.id, user.name]));

  return (
    <div className="space-y-4">
      <FormField
        control={form.control}
        name="targeting_mode"
        render={({ field }) => (
          <FormItem>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {targetingModeValues.map((mode) => (
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

      {targetingMode === "selected_users" && (
        <FormField
          control={form.control}
          name="user_ids"
          render={({ field }) => (
            <FormItem>
              <CheckboxList
                items={usersQuery.data ?? []}
                selected={field.value ?? []}
                onToggle={(id, checked) =>
                  field.onChange(checked ? [...(field.value ?? []), id] : (field.value ?? []).filter((v) => v !== id))
                }
                renderLabel={(user) => (
                  <span>
                    {user.name} <span className="text-muted-foreground">({user.email})</span>
                  </span>
                )}
              />
              <FormMessage />
            </FormItem>
          )}
        />
      )}

      {targetingMode === "selected_groups" && (
        <FormField
          control={form.control}
          name="group_ids"
          render={({ field }) => (
            <FormItem>
              <CheckboxList
                items={groupsQuery.data ?? []}
                selected={field.value ?? []}
                onToggle={(id, checked) =>
                  field.onChange(checked ? [...(field.value ?? []), id] : (field.value ?? []).filter((v) => v !== id))
                }
                renderLabel={(group) => group.name}
              />
              <FormMessage />
            </FormItem>
          )}
        />
      )}

      {targetingMode === "selected_channels" && (
        <FormField
          control={form.control}
          name="channel_ids"
          render={({ field }) => (
            <FormItem>
              <CheckboxList
                items={channelsQuery.data ?? []}
                selected={field.value ?? []}
                onToggle={(id, checked) =>
                  field.onChange(checked ? [...(field.value ?? []), id] : (field.value ?? []).filter((v) => v !== id))
                }
                renderLabel={(channel) => (
                  <span className="flex items-center gap-2">
                    <PlatformBadge platform={channel.platform} />
                    {channel.name}
                    <span className="text-muted-foreground">
                      ({userNames.get(channel.user_id) ?? "utente sconosciuto"})
                    </span>
                  </span>
                )}
              />
              <FormMessage />
            </FormItem>
          )}
        />
      )}

      {targetingMode === "selected_platforms" && (
        <FormField
          control={form.control}
          name="platform_names"
          render={({ field }) => (
            <FormItem>
              <PlatformCheckboxList
                selected={field.value ?? []}
                onToggle={(platform, checked) => {
                  const current = field.value ?? [];
                  field.onChange(checked ? [...current, platform] : current.filter((p) => p !== platform));
                }}
              />
              <FormMessage />
            </FormItem>
          )}
        />
      )}

      {PLATFORM_FILTER_COMPATIBLE_MODES.has(targetingMode) && (
        <FormField
          control={form.control}
          name="platform_names"
          render={({ field }) => (
            <FormItem>
              <div>
                <p className="text-sm font-medium">Filtra per piattaforma (opzionale)</p>
                <p className="text-xs text-muted-foreground">
                  Lascia tutto deselezionato per pubblicare su tutti i canali collegati. Seleziona una o più
                  piattaforme per pubblicare solo su quelle, anche se l&apos;utente/gruppo ne ha altre collegate.
                </p>
              </div>
              <PlatformCheckboxList
                selected={field.value ?? []}
                onToggle={(platform, checked) => {
                  const current = field.value ?? [];
                  field.onChange(checked ? [...current, platform] : current.filter((p) => p !== platform));
                }}
              />
              <FormMessage />
            </FormItem>
          )}
        />
      )}
    </div>
  );
}
