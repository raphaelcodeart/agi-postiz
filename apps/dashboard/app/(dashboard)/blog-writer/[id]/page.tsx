"use client";

import { use, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import {
  SaveIcon,
  SendIcon,
  RotateCcwIcon,
  MegaphoneIcon,
  EyeIcon,
  Loader2Icon,
  ImagesIcon,
} from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { MediaPreview } from "@/components/shared/media-preview";
import { StatusBadge } from "@/components/shared/status-badge";
import { ErrorState } from "@/components/shared/error-state";
import { EmptyState } from "@/components/shared/empty-state";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { articleEditFormSchema, type ArticleEditFormValues } from "@/lib/validation/blog-writer";
import {
  useArticleDetail,
  useUpdateArticle,
  useRetryArticlePublication,
  useSocialPreview,
} from "@/hooks/use-blog-writer";
import { useDebounce } from "@/hooks/use-debounce";
import { formatDateTime } from "@/lib/format";
import { ApiError } from "@/lib/api/errors";
import { BLOG_WRITER_PREFILL_KEY, type BlogWriterCampaignPrefill } from "@/lib/blog-writer-prefill";
import { PublishDialog } from "./_components/publish-dialog";
import { BlogWriterSubnav } from "../_components/blog-writer-subnav";
import { useAIGate } from "@/hooks/use-ai-gate";
import { AIRequiredDialog } from "@/components/shared/ai-required-dialog";
import { cn } from "@/lib/utils";
import { useMediaList } from "@/hooks/use-media";
import { MediaTypeFilter, filterMediaByType, type MediaTypeFilterValue } from "@/components/shared/media-type-filter";

function countWords(html: string): number {
  const text = html.replace(/<[^>]*>/g, " ");
  return text.split(/\s+/).filter(Boolean).length;
}

function countChars(html: string): number {
  return html.replace(/<[^>]*>/g, "").length;
}

export default function ArticleEditorPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const detailQuery = useArticleDetail(id, { refetchInterval: (query) => {
    const status = query.state.data?.article.status;
    return status === "publishing" || status === "generating" ? 3000 : false;
  } });
  const updateArticle = useUpdateArticle();
  const retryPublication = useRetryArticlePublication();
  const socialPreview = useSocialPreview();
  const aiGate = useAIGate();
  const mediaQuery = useMediaList();

  const [publishDialogOpen, setPublishDialogOpen] = useState(false);
  const [previewMode, setPreviewMode] = useState(false);
  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null);
  const [socialSiteId, setSocialSiteId] = useState<string | undefined>(undefined);
  const [selectedMediaId, setSelectedMediaId] = useState<string | null>(null);
  const [mediaTypeFilter, setMediaTypeFilter] = useState<MediaTypeFilterValue>("all");
  const hasHydrated = useRef(false);

  const form = useForm<ArticleEditFormValues>({
    resolver: zodResolver(articleEditFormSchema),
    defaultValues: { title: "", slug: "", excerpt: "", content: "", meta_title: "", meta_description: "", hashtags: [] },
  });

  useEffect(() => {
    if (detailQuery.data && !hasHydrated.current) {
      hasHydrated.current = true;
      const a = detailQuery.data.article;
      form.reset({
        title: a.title,
        slug: a.slug,
        excerpt: a.excerpt ?? "",
        content: a.content,
        meta_title: a.meta_title ?? "",
        meta_description: a.meta_description ?? "",
        hashtags: a.hashtags ?? [],
      });
      setSelectedMediaId(a.media_file_id ?? null);
      setLastSavedAt(new Date(a.updated_at));
    }
  }, [detailQuery.data, form]);

  // Warn on tab close/refresh with unsaved changes. Note: this does not
  // intercept in-app Next.js Link navigation (no stable App Router API for
  // that without an extra library) - only browser-level close/reload/back.
  useEffect(() => {
    function handler(e: BeforeUnloadEvent) {
      if (form.formState.isDirty) {
        e.preventDefault();
      }
    }
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [form.formState.isDirty]);

  const watchedValues = form.watch();
  const debouncedValues = useDebounce(watchedValues, 2000);
  const autosaveGuard = useRef(false);

  useEffect(() => {
    if (!autosaveGuard.current) {
      autosaveGuard.current = true;
      return;
    }
    if (!form.formState.isDirty || !detailQuery.data) return;
    if (!form.formState.isValid) return;
    handleSave(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedValues]);

  function handleSave(silent = false) {
    const values = form.getValues();
    updateArticle.mutate(
      {
        id,
        payload: {
          title: values.title,
          slug: values.slug,
          excerpt: values.excerpt || undefined,
          content: values.content,
          meta_title: values.meta_title || undefined,
          meta_description: values.meta_description || undefined,
          hashtags: values.hashtags,
        },
      },
      {
        onSuccess: () => {
          setLastSavedAt(new Date());
          form.reset(values);
          if (!silent) toast.success("Bozza salvata");
        },
        onError: (error) => {
          if (!silent) toast.error(error instanceof ApiError ? error.detail : "Salvataggio non riuscito");
        },
      }
    );
  }

  function handleSelectMedia(mediaId: string | null) {
    const next = selectedMediaId === mediaId ? null : mediaId;
    setSelectedMediaId(next);
    updateArticle.mutate(
      { id, payload: { media_file_id: next ?? "" } },
      {
        onSuccess: () => toast.success(next ? "Media allegato" : "Media rimosso"),
        onError: (error) => {
          setSelectedMediaId(selectedMediaId);
          toast.error(error instanceof ApiError ? error.detail : "Operazione non riuscita");
        },
      }
    );
  }

  function handleUseForSocialCampaign() {
    aiGate.guard(() => {
      socialPreview.mutate(
        { id, wordpressSiteId: socialSiteId },
        {
          onSuccess: (result) => {
            const prefill: BlogWriterCampaignPrefill = {
              title: detailQuery.data?.article.title ?? "",
              default_text: result.default_text,
              instagram_text: result.instagram_text,
              facebook_text: result.facebook_text,
              linkedin_text: result.linkedin_text,
              x_text: result.x_text,
              threads_text: result.threads_text,
              article_id: id,
            };
            sessionStorage.setItem(BLOG_WRITER_PREFILL_KEY, JSON.stringify(prefill));
            router.push("/campaigns/new?prefillArticle=1");
          },
          onError: (error) => toast.error(error instanceof ApiError ? error.detail : "Generazione anteprima non riuscita"),
        }
      );
    });
  }

  if (detailQuery.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-9 w-72" />
        <Skeleton className="h-96" />
      </div>
    );
  }

  if (detailQuery.isError || !detailQuery.data) {
    return <ErrorState error={detailQuery.error} onRetry={() => detailQuery.refetch()} />;
  }

  const { article, publications, social_campaigns } = detailQuery.data;
  const publishedSites = publications.filter((p) => p.publication_status === "published" || p.publication_status === "updated");
  const canUseForSocial = publishedSites.length > 0;
  const content = form.watch("content");

  return (
    <div className="space-y-6">
      <BlogWriterSubnav />
      <PageHeader
        title="Modifica articolo"
        description={
          lastSavedAt
            ? `Ultimo salvataggio: ${formatDateTime(lastSavedAt.toISOString())}${form.formState.isDirty ? " · modifiche non salvate" : ""}`
            : "Modifiche non salvate"
        }
        actions={
          <>
            <StatusBadge status={article.status} />
            <Button variant="outline" onClick={() => setPreviewMode((v) => !v)}>
              <EyeIcon className="size-4" />
              {previewMode ? "Modifica" : "Anteprima"}
            </Button>
            <Button variant="outline" onClick={() => handleSave(false)} disabled={updateArticle.isPending}>
              <SaveIcon className="size-4" />
              Salva
            </Button>
            <Button onClick={() => setPublishDialogOpen(true)}>
              <SendIcon className="size-4" />
              Pubblica sui blog
            </Button>
          </>
        }
      />

      <Card>
        <CardContent className="space-y-4 p-6">
          <Form {...form}>
            <form className="space-y-4" onSubmit={(e) => e.preventDefault()}>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <FormField
                  control={form.control}
                  name="title"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Titolo</FormLabel>
                      <FormControl>
                        <Input {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="slug"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Slug</FormLabel>
                      <FormControl>
                        <Input {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              <FormField
                control={form.control}
                name="excerpt"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Excerpt / riassunto</FormLabel>
                    <FormControl>
                      <Textarea rows={2} {...field} />
                    </FormControl>
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="content"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Contenuto (HTML)</FormLabel>
                    <FormControl>
                      {previewMode ? (
                        <div
                          className="max-w-none space-y-3 rounded-md border p-4 text-sm leading-relaxed [&_h2]:mt-4 [&_h2]:text-lg [&_h2]:font-semibold [&_h3]:text-base [&_h3]:font-semibold [&_li]:ml-4 [&_li]:list-disc [&_p]:leading-relaxed"
                          dangerouslySetInnerHTML={{ __html: field.value }}
                        />
                      ) : (
                        <Textarea rows={20} className="font-mono text-xs" {...field} />
                      )}
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <p className="text-xs text-muted-foreground">
                {countWords(content)} parole · {countChars(content)} caratteri
              </p>

              <FormField
                control={form.control}
                name="hashtags"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Hashtag</FormLabel>
                    <FormControl>
                      <Input
                        placeholder="Separati da virgola, senza #"
                        value={field.value.join(", ")}
                        onChange={(e) =>
                          field.onChange(e.target.value.split(",").map((h) => h.trim()).filter(Boolean))
                        }
                      />
                    </FormControl>
                  </FormItem>
                )}
              />

              <div className="grid grid-cols-1 gap-4 border-t pt-4 sm:grid-cols-2">
                <FormField
                  control={form.control}
                  name="meta_title"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Meta title</FormLabel>
                      <FormControl>
                        <Input {...field} />
                      </FormControl>
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="meta_description"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Meta description</FormLabel>
                      <FormControl>
                        <Input {...field} />
                      </FormControl>
                    </FormItem>
                  )}
                />
              </div>
            </form>
          </Form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Media allegato</CardTitle>
          <p className="text-xs text-muted-foreground">
            Caricato manualmente in <Link href="/media" className="underline">Media</Link>, non generato dall&apos;AI.
            Verrà incluso nel post quando pubblichi.
          </p>
        </CardHeader>
        <CardContent>
          {mediaQuery.isLoading ? (
            <Skeleton className="h-16" />
          ) : (mediaQuery.data ?? []).length === 0 ? (
            <EmptyState
              icon={ImagesIcon}
              title="Nessun media caricato"
              description="Carica un'immagine nella sezione Media per poterla allegare qui."
              action={
                <Button variant="outline" size="sm" asChild>
                  <Link href="/media">Vai a Media</Link>
                </Button>
              }
            />
          ) : (
            <div className="space-y-3">
              <MediaTypeFilter value={mediaTypeFilter} onChange={setMediaTypeFilter} />
              {(() => {
                const filtered = filterMediaByType(mediaQuery.data ?? [], mediaTypeFilter);
                return filtered.length === 0 ? (
                  <p className="text-xs text-muted-foreground">Nessun media di questo tipo.</p>
                ) : (
                  <div className="flex flex-wrap gap-3">
                    {filtered.map((media) => (
                      <button
                        key={media.id}
                        type="button"
                        onClick={() => handleSelectMedia(media.id)}
                        className={cn(
                          "flex w-20 flex-col items-center gap-1 rounded-md p-1 ring-2 ring-transparent transition-all",
                          selectedMediaId === media.id && "ring-primary"
                        )}
                      >
                        <MediaPreview media={media} className="size-16" />
                        <span className="line-clamp-2 text-center text-[10px] leading-tight text-muted-foreground" title={media.original_filename}>
                          {media.original_filename}
                        </span>
                      </button>
                    ))}
                  </div>
                );
              })()}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-4 space-y-0">
          <CardTitle className="text-base">Pubblicazioni WordPress</CardTitle>
          <div className="flex items-center gap-2">
            {publishedSites.length > 1 && (
              <Select
                items={publishedSites.map((p) => ({ value: p.wordpress_site_id, label: p.wordpress_site_name }))}
                value={socialSiteId ?? publishedSites[0].wordpress_site_id}
                onValueChange={(v) => setSocialSiteId(v ?? undefined)}
              >
                <SelectTrigger size="sm" className="w-48">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {publishedSites.map((p) => (
                    <SelectItem key={p.wordpress_site_id} value={p.wordpress_site_id}>
                      {p.wordpress_site_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            <Button
              variant="outline"
              size="sm"
              disabled={!canUseForSocial || socialPreview.isPending}
              onClick={handleUseForSocialCampaign}
              title={!canUseForSocial ? "Pubblica l'articolo su almeno un sito prima" : undefined}
              className={cn(!aiGate.configured && "opacity-50")}
            >
              {socialPreview.isPending ? <Loader2Icon className="size-4 animate-spin" /> : <MegaphoneIcon className="size-4" />}
              Utilizza per campagna social
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {publications.length === 0 ? (
            <EmptyState icon={SendIcon} title="Non ancora pubblicato" description='Usa "Pubblica sui blog" per scegliere i siti.' />
          ) : (
            <ul className="divide-y">
              {publications.map((pub) => (
                <li key={pub.id} className="flex flex-wrap items-center justify-between gap-2 py-3 text-sm">
                  <div className="min-w-0 space-y-0.5">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{pub.wordpress_site_name}</span>
                      <StatusBadge status={pub.publication_status} />
                    </div>
                    {pub.wordpress_post_url && (
                      <a href={pub.wordpress_post_url} target="_blank" rel="noreferrer" className="text-xs text-primary hover:underline">
                        {pub.wordpress_post_url}
                      </a>
                    )}
                    {pub.error_message && <p className="text-xs text-destructive">{pub.error_message}</p>}
                  </div>
                  {pub.publication_status === "failed" && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() =>
                        retryPublication.mutate(
                          { articleId: id, publicationId: pub.id },
                          { onSuccess: () => toast.success("Nuovo tentativo avviato") }
                        )
                      }
                      disabled={retryPublication.isPending}
                    >
                      <RotateCcwIcon className="size-3.5" />
                      Riprova
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Campagne social create</CardTitle>
        </CardHeader>
        <CardContent>
          {social_campaigns.length === 0 ? (
            <EmptyState icon={MegaphoneIcon} title="Nessuna campagna social ancora creata da questo articolo" />
          ) : (
            <ul className="divide-y">
              {social_campaigns.map((c) => (
                <li key={c.id} className="flex items-center justify-between gap-3 py-2 text-sm">
                  <Link href={`/campaigns/${c.id}`} className="min-w-0 flex-1 truncate hover:underline">
                    {c.title}
                  </Link>
                  <StatusBadge status={c.status} />
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <PublishDialog
        open={publishDialogOpen}
        onOpenChange={setPublishDialogOpen}
        articleId={id}
        alreadyPublishedSiteIds={publishedSites.map((p) => p.wordpress_site_id)}
      />

      <AIRequiredDialog open={aiGate.dialogOpen} onOpenChange={aiGate.setDialogOpen} />
    </div>
  );
}
