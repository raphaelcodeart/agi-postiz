import { apiClient } from "@/lib/api/client";
import type { MyAgiGatewayStatus, MyAgiQrResponse, MyAgiSessionResponse } from "@/types/api";

const BASE = "/myagi";

export function getGatewayStatus(): Promise<MyAgiGatewayStatus> {
  return apiClient.get<MyAgiGatewayStatus>(`${BASE}/status`);
}

export function listSessions(): Promise<MyAgiSessionResponse[]> {
  return apiClient.get<MyAgiSessionResponse[]>(`${BASE}/sessions`);
}

export function createSession(name: string): Promise<MyAgiSessionResponse> {
  return apiClient.post<MyAgiSessionResponse>(`${BASE}/sessions`, { name });
}

export function startSession(accountId: string): Promise<MyAgiSessionResponse> {
  return apiClient.post<MyAgiSessionResponse>(`${BASE}/sessions/${accountId}/start`);
}

export function restartSession(accountId: string): Promise<MyAgiSessionResponse> {
  return apiClient.post<MyAgiSessionResponse>(`${BASE}/sessions/${accountId}/restart`);
}

export function logoutSession(accountId: string): Promise<MyAgiSessionResponse> {
  return apiClient.post<MyAgiSessionResponse>(`${BASE}/sessions/${accountId}/logout`);
}

export function getSessionQr(accountId: string): Promise<MyAgiQrResponse> {
  return apiClient.get<MyAgiQrResponse>(`${BASE}/sessions/${accountId}/qr`);
}
