"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { ArrowLeftIcon, ArrowRightIcon, Loader2Icon } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Form } from "@/components/ui/form";
import { Progress } from "@/components/ui/progress";
import {
  campaignWizardSchema,
  WIZARD_STEP_FIELDS,
  WIZARD_STEPS,
  buildTargetingParams,
  campaignToWizardDefaults,
  toCampaignCreatePayload,
  type CampaignWizardValues,
} from "@/lib/validation/campaigns";
import { useCreateCampaign, useLaunchCampaign, useCampaignDetail } from "@/hooks/use-campaigns";
import { ApiError } from "@/lib/api/errors";
import { BLOG_WRITER_PREFILL_KEY, type BlogWriterCampaignPrefill } from "@/lib/blog-writer-prefill";
import { WizardStepper } from "./_components/wizard-stepper";
import { StepInfo } from "./_components/step-info";
import { StepText } from "./_components/step-text";
import { StepMedia } from "./_components/step-media";
import { StepRecipients } from "./_components/step-recipients";
import { StepScheduling } from "./_components/step-scheduling";
import { StepSummary } from "./_components/step-summary";

function NewCampaignForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const duplicateId = searchParams.get("duplicate");
  const prefillArticle = searchParams.get("prefillArticle") === "1";
  const [step, setStep] = useState(1);
  const createCampaign = useCreateCampaign();
  const duplicateSource = useCampaignDetail(duplicateId ?? undefined);
  const hasPrefilled = useRef(false);
  const hasPrefilledArticle = useRef(false);

  const form = useForm<CampaignWizardValues>({
    resolver: zodResolver(campaignWizardSchema),
    defaultValues: {
      title: "",
      default_text: "",
      instagram_text: "",
      facebook_text: "",
      linkedin_text: "",
      tiktok_text: "",
      youtube_title: "",
      youtube_description: "",
      x_text: "",
      threads_text: "",
      include_referral_link: false,
      include_personal_contacts: false,
      media_file_id: null,
      article_id: null,
      targeting_mode: "all_active_channels",
      user_ids: [],
      group_ids: [],
      channel_ids: [],
      platform_names: [],
      publishing_mode: "immediate",
      scheduled_at: null,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    },
  });

  const launchCampaign = useLaunchCampaign();

  // Real progress isn't available during create+launch (both are quick DB writes
  // that just dispatch background jobs, not the actual per-channel Buffer calls -
  // those happen later, tracked separately by the campaign detail page's own
  // progress bar). This is a deliberately approximate "creep toward a ceiling,
  // then snap forward on each real milestone" bar - just to make it visually
  // obvious the click registered and nothing has frozen.
  const [launchProgress, setLaunchProgress] = useState<{ value: number; label: string } | null>(null);
  const creepTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  function stopCreep() {
    if (creepTimer.current) {
      clearInterval(creepTimer.current);
      creepTimer.current = null;
    }
  }

  function creepTo(from: number, ceiling: number, label: string) {
    stopCreep();
    setLaunchProgress({ value: from, label });
    creepTimer.current = setInterval(() => {
      setLaunchProgress((prev) => {
        if (!prev) return prev;
        const next = prev.value + (ceiling - prev.value) * 0.15;
        return { value: next, label: prev.label };
      });
    }, 200);
  }

  useEffect(() => () => stopCreep(), []);

  useEffect(() => {
    if (duplicateSource.data && !hasPrefilled.current) {
      hasPrefilled.current = true;
      form.reset(campaignToWizardDefaults(duplicateSource.data.campaign));
      toast.info("Campagna precompilata: rivedi testo, media e scelte di pubblicazione prima di lanciarla.");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [duplicateSource.data]);

  // Same idiom as the ?duplicate= prefill above, but reading a blob stashed by
  // Blog Writer's "Usa per campagna social" (see lib/blog-writer-prefill.ts) -
  // sessionStorage instead of a fetched campaign since there's no existing
  // Campaign row to load yet.
  useEffect(() => {
    if (!prefillArticle || hasPrefilledArticle.current) return;
    hasPrefilledArticle.current = true;
    const raw = sessionStorage.getItem(BLOG_WRITER_PREFILL_KEY);
    if (!raw) return;
    sessionStorage.removeItem(BLOG_WRITER_PREFILL_KEY);
    try {
      const prefill = JSON.parse(raw) as BlogWriterCampaignPrefill;
      form.reset({
        ...form.getValues(),
        title: prefill.title,
        default_text: prefill.default_text,
        instagram_text: prefill.instagram_text,
        facebook_text: prefill.facebook_text,
        linkedin_text: prefill.linkedin_text,
        x_text: prefill.x_text,
        threads_text: prefill.threads_text,
        article_id: prefill.article_id,
        publishing_mode: "draft",
      });
      toast.info("Campagna precompilata dall'articolo: rivedi il testo prima di scegliere destinatari e pubblicazione.");
    } catch {
      // Malformed/stale blob - silently ignore, wizard just starts blank.
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefillArticle]);

  async function goNext() {
    const fields = WIZARD_STEP_FIELDS[step - 1];
    const valid = fields.length === 0 || (await form.trigger(fields));
    if (valid) {
      setStep((s) => Math.min(WIZARD_STEPS.length, s + 1));
      return;
    }
    // Errors are already shown inline under each field, but if the field
    // with the problem is on a platform tab the admin isn't currently
    // looking at (e.g. X while viewing Instagram), clicking "Avanti" would
    // otherwise just silently do nothing with no visible explanation.
    const messages = new Set(
      fields.map((f) => form.formState.errors[f]?.message).filter((m): m is string => !!m)
    );
    if (messages.size > 0) {
      messages.forEach((message) => toast.error(message));
    } else {
      toast.error("Correggi gli errori evidenziati prima di continuare");
    }
  }

  function goBack() {
    setStep((s) => Math.max(1, s - 1));
  }

  async function handleSubmit(values: CampaignWizardValues) {
    try {
      creepTo(8, 45, "Creazione campagna...");
      const campaign = await createCampaign.mutateAsync(toCampaignCreatePayload(values));

      if (values.publishing_mode === "draft") {
        stopCreep();
        setLaunchProgress({ value: 100, label: "Bozza salvata" });
        toast.success("Campagna salvata come bozza");
        router.push(`/campaigns/${campaign.id}`);
        return;
      }

      creepTo(45, 95, "Risoluzione destinatari e avvio pubblicazione...");
      await launchCampaign.mutateAsync({
        campaignId: campaign.id,
        targetingParams: buildTargetingParams(values),
      });
      stopCreep();
      setLaunchProgress({ value: 100, label: "Campagna lanciata" });

      toast.success("Campagna creata e lanciata");
      router.push(`/campaigns/${campaign.id}`);
    } catch (error) {
      stopCreep();
      setLaunchProgress(null);
      toast.error(error instanceof ApiError ? error.detail : "Impossibile creare la campagna");
    }
  }

  const isLastStep = step === WIZARD_STEPS.length;
  const isSubmitting = createCampaign.isPending || launchCampaign.isPending;

  return (
    <div className="space-y-6">
      <PageHeader
        title={duplicateId ? "Duplica campagna" : prefillArticle ? "Nuova campagna da articolo" : "Nuova campagna"}
        description={
          duplicateId
            ? "Testo, media e destinatari precompilati dalla campagna originale: correggi ciò che serve e scegli come pubblicare."
            : prefillArticle
              ? "Testo precompilato dall'articolo Blog Writer: rivedilo, scegli destinatari e pubblicazione."
              : "Crea una campagna di pubblicazione multi-piattaforma"
        }
      />

      <WizardStepper currentStep={step} />

      <Card>
        <CardContent className="p-6">
          {launchProgress ? (
            <div className="flex flex-col items-center gap-4 py-10 text-center">
              <Loader2Icon className="size-6 animate-spin text-primary" />
              <div className="w-full max-w-sm space-y-2">
                <Progress value={launchProgress.value} />
                <p className="text-sm text-muted-foreground">{launchProgress.label}</p>
              </div>
            </div>
          ) : (
            <Form {...form}>
              <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-6">
                {step === 1 && <StepInfo form={form} />}
                {step === 2 && <StepText form={form} />}
                {step === 3 && <StepMedia form={form} />}
                {step === 4 && <StepRecipients form={form} />}
                {step === 5 && <StepScheduling form={form} />}
                {step === 6 && <StepSummary form={form} />}

                <div className="flex items-center justify-between border-t pt-4">
                  <Button type="button" variant="outline" onClick={goBack} disabled={step === 1}>
                    <ArrowLeftIcon className="size-4" />
                    Indietro
                  </Button>
                  {isLastStep ? (
                    <Button type="submit" disabled={isSubmitting}>
                      {isSubmitting && <Loader2Icon className="size-4 animate-spin" />}
                      {form.watch("publishing_mode") === "draft" ? "Salva bozza" : "Crea e lancia campagna"}
                    </Button>
                  ) : (
                    <Button type="button" onClick={goNext}>
                      Avanti
                      <ArrowRightIcon className="size-4" />
                    </Button>
                  )}
                </div>
              </form>
            </Form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default function NewCampaignPage() {
  return (
    <Suspense>
      <NewCampaignForm />
    </Suspense>
  );
}
