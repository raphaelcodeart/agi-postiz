// Shared between blog-writer/[id]/page.tsx ("Usa per campagna social") and
// campaigns/new/page.tsx (?prefillArticle=1 reader). sessionStorage carries the
// blob because generated text can be up to 5000 chars - too long for a query
// param, and this mirrors the existing ?duplicate=<id> prefill idiom already
// used by the wizard (see campaignToWizardDefaults) without touching it.
export const BLOG_WRITER_PREFILL_KEY = "blog-writer-campaign-prefill";

export interface BlogWriterCampaignPrefill {
  title: string;
  default_text: string;
  instagram_text: string;
  facebook_text: string;
  linkedin_text: string;
  x_text: string;
  threads_text: string;
  article_id: string;
}
