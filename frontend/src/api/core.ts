import { download, post, request } from './client';
import type { Analytics, Deadline, DownloadItem, HistoryItem, Notification, Page, PlanDetailResponse, SavedSearch, SearchJob, SearchParams, TenderDetailResponse, User, WatchItem } from '../types';

export const authApi = {
  me: () => request<{ user: User }>('/api/auth/me'),
  login: (email: string, password: string) => post<{ user: User }>('/api/auth/login', { email, password }),
  register: (email: string, password: string) => post<{ user: User }>('/api/auth/register', { email, password }),
  logout: () => post<unknown>('/api/auth/logout', {}),
};
export const searchApi = {
  start: (params: SearchParams, signal?: AbortSignal) => request<SearchJob>('/api/search', { method: 'POST', body: JSON.stringify(params), signal }),
  poll: (id: string, signal?: AbortSignal) => request<SearchJob>('/api/job?id=' + encodeURIComponent(id), { signal }),
  export: (jobId: string, indices?: number[]) => download('/api/export', { job_id: jobId, ...(indices ? { indices } : {}) }, 'Ket_qua.xlsx'),
};
export const workspaceApi = {
  watchlist: () => request<{ items: WatchItem[] }>('/api/watchlist'),
  watch: (body: object) => post<{ items: WatchItem[] }>('/api/watchlist', body),
  history: () => request<{ items: HistoryItem[] }>('/api/history'),
  historyAction: (body: object) => post<{ items: HistoryItem[] }>('/api/history', body),
  presets: () => request<{ presets: SavedSearch[] }>('/api/presets'),
  presetAction: (body: object) => post<{ presets: SavedSearch[] }>('/api/presets', body),
  notifications: () => request<{ items: Notification[] }>('/api/notifications'),
  notificationAction: (body: object) => post<unknown>('/api/notifications', body),
  downloads: () => request<{ items: DownloadItem[] }>('/api/downloads'),
  analytics: () => request<Analytics>('/api/intelligence/analytics?period=day'),
  deadlines: () => request<Page<Deadline>>('/api/intelligence/deadlines?days=30&page=1&page_size=10'),
  tender: (code: string) => request<TenderDetailResponse>('/api/intelligence/tenders/' + encodeURIComponent(code)),
  plan: (code: string) => request<PlanDetailResponse>('/api/intelligence/plans/' + encodeURIComponent(code)),
};
