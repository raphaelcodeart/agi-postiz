import Link from "next/link";
import { redirect } from "next/navigation";
import { ArrowLeftIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { portalFetch, type PortalUser } from "@/lib/portal/server";
import { ProposalForm } from "../proposal-form";

export const dynamic = "force-dynamic";

export default async function NewPortalProposalPage() {
  const user = await portalFetch<PortalUser>("me");
  if (!user) redirect("/portal/login");

  return (
    <div className="flex flex-col gap-6">
      <Button variant="outline" size="sm" asChild className="self-start">
        <Link href="/portal/proposals">
          <ArrowLeftIcon className="size-4" />
          Torna alle proposte
        </Link>
      </Button>

      <div>
        <h1 className="text-2xl font-semibold">Nuova proposta</h1>
        <p className="text-muted-foreground">
          Scrivi il contenuto che proponi. Non viene pubblicato niente: lo legge
          l&apos;amministratore, e se lo accetta ne nasce una campagna.
        </p>
      </div>

      <ProposalForm />
    </div>
  );
}
