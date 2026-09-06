import { z } from "zod";

export const wordpressSiteFormSchema = z.object({
  name: z.string().min(1, "Obbligatorio").max(255),
  site_url: z.string().min(1, "Obbligatorio").url("Deve essere un URL valido (https://...)"),
  api_url: z.string().min(1, "Obbligatorio").url("Deve essere un URL valido (es. https://tuosito.com/wp-json)"),
  username: z.string().min(1, "Obbligatorio").max(255),
  application_password: z.string().max(500),
  default_status: z.enum(["publish", "draft", "pending", "private"]),
  language: z.string().min(2).max(10),
});

export type WordpressSiteFormValues = z.infer<typeof wordpressSiteFormSchema>;

export const articleGenerateFormSchema = z.object({
  topic: z.string().min(3, "Descrivi almeno brevemente l'argomento").max(500),
  description: z.string().max(2000).optional().or(z.literal("")),
  goal: z.string().max(500).optional().or(z.literal("")),
  target_audience: z.string().max(500).optional().or(z.literal("")),
  language: z.string().min(2).max(10),
  tone: z.string().max(100).optional().or(z.literal("")),
  length: z.enum(["short", "medium", "long"]),
  primary_keyword: z.string().max(255).optional().or(z.literal("")),
  secondary_keywords: z.array(z.string()),
  must_include: z.string().max(1000).optional().or(z.literal("")),
  must_avoid: z.string().max(1000).optional().or(z.literal("")),
  call_to_action: z.string().max(255).optional().or(z.literal("")),
  hashtag_count: z.number().int().min(0).max(15),
  wordpress_site_id: z.string().nullable().optional(),
  wordpress_category_id: z.number().nullable().optional(),
});

export type ArticleGenerateFormValues = z.infer<typeof articleGenerateFormSchema>;

export const manualArticleFormSchema = z.object({
  title: z.string().min(1, "Obbligatorio").max(255),
  slug: z.string().max(255).optional().or(z.literal("")),
  excerpt: z.string().max(1000).optional().or(z.literal("")),
  content: z.string().min(1, "Incolla o scrivi il contenuto dell'articolo"),
  hashtags: z.array(z.string()),
  meta_title: z.string().max(255).optional().or(z.literal("")),
  meta_description: z.string().max(500).optional().or(z.literal("")),
  language: z.string().min(2).max(10),
});

export type ManualArticleFormValues = z.infer<typeof manualArticleFormSchema>;

export const articleEditFormSchema = z.object({
  title: z.string().min(1, "Obbligatorio").max(255),
  slug: z.string().min(1, "Obbligatorio").max(255),
  excerpt: z.string().max(1000).optional().or(z.literal("")),
  content: z.string().min(1, "Il contenuto non può essere vuoto"),
  meta_title: z.string().max(255).optional().or(z.literal("")),
  meta_description: z.string().max(500).optional().or(z.literal("")),
  hashtags: z.array(z.string()),
});

export type ArticleEditFormValues = z.infer<typeof articleEditFormSchema>;
