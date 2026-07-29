/** API client for communicating with the manga translator backend. */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  const config: RequestInit = {
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
    ...options,
  };

  const response = await fetch(url, config);

  // Handle 204 No Content (e.g. DELETE endpoints)
  if (response.status === 204) {
    return undefined as T;
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || `Request failed: ${response.status}`);
  }

  return response.json();
}

// ── Manga ──────────────────────────────────────────────────────────────

export interface Manga {
  id: string;
  title: string;
  title_original?: string;
  author?: string;
  artist?: string;
  description?: string;
  cover_image_path?: string;
  source_language: string;
  target_language: string;
  tags?: string[];
  chapter_count: number;
  total_pages?: number;
  translated_pages?: number;
  translation_progress?: number;
  last_activity?: string;
  last_translated_at?: string;
  created_at: string;
  updated_at: string;
}

export interface MangaCreate {
  title: string;
  title_original?: string;
  author?: string;
  artist?: string;
  description?: string;
  source_language?: string;
  target_language?: string;
  tags?: string[];
}

export interface Chapter {
  id: string;
  manga_id: string;
  chapter_number: number;
  title?: string;
  page_count: number;
  is_translated: boolean;
  created_at: string;
}

export interface Page {
  id: string;
  chapter_id: string;
  page_number: number;
  original_image_path: string;
  translated_image_path?: string;
  width?: number;
  height?: number;
  is_translated: boolean;
  bubble_count: number;
  /** Image URL (constructed from filesystem path for HTTP access) */
  original_image_url?: string;
  translated_image_url?: string;
}

export interface TranslationJob {
  id: string;
  chapter_id?: string;
  status: string;
  progress: number;
  total_pages: number;
  completed_pages: number;
  failed_pages: number;
  error_message?: string;
  source_language: string;
  target_language: string;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  updated_at?: string;
}

export interface TranslationJobCreate {
  chapter_id: string;
  source_language?: string;
  target_language?: string;
}

export interface TranslationRequest {
  text: string;
  source_language?: string;
  target_language?: string;
  context?: string;
}

export interface TranslationResponse {
  translated_text: string;
  source_language: string;
  target_language: string;
  confidence: number;
  processing_time_ms: number;
}

// ── API Functions ──────────────────────────────────────────────────────

export const mangaApi = {
  list: (params?: { page?: number; per_page?: number; search?: string }) =>
    request<Manga[]>(`/manga?${new URLSearchParams(params as any)}`),

  get: (id: string) => request<Manga>(`/manga/${id}`),

  create: (data: MangaCreate) =>
    request<Manga>("/manga", { method: "POST", body: JSON.stringify(data) }),

  update: (id: string, data: Partial<MangaCreate>) =>
    request<Manga>(`/manga/${id}`, { method: "PUT", body: JSON.stringify(data) }),

  delete: (id: string) =>
    request<void>(`/manga/${id}`, { method: "DELETE" }),

  listChapters: (mangaId: string) =>
    request<Chapter[]>(`/manga/${mangaId}/chapters`),

  createChapter: (mangaId: string, data: { chapter_number: number; title?: string }) =>
    request<Chapter>(`/manga/${mangaId}/chapters`, { method: "POST", body: JSON.stringify(data) }),

  listPages: (mangaId: string, chapterId: string) =>
    request<Page[]>(`/manga/${mangaId}/chapters/${chapterId}/pages`),
};

export const translationApi = {
  translate: (data: TranslationRequest) =>
    request<TranslationResponse>("/translate/text", { method: "POST", body: JSON.stringify(data) }),

  translateBatch: (texts: string[], sourceLanguage?: string, targetLanguage?: string) =>
    request<TranslationResponse[]>("/translate/batch", {
      method: "POST",
      body: JSON.stringify({ texts, source_language: sourceLanguage, target_language: targetLanguage }),
    }),

  createJob: (data: TranslationJobCreate) =>
    request<TranslationJob>("/translate/jobs", { method: "POST", body: JSON.stringify(data) }),

  listJobs: (params?: { limit?: number; offset?: number; status?: string }) =>
    request<TranslationJob[]>(`/translate/jobs?${new URLSearchParams(params as any)}`),

  getJob: (id: string) => request<TranslationJob>(`/translate/jobs/${id}`),

  getJobStatus: (id: string) =>
    request<{ id: string; status: string; progress: number }>(`/translate/jobs/${id}/status`),

  cancelJob: (id: string) =>
    request<{ message: string }>(`/translate/jobs/${id}/cancel`, { method: "POST" }),

  stopJob: (id: string) =>
    request<{ message: string }>(`/translate/jobs/${id}/stop`, { method: "POST" }),

  resumeJob: (id: string) =>
    request<{ message: string }>(`/translate/jobs/${id}/resume`, { method: "POST" }),

  retryJob: (id: string) =>
    request<{ message: string }>(`/translate/jobs/${id}/retry`, { method: "POST" }),

  getQueueStatus: () =>
    request<{ active_jobs: number; pending_queue_size: number; max_concurrent: number; healthy: boolean }>("/translate/queue/status"),
};
