import { API_BASE_URL, authToken } from '@/src/api/client';
import type { Box, Manifest } from './scene';

export type CatalogEntry = { model_id: string; version_id: string; canonical_key: string; title: string; source_type: 'seed' | 'generated'; shared: boolean; category?: string; aliases?: string[] };
export type CatalogResult = {
  status: 'family' | 'building' | 'unknown';
  sources?: {title:string;url:string}[];
  model_id?: string; version_id?: string; manifest?: Manifest;
  source_type?: 'seed' | 'generated' | 'source_based';
  cache_hit?: boolean; generation_used?: boolean; shared?: boolean;
  reason?: string; job_id?: string; retry_after_seconds?: number; frame_id?: string;
  identification?: { canonical_key: string; object_name: string; confidence: 'high' | 'medium'; bbox: Box; uncertainty: string };
};
async function request<T>(path: string, init: RequestInit = {}, external?: AbortSignal): Promise<T> {
  if (!API_BASE_URL) throw new Error('Collegamento al motore di ORA non configurato.');
  const token = await authToken.get();
  if (!token) throw new Error('Accedi a ORA per usare la fotocamera intelligente.');
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (external?.aborted) controller.abort(); else external?.addEventListener('abort', abort, { once: true });
  const deadline = setTimeout(abort, 52_000);
  try {
    const response = await fetch(API_BASE_URL + '/api/vision-xray' + path, {
      ...init, signal: controller.signal, cache: 'no-store',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token, ...(init.headers || {}) },
    });
    const body = await response.json().catch(() => null);
    if (!response.ok) {
      const message = typeof body?.detail === 'string' ? body.detail : 'ORA non riesce a completare l’analisi.';
      throw new Error(message);
    }
    return body as T;
  } finally { clearTimeout(deadline); external?.removeEventListener('abort', abort); }
}
export const catalogApi = {
  list: () => request<{models: CatalogEntry[]}>('/catalog'),
  available: () => request<{available: boolean; catalog_count: number; seed_count: number}>('/available'),
  model: (id: string, signal?: AbortSignal) => request<CatalogResult>('/catalog/' + encodeURIComponent(id), {}, signal),
  job: (id: string, signal?: AbortSignal) => request<CatalogResult>('/jobs/' + encodeURIComponent(id), {}, signal),
  scan: (dataUri: string, frameId: string, signal?: AbortSignal) => {
    const match = /^data:(image\/(?:jpeg|png|webp));base64,([A-Za-z0-9+/=]+)$/.exec(dataUri);
    if (!match || match[2].length > 4_194_304) throw new Error('Usa una foto JPEG, PNG o WebP inferiore a 3 MB.');
    return request<CatalogResult>('/scan', { method: 'POST', body: JSON.stringify({
      mime_type: match[1], image_base64: match[2], frame_id: frameId,
      allow_generation: true,
    }) }, signal);
  },
};
