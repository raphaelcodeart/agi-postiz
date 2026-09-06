import { apiClient } from "@/lib/api/client";
import { isMockApiEnabled } from "@/lib/env";
import * as mock from "@/lib/api/mock/adapter";
import type { BufferConnectionResponse } from "@/types/api";

export function listConnections(): Promise<BufferConnectionResponse[]> {
  if (isMockApiEnabled()) return mock.listConnections();
  return apiClient.get<BufferConnectionResponse[]>("/buffer/connections");
}

export function createConnection(userId: string, apiKey: string): Promise<BufferConnectionResponse> {
  if (isMockApiEnabled()) return mock.createConnection(userId, apiKey);
  return apiClient.post<BufferConnectionResponse>("/buffer/connections", { user_id: userId, api_key: apiKey });
}

export function syncConnection(connectionId: string): Promise<{ message: string }> {
  if (isMockApiEnabled()) return mock.syncConnection(connectionId);
  return apiClient.post<{ message: string }>(`/buffer/connections/${connectionId}/sync`);
}

export function disconnectConnection(connectionId: string): Promise<void> {
  if (isMockApiEnabled()) return mock.disconnectConnection(connectionId);
  return apiClient.delete<void>(`/buffer/connections/${connectionId}`);
}
