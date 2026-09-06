import { apiClient, ApiError } from "@/lib/api/client";
import { isMockApiEnabled } from "@/lib/env";
import * as mock from "@/lib/api/mock/adapter";
import type { MediaResponse } from "@/types/api";

export function listMedia(): Promise<MediaResponse[]> {
  if (isMockApiEnabled()) return mock.listMedia();
  return apiClient.get<MediaResponse[]>("/media/");
}

export function uploadMedia(file: File, onProgress?: (percent: number) => void): Promise<MediaResponse> {
  if (isMockApiEnabled()) {
    onProgress?.(100);
    return mock.uploadMedia(file);
  }
  const formData = new FormData();
  formData.append("file", file);
  return uploadWithProgress<MediaResponse>("/media/upload", formData, onProgress);
}

// fetch() has no cross-browser way to observe upload (request body) progress -
// only XMLHttpRequest exposes xhr.upload.onprogress - so this bypasses apiClient
// (which is fetch-based) for this one call. Same same-origin BFF proxy path and
// error-body shape as apiClient/lib/api/errors.ts, kept in sync deliberately.
function uploadWithProgress<T>(path: string, formData: FormData, onProgress?: (percent: number) => void): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `/api/backend${path}`);
    xhr.responseType = "text";
    xhr.setRequestHeader("Accept", "application/json");

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        onProgress?.(Math.round((event.loaded / event.total) * 100));
      }
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        onProgress?.(100);
        resolve(xhr.responseText ? (JSON.parse(xhr.responseText) as T) : (undefined as T));
        return;
      }
      let detail = xhr.statusText || "Request failed";
      try {
        const body = JSON.parse(xhr.responseText);
        if (typeof body?.detail === "string") detail = body.detail;
      } catch {
        // response had no JSON body
      }
      reject(new ApiError(xhr.status, detail));
    };

    xhr.onerror = () => reject(new ApiError(0, "Errore di rete durante il caricamento"));

    xhr.send(formData);
  });
}

export function getMedia(id: string): Promise<MediaResponse> {
  if (isMockApiEnabled()) return mock.getMedia(id);
  return apiClient.get<MediaResponse>(`/media/${id}`);
}

export function renameMedia(id: string, originalFilename: string): Promise<MediaResponse> {
  if (isMockApiEnabled()) return mock.renameMedia(id, originalFilename);
  return apiClient.patch<MediaResponse>(`/media/${id}`, { original_filename: originalFilename });
}

export function deleteMedia(id: string): Promise<void> {
  if (isMockApiEnabled()) return mock.deleteMedia(id);
  return apiClient.delete<void>(`/media/${id}`);
}
