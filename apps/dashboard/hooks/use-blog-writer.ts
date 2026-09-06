"use client";

import { useMutation, useQuery, useQueryClient, type UseQueryOptions } from "@tanstack/react-query";
import * as blogWriterService from "@/services/blog-writer";
import { queryKeys } from "@/lib/query/keys";
import type {
  BlogArticleCreatePayload,
  BlogArticleGeneratePayload,
  BlogArticleUpdatePayload,
  BlogPublishTarget,
  WordpressSiteCreatePayload,
  WordpressSiteUpdatePayload,
} from "@/types/api";
import type { ListArticlesParams } from "@/services/blog-writer";

// ---------------------------------------------------------------------------
// WordPress sites
// ---------------------------------------------------------------------------
export function useWordpressSites() {
  return useQuery({
    queryKey: queryKeys.blogWriter.sites(),
    queryFn: blogWriterService.listWordpressSites,
  });
}

export function useCreateWordpressSite() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: WordpressSiteCreatePayload) => blogWriterService.createWordpressSite(payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.blogWriter.sites() }),
  });
}

export function useUpdateWordpressSite() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: WordpressSiteUpdatePayload }) =>
      blogWriterService.updateWordpressSite(id, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.blogWriter.sites() }),
  });
}

export function useDeleteWordpressSite() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => blogWriterService.deleteWordpressSite(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.blogWriter.sites() }),
  });
}

export function useTestWordpressSiteConnection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => blogWriterService.testWordpressSiteConnection(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.blogWriter.sites() }),
  });
}

export function useWordpressSiteCategories(siteId: string | undefined) {
  return useQuery({
    queryKey: ["blog-writer", "site-categories", siteId],
    queryFn: () => blogWriterService.getWordpressSiteCategories(siteId as string),
    enabled: !!siteId,
    retry: false,
  });
}

export function useWordpressSiteAuthors(siteId: string | undefined) {
  return useQuery({
    queryKey: ["blog-writer", "site-authors", siteId],
    queryFn: () => blogWriterService.getWordpressSiteAuthors(siteId as string),
    enabled: !!siteId,
    retry: false,
  });
}

// ---------------------------------------------------------------------------
// Articles
// ---------------------------------------------------------------------------
export function useArticles(params: ListArticlesParams = {}) {
  return useQuery({
    queryKey: queryKeys.blogWriter.articles(params),
    queryFn: () => blogWriterService.listArticles(params),
    placeholderData: (previousData) => previousData,
  });
}

export function useArticleDetail(
  id: string | undefined,
  options?: { refetchInterval?: UseQueryOptions<Awaited<ReturnType<typeof blogWriterService.getArticle>>>["refetchInterval"] }
) {
  return useQuery({
    queryKey: queryKeys.blogWriter.articleDetail(id ?? ""),
    queryFn: () => blogWriterService.getArticle(id as string),
    enabled: !!id,
    refetchInterval: options?.refetchInterval,
  });
}

export function useBlogWriterDashboard() {
  return useQuery({
    queryKey: queryKeys.blogWriter.dashboard(),
    queryFn: blogWriterService.getDashboardStats,
  });
}

function invalidateArticles(queryClient: ReturnType<typeof useQueryClient>, id?: string) {
  queryClient.invalidateQueries({ queryKey: ["blog-writer", "articles"] });
  queryClient.invalidateQueries({ queryKey: ["blog-writer", "dashboard"] });
  if (id) queryClient.invalidateQueries({ queryKey: queryKeys.blogWriter.articleDetail(id) });
}

export function useGenerateArticle() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: BlogArticleGeneratePayload) => blogWriterService.generateArticle(payload),
    onSuccess: () => invalidateArticles(queryClient),
  });
}

export function useCreateArticleManual() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: BlogArticleCreatePayload) => blogWriterService.createArticleManual(payload),
    onSuccess: () => invalidateArticles(queryClient),
  });
}

export function useUpdateArticle() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: BlogArticleUpdatePayload }) =>
      blogWriterService.updateArticle(id, payload),
    onSuccess: (_data, variables) => invalidateArticles(queryClient, variables.id),
  });
}

export function useArchiveArticle() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => blogWriterService.archiveArticle(id),
    onSuccess: (_data, id) => invalidateArticles(queryClient, id),
  });
}

export function useRestoreArticle() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => blogWriterService.restoreArticle(id),
    onSuccess: (_data, id) => invalidateArticles(queryClient, id),
  });
}

export function useDeleteArticle() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => blogWriterService.deleteArticle(id),
    onSuccess: () => invalidateArticles(queryClient),
  });
}

export function useDuplicateArticle() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => blogWriterService.duplicateArticle(id),
    onSuccess: () => invalidateArticles(queryClient),
  });
}

export function useRegenerateArticle() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => blogWriterService.regenerateArticle(id),
    onSuccess: (_data, id) => invalidateArticles(queryClient, id),
  });
}

export function usePublishArticle() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, targets }: { id: string; targets: BlogPublishTarget[] }) =>
      blogWriterService.publishArticle(id, targets),
    onSuccess: (_data, variables) => invalidateArticles(queryClient, variables.id),
  });
}

export function useRetryArticlePublication() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ articleId, publicationId }: { articleId: string; publicationId: string }) =>
      blogWriterService.retryArticlePublication(articleId, publicationId),
    onSuccess: (_data, variables) => invalidateArticles(queryClient, variables.articleId),
  });
}

export function useSocialPreview() {
  return useMutation({
    mutationFn: ({ id, wordpressSiteId }: { id: string; wordpressSiteId?: string }) =>
      blogWriterService.getSocialPreview(id, wordpressSiteId),
  });
}
