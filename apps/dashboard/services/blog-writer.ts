import { apiClient } from "@/lib/api/client";
import { buildQueryString } from "@/lib/api/query-string";
import type {
  BlogArticleCreatePayload,
  BlogArticleDetailResponse,
  BlogArticleGeneratePayload,
  BlogArticleListItem,
  BlogArticleResponse,
  BlogArticleUpdatePayload,
  BlogPublicationResponse,
  BlogPublishTarget,
  BlogWriterDashboardResponse,
  SocialPreviewResponse,
  WordpressOptionItem,
  WordpressSiteCreatePayload,
  WordpressSiteResponse,
  WordpressSiteUpdatePayload,
  WordpressTestConnectionResponse,
} from "@/types/api";

// ---------------------------------------------------------------------------
// WordPress sites
// ---------------------------------------------------------------------------
export function listWordpressSites(): Promise<WordpressSiteResponse[]> {
  return apiClient.get<WordpressSiteResponse[]>("/blog-writer/sites/");
}

export function createWordpressSite(payload: WordpressSiteCreatePayload): Promise<WordpressSiteResponse> {
  return apiClient.post<WordpressSiteResponse>("/blog-writer/sites/", payload);
}

export function updateWordpressSite(id: string, payload: WordpressSiteUpdatePayload): Promise<WordpressSiteResponse> {
  return apiClient.put<WordpressSiteResponse>(`/blog-writer/sites/${id}`, payload);
}

export function deleteWordpressSite(id: string): Promise<void> {
  return apiClient.delete<void>(`/blog-writer/sites/${id}`);
}

export function testWordpressSiteConnection(id: string): Promise<WordpressTestConnectionResponse> {
  return apiClient.post<WordpressTestConnectionResponse>(`/blog-writer/sites/${id}/test-connection`);
}

export function getWordpressSiteCategories(id: string): Promise<WordpressOptionItem[]> {
  return apiClient.get<WordpressOptionItem[]>(`/blog-writer/sites/${id}/categories`);
}

export function getWordpressSiteAuthors(id: string): Promise<WordpressOptionItem[]> {
  return apiClient.get<WordpressOptionItem[]>(`/blog-writer/sites/${id}/authors`);
}

// ---------------------------------------------------------------------------
// Articles
// ---------------------------------------------------------------------------
export interface ListArticlesParams {
  status?: string;
  skip?: number;
  limit?: number;
}

export function listArticles(params: ListArticlesParams = {}): Promise<BlogArticleListItem[]> {
  return apiClient.get<BlogArticleListItem[]>(`/blog-writer/articles/${buildQueryString(params)}`);
}

export function getArticle(id: string): Promise<BlogArticleDetailResponse> {
  return apiClient.get<BlogArticleDetailResponse>(`/blog-writer/articles/${id}`);
}

export function generateArticle(payload: BlogArticleGeneratePayload): Promise<BlogArticleResponse> {
  return apiClient.post<BlogArticleResponse>("/blog-writer/articles/generate", payload);
}

export function createArticleManual(payload: BlogArticleCreatePayload): Promise<BlogArticleResponse> {
  return apiClient.post<BlogArticleResponse>("/blog-writer/articles/", payload);
}

export function updateArticle(id: string, payload: BlogArticleUpdatePayload): Promise<BlogArticleResponse> {
  return apiClient.put<BlogArticleResponse>(`/blog-writer/articles/${id}`, payload);
}

export function archiveArticle(id: string): Promise<BlogArticleResponse> {
  return apiClient.post<BlogArticleResponse>(`/blog-writer/articles/${id}/archive`);
}

export function restoreArticle(id: string): Promise<BlogArticleResponse> {
  return apiClient.post<BlogArticleResponse>(`/blog-writer/articles/${id}/restore`);
}

export function deleteArticle(id: string): Promise<void> {
  return apiClient.delete<void>(`/blog-writer/articles/${id}`);
}

export function duplicateArticle(id: string): Promise<BlogArticleResponse> {
  return apiClient.post<BlogArticleResponse>(`/blog-writer/articles/${id}/duplicate`);
}

export function regenerateArticle(id: string): Promise<BlogArticleResponse> {
  return apiClient.post<BlogArticleResponse>(`/blog-writer/articles/${id}/regenerate`);
}

export function publishArticle(id: string, targets: BlogPublishTarget[]): Promise<BlogPublicationResponse[]> {
  return apiClient.post<BlogPublicationResponse[]>(`/blog-writer/articles/${id}/publish`, { targets });
}

export function retryArticlePublication(articleId: string, publicationId: string): Promise<BlogPublicationResponse> {
  return apiClient.post<BlogPublicationResponse>(`/blog-writer/articles/${articleId}/publications/${publicationId}/retry`);
}

export function getSocialPreview(id: string, wordpressSiteId?: string): Promise<SocialPreviewResponse> {
  return apiClient.post<SocialPreviewResponse>(`/blog-writer/articles/${id}/social-preview`, {
    wordpress_site_id: wordpressSiteId ?? null,
  });
}

export function getDashboardStats(): Promise<BlogWriterDashboardResponse> {
  return apiClient.get<BlogWriterDashboardResponse>("/blog-writer/articles/dashboard/stats");
}
