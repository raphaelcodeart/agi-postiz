import { z } from "zod";
import type { CampaignCreatePayload, CampaignResponse } from "@/types/api";

export const publishingModeValues = [
  "immediate",
  "scheduled",
  "buffer_queue",
  "draft",
  "approval",
] as const;

export const targetingModeValues = [
  "all_active_channels",
  "selected_users",
  "selected_groups",
  "selected_channels",
  "selected_platforms",
] as const;

// Hard per-platform text limits actually enforced by Buffer (mirrors
// PLATFORM_TEXT_LIMITS in campaign_resolver.py) - only X/Twitter and Threads
// have one; Instagram/Facebook/LinkedIn/TikTok don't, so their boxes stay at
// the generous 5000-char UI cap regardless of the referral link toggle.
export const PLATFORM_HARD_LIMITS: Record<"x_text" | "threads_text", number> = {
  x_text: 280,
  threads_text: 500,
};

// Space reserved for "\n\nISCRIVITI QUI: {link}" (17 chars of fixed label,
// see resolve_text_for_channel in campaign_resolver.py) plus an assumption
// for the link itself. Deliberately modest (43 chars for the link, not the
// full 1000 the field technically allows): a first version reserved 150 and
// it blocked completely ordinary 168-char X/Twitter text the moment the
// toggle was switched on - real referral links are typically short URLs, and
// this is a *soft*, UI-only guardrail, not the real safety check. The actual
// backstop remains the backend's PLATFORM_TEXT_LIMITS check on the resolved
// text (with the link already appended) at launch time, which still excludes
// just that one target if a user's real link is longer than assumed here.
export const REFERRAL_LINK_RESERVED_CHARS = 60;

// Same idea as REFERRAL_LINK_RESERVED_CHARS above, but for "Includi contatti
// personali" (a short signature block - name, phone, etc. - not a single URL).
// Mirrors PERSONAL_CONTACTS_RESERVED_CHARS in
// apps/api/app/integrations/openai/client.py - keep both in sync if either
// changes. Same soft, UI-only guardrail rationale: the real backstop remains
// the backend's PLATFORM_TEXT_LIMITS check on the resolved text at launch.
export const PERSONAL_CONTACTS_RESERVED_CHARS = 100;

export const campaignWizardSchema = z
  .object({
    // Step 1 - Info
    title: z.string().min(1, "Il titolo è obbligatorio").max(255),

    // Step 2 - Text
    default_text: z.string().min(1, "Il testo predefinito è obbligatorio").max(5000),
    instagram_text: z.string().max(5000).optional().or(z.literal("")),
    facebook_text: z.string().max(5000).optional().or(z.literal("")),
    linkedin_text: z.string().max(5000).optional().or(z.literal("")),
    tiktok_text: z.string().max(5000).optional().or(z.literal("")),
    youtube_title: z.string().max(100).optional().or(z.literal("")),
    youtube_description: z.string().max(5000).optional().or(z.literal("")),
    x_text: z.string().max(280).optional().or(z.literal("")),
    threads_text: z.string().max(500).optional().or(z.literal("")),
    include_referral_link: z.boolean(),
    include_personal_contacts: z.boolean(),

    // Step 3 - Media
    media_file_id: z.string().optional().nullable(),

    // Set only when prefilled from Blog Writer's "Usa per campagna social"
    // (see lib/blog-writer-prefill.ts) - purely informational, never required.
    article_id: z.string().optional().nullable(),

    // Step 4 - Recipients
    targeting_mode: z.enum(targetingModeValues),
    user_ids: z.array(z.string()).optional(),
    group_ids: z.array(z.string()).optional(),
    channel_ids: z.array(z.string()).optional(),
    platform_names: z.array(z.string()).optional(),

    // Step 5 - Scheduling
    publishing_mode: z.enum(publishingModeValues),
    scheduled_at: z.string().optional().nullable(),
    timezone: z.string().min(1),
  })
  .superRefine((data, ctx) => {
    const reservedChars =
      (data.include_referral_link ? REFERRAL_LINK_RESERVED_CHARS : 0) +
      (data.include_personal_contacts ? PERSONAL_CONTACTS_RESERVED_CHARS : 0);
    if (reservedChars > 0) {
      const toggledLabel =
        data.include_referral_link && data.include_personal_contacts
          ? "il link referral e i contatti personali attivi"
          : data.include_referral_link
            ? "il link referral attivo"
            : "i contatti personali attivi";
      (Object.keys(PLATFORM_HARD_LIMITS) as (keyof typeof PLATFORM_HARD_LIMITS)[]).forEach((field) => {
        const limit = PLATFORM_HARD_LIMITS[field] - reservedChars;
        const length = (data[field] ?? "").length;
        if (length > limit) {
          ctx.addIssue({
            code: "custom",
            message: `Con ${toggledLabel} restano ${limit} caratteri disponibili (${PLATFORM_HARD_LIMITS[field]} del limite piattaforma meno lo spazio riservato) - ${length - limit} di troppo`,
            path: [field],
          });
        }
      });
    }
    if (data.publishing_mode === "scheduled" && !data.scheduled_at) {
      ctx.addIssue({
        code: "custom",
        message: "Seleziona una data di programmazione",
        path: ["scheduled_at"],
      });
    }
    if (data.targeting_mode === "selected_users" && !data.user_ids?.length) {
      ctx.addIssue({
        code: "custom",
        message: "Seleziona almeno un utente",
        path: ["user_ids"],
      });
    }
    if (data.targeting_mode === "selected_groups" && !data.group_ids?.length) {
      ctx.addIssue({
        code: "custom",
        message: "Seleziona almeno un gruppo",
        path: ["group_ids"],
      });
    }
    if (data.targeting_mode === "selected_channels" && !data.channel_ids?.length) {
      ctx.addIssue({
        code: "custom",
        message: "Seleziona almeno un canale",
        path: ["channel_ids"],
      });
    }
    if (data.targeting_mode === "selected_platforms" && !data.platform_names?.length) {
      ctx.addIssue({
        code: "custom",
        message: "Seleziona almeno una piattaforma",
        path: ["platform_names"],
      });
    }
  });

export type CampaignWizardValues = z.infer<typeof campaignWizardSchema>;

export const WIZARD_STEP_FIELDS: (keyof CampaignWizardValues)[][] = [
  ["title"],
  ["default_text", "x_text", "threads_text", "include_referral_link", "include_personal_contacts"],
  ["media_file_id"],
  ["targeting_mode", "user_ids", "group_ids", "channel_ids", "platform_names"],
  ["publishing_mode", "scheduled_at", "timezone"],
  [],
];

export const WIZARD_STEPS = [
  "Informazioni",
  "Testo",
  "Media",
  "Destinatari",
  "Programmazione",
  "Riepilogo",
] as const;

export function toCampaignCreatePayload(values: CampaignWizardValues): CampaignCreatePayload {
  return {
    title: values.title,
    default_text: values.default_text,
    instagram_text: values.instagram_text || null,
    facebook_text: values.facebook_text || null,
    linkedin_text: values.linkedin_text || null,
    tiktok_text: values.tiktok_text || null,
    youtube_title: values.youtube_title || null,
    youtube_description: values.youtube_description || null,
    x_text: values.x_text || null,
    threads_text: values.threads_text || null,
    include_referral_link: values.include_referral_link,
    include_personal_contacts: values.include_personal_contacts,
    media_file_id: values.media_file_id || null,
    article_id: values.article_id || null,
    publishing_mode: values.publishing_mode,
    scheduled_at: values.scheduled_at ? new Date(values.scheduled_at).toISOString() : null,
    timezone: values.timezone,
    targeting_mode: values.targeting_mode,
    targeting_params: buildTargetingParams(values),
  };
}

// Prefills the wizard from an existing campaign ("Duplica campagna"). Text,
// media and recipient selection are copied as-is; publishing mode and
// scheduled_at are deliberately reset so the admin has to actively re-pick
// them rather than silently reusing a possibly past/one-off schedule.
export function campaignToWizardDefaults(campaign: CampaignResponse): Partial<CampaignWizardValues> {
  const params = (campaign.metadata_json ?? {}) as Record<string, unknown>;
  const asStringArray = (value: unknown): string[] => (Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : []);

  return {
    title: `${campaign.title} (copia)`,
    default_text: campaign.default_text,
    instagram_text: campaign.instagram_text ?? "",
    facebook_text: campaign.facebook_text ?? "",
    linkedin_text: campaign.linkedin_text ?? "",
    tiktok_text: campaign.tiktok_text ?? "",
    youtube_title: campaign.youtube_title ?? "",
    youtube_description: campaign.youtube_description ?? "",
    x_text: campaign.x_text ?? "",
    threads_text: campaign.threads_text ?? "",
    include_referral_link: campaign.include_referral_link,
    include_personal_contacts: campaign.include_personal_contacts,
    media_file_id: campaign.media_file_id,
    targeting_mode: campaign.targeting_mode,
    user_ids: asStringArray(params.user_ids),
    group_ids: asStringArray(params.group_ids),
    channel_ids: asStringArray(params.channel_ids),
    platform_names: asStringArray(params.platform_names),
    publishing_mode: "immediate",
    scheduled_at: null,
    timezone: campaign.timezone,
  };
}

export function buildTargetingParams(values: CampaignWizardValues): Record<string, unknown> {
  // "all_active_channels" / "selected_users" / "selected_groups" can optionally
  // be narrowed to specific platforms on top of who's targeted (e.g. a group,
  // but only their Instagram+Facebook channels) - "selected_channels" is already
  // explicit and "selected_platforms" already *is* the platform filter, so
  // neither combines with it.
  const platformFilter = values.platform_names?.length ? { platform_names: values.platform_names } : {};

  switch (values.targeting_mode) {
    case "selected_users":
      return { user_ids: values.user_ids ?? [], ...platformFilter };
    case "selected_groups":
      return { group_ids: values.group_ids ?? [], ...platformFilter };
    case "selected_channels":
      return { channel_ids: values.channel_ids ?? [] };
    case "selected_platforms":
      return { platform_names: values.platform_names ?? [] };
    default:
      return { ...platformFilter };
  }
}
