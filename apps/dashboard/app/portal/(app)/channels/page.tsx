import { redirect } from "next/navigation";
import { ExternalLinkIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { PlatformIcon } from "@/components/shared/platform-badge";
import { portalFetch, type PortalChannel, type PortalUser } from "@/lib/portal/server";
import { ConnectChannelPanel } from "./connect-panel";

export const dynamic = "force-dynamic";

export default async function PortalChannelsPage() {
  const [user, channels] = await Promise.all([
    portalFetch<PortalUser>("me"),
    portalFetch<PortalChannel[]>("channels"),
  ]);

  if (!user) redirect("/portal/login");

  const list = channels ?? [];

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-2xl font-semibold">I tuoi canali</h1>
        <p className="text-muted-foreground">
          I profili social su cui pubblichiamo per te quando partecipi a una campagna.
        </p>
      </div>

      <ConnectChannelPanel />

      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold tracking-wide text-muted-foreground uppercase">
          Collegati ({list.length})
        </h2>

        {list.length === 0 ? (
          <Card>
            <CardContent className="p-6 text-sm text-muted-foreground">
              Nessun canale collegato per ora.
            </CardContent>
          </Card>
        ) : (
          <div className="flex flex-col gap-2">
            {list.map((channel) => (
              <Card key={channel.id}>
                <CardContent className="flex flex-wrap items-center gap-x-4 gap-y-2 p-4">
                  <PlatformIcon platform={channel.platform} className="size-5 shrink-0" />

                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">{channel.name}</p>
                    {channel.username && (
                      <p className="truncate text-sm text-muted-foreground">@{channel.username}</p>
                    )}
                  </div>

                  {/* Where the channel came from - the whole point of the
                      multi-provider split, and the one thing a user might
                      reasonably wonder about their own channel. */}
                  <Badge variant="outline">{channel.provider_label}</Badge>

                  <Badge variant={channel.is_active ? "default" : "secondary"}>
                    {channel.is_active ? "Attivo" : "Non attivo"}
                  </Badge>

                  {channel.external_link && (
                    <a
                      href={channel.external_link}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-muted-foreground transition-colors hover:text-foreground"
                      aria-label={`Apri ${channel.name}`}
                    >
                      <ExternalLinkIcon className="size-4" />
                    </a>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
