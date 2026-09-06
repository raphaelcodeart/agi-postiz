"use client";

import Link from "next/link";
import {
  UsersIcon,
  UsersRoundIcon,
  LinkIcon,
  Share2Icon,
  ImagesIcon,
  MegaphoneIcon,
  SendIcon,
  AlertOctagonIcon,
  SettingsIcon,
  XCircleIcon,
  RotateCcwIcon,
  TrendingUpIcon,
  type LucideIcon,
} from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { StatCard } from "@/components/shared/stat-card";
import { StatusBadge } from "@/components/shared/status-badge";
import { EmptyState } from "@/components/shared/empty-state";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useUsers } from "@/hooks/use-users";
import { useBufferConnections } from "@/hooks/use-buffer-connections";
import { useChannels } from "@/hooks/use-channels";
import { useCampaigns } from "@/hooks/use-campaigns";
import { usePublications } from "@/hooks/use-publications";
import { formatCappedCount, formatDateTime, formatPercentage } from "@/lib/format";
import { cn } from "@/lib/utils";

const LIST_CAP = 100;

interface QuickAction {
  href: string;
  label: string;
  description: string;
  icon: LucideIcon;
  toneClass: string;
}

const QUICK_ACTIONS: QuickAction[] = [
  { href: "/campaigns", label: "Campagne", description: "Crea e monitora", icon: MegaphoneIcon, toneClass: "bg-chart-1/12 text-chart-1" },
  { href: "/publications", label: "Pubblicazioni", description: "Stato invii", icon: SendIcon, toneClass: "bg-chart-2/12 text-chart-2" },
  { href: "/media", label: "Media", description: "Foto e video", icon: ImagesIcon, toneClass: "bg-chart-3/12 text-chart-3" },
  { href: "/channels", label: "Canali social", description: "Profili collegati", icon: Share2Icon, toneClass: "bg-chart-4/12 text-chart-4" },
  { href: "/buffer-connections", label: "Connessioni Buffer", description: "Account collegati", icon: LinkIcon, toneClass: "bg-chart-5/12 text-chart-5" },
  { href: "/users", label: "Utenti", description: "Clienti e amici", icon: UsersIcon, toneClass: "bg-chart-1/12 text-chart-1" },
  { href: "/groups", label: "Gruppi", description: "Segmenti utenti", icon: UsersRoundIcon, toneClass: "bg-chart-2/12 text-chart-2" },
  { href: "/errors", label: "Centro errori", description: "Problemi da risolvere", icon: AlertOctagonIcon, toneClass: "bg-chart-3/12 text-chart-3" },
  { href: "/settings", label: "Impostazioni", description: "Configurazione", icon: SettingsIcon, toneClass: "bg-chart-4/12 text-chart-4" },
];

function QuickActionsGrid() {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      {QUICK_ACTIONS.map((action, index) => (
        <Link
          key={action.href}
          href={action.href}
          style={{ animationDelay: `${index * 40}ms` }}
          className="group animate-in fade-in slide-in-from-bottom-2 fill-mode-both flex flex-col items-center gap-2.5 rounded-xl border bg-card p-4 text-center transition-all duration-300 hover:-translate-y-1 hover:border-transparent hover:shadow-lg hover:shadow-primary/10"
        >
          <div
            className={cn(
              "flex size-12 items-center justify-center rounded-2xl transition-transform duration-300 group-hover:scale-110",
              action.toneClass
            )}
          >
            <action.icon className="size-6" />
          </div>
          <div className="space-y-0.5">
            <p className="text-sm font-medium text-foreground">{action.label}</p>
            <p className="text-xs text-muted-foreground">{action.description}</p>
          </div>
        </Link>
      ))}
    </div>
  );
}

export default function DashboardOverviewPage() {
  const activeUsers = useUsers({ status_filter: "active", limit: LIST_CAP });
  const connections = useBufferConnections();
  const channels = useChannels({});
  const runningCampaigns = useCampaigns({ status_filter: "running", limit: LIST_CAP });
  const recentCampaigns = useCampaigns({ limit: 5 });
  const publishedPubs = usePublications({ status_filter: "published", limit: LIST_CAP });
  const failedPubs = usePublications({ status_filter: "failed", limit: LIST_CAP });
  const retryWaitPubs = usePublications({ status_filter: "retry_wait", limit: LIST_CAP });

  const connectedConnections = connections.data?.filter((c) => c.status === "connected").length;
  const activeChannels = channels.data?.filter((c) => c.is_active).length;

  const publishedCount = publishedPubs.data?.length ?? 0;
  const failedCount = failedPubs.data?.length ?? 0;
  const denominator = publishedCount + failedCount;
  const successRate = denominator > 0 ? (publishedCount / denominator) * 100 : null;

  const isLoadingStats =
    activeUsers.isLoading || connections.isLoading || channels.isLoading || runningCampaigns.isLoading;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard"
        description="Panoramica in tempo reale della piattaforma di pubblicazione"
        actions={
          <Button asChild>
            <Link href="/campaigns/new">Nuova campagna</Link>
          </Button>
        }
      />

      <QuickActionsGrid />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Utenti attivi"
          value={formatCappedCount(activeUsers.data?.length, LIST_CAP)}
          icon={UsersIcon}
          loading={isLoadingStats}
        />
        <StatCard
          label="Account Buffer collegati"
          value={connectedConnections ?? "—"}
          hint={connections.data ? `su ${connections.data.length} totali` : undefined}
          icon={LinkIcon}
          loading={isLoadingStats}
        />
        <StatCard
          label="Canali social attivi"
          value={activeChannels ?? "—"}
          hint={channels.data ? `su ${channels.data.length} totali` : undefined}
          icon={Share2Icon}
          loading={isLoadingStats}
        />
        <StatCard
          label="Campagne in esecuzione"
          value={formatCappedCount(runningCampaigns.data?.length, LIST_CAP)}
          icon={MegaphoneIcon}
          loading={isLoadingStats}
        />
        <StatCard
          label="Pubblicazioni completate"
          value={formatCappedCount(publishedPubs.data?.length, LIST_CAP)}
          icon={SendIcon}
          tone="success"
          loading={publishedPubs.isLoading}
        />
        <StatCard
          label="Pubblicazioni fallite"
          value={formatCappedCount(failedPubs.data?.length, LIST_CAP)}
          icon={XCircleIcon}
          tone="destructive"
          loading={failedPubs.isLoading}
        />
        <StatCard
          label="Retry in attesa"
          value={formatCappedCount(retryWaitPubs.data?.length, LIST_CAP)}
          icon={RotateCcwIcon}
          tone="warning"
          loading={retryWaitPubs.isLoading}
        />
        <StatCard
          label="Tasso di successo"
          value={successRate === null ? "—" : formatPercentage(successRate)}
          hint="Pubblicate vs fallite (ultime 100)"
          icon={TrendingUpIcon}
          tone="success"
          loading={publishedPubs.isLoading || failedPubs.isLoading}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Campagne recenti</CardTitle>
          </CardHeader>
          <CardContent>
            {recentCampaigns.data && recentCampaigns.data.length > 0 ? (
              <ul className="divide-y">
                {recentCampaigns.data.map((campaign) => (
                  <li key={campaign.id} className="py-2.5 first:pt-0 last:pb-0">
                    <Link
                      href={`/campaigns/${campaign.id}`}
                      className="flex items-center justify-between gap-3 hover:underline"
                    >
                      <span className="min-w-0 truncate text-sm font-medium">{campaign.title}</span>
                      <span className="flex shrink-0 items-center gap-2">
                        <span className="text-xs text-muted-foreground">
                          {formatDateTime(campaign.created_at)}
                        </span>
                        <StatusBadge status={campaign.status} />
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState title="Nessuna campagna ancora creata" />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Errori recenti</CardTitle>
          </CardHeader>
          <CardContent>
            {failedPubs.data && failedPubs.data.length > 0 ? (
              <ul className="divide-y">
                {failedPubs.data.slice(0, 5).map((pub) => (
                  <li key={pub.id} className="py-2.5 first:pt-0 last:pb-0">
                    <Link
                      href={`/publications/${pub.id}`}
                      className="flex items-center justify-between gap-3 hover:underline"
                    >
                      <span className="min-w-0 flex-1 truncate text-sm">
                        {pub.error_message ?? "Errore non specificato"}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {formatDateTime(pub.updated_at)}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState title="Nessun errore recente" />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
