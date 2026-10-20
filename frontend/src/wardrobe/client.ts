import { API_BASE_URL, authToken } from '@/src/api/client';

export const CATEGORIES = [
  { value: 'top', label: 'Maglia / camicia' },
  { value: 'bottom', label: 'Pantaloni / gonna' },
  { value: 'shoes', label: 'Scarpe' },
  { value: 'one_piece', label: 'Abito intero / tuta' },
  { value: 'outerwear', label: 'Giacca / cappotto' },
  { value: 'accessory', label: 'Accessorio' },
] as const;
export type Category = typeof CATEGORIES[number]['value'];
export const FORMALITIES = [
  { value: 'sport', label: 'Sportivo' },
  { value: 'casual', label: 'Casual' },
  { value: 'smart', label: 'Curato' },
  { value: 'formal', label: 'Elegante' },
] as const;
export type Formality = typeof FORMALITIES[number]['value'];
export type GarmentStatus = 'available' | 'laundry' | 'unavailable';
export type Season = 'spring' | 'summer' | 'fall' | 'winter';
export type GarmentInput = {
  id: string; revision: number; name: string; category: Category;
  color: string; formality: Formality; seasons: Season[]; status: GarmentStatus;
};
export type Garment = GarmentInput & { photo: string | null; created_at: string; updated_at: string };
export const OCCASIONS = [
  { value: 'running', label: 'Correre' },
  { value: 'casual_evening', label: 'Sabato sera' },
  { value: 'chic_evening', label: 'Serata chic' },
  { value: 'club', label: 'Discoteca' },
  { value: 'wedding', label: 'Matrimonio' },
] as const;
export type Occasion = typeof OCCASIONS[number]['value'];
export type GarmentProposal = {
  name: string; category: Category; color: string; formality?: Formality;
};
export type GarmentAnalysis = {
  recognized: boolean; confidence: 'high' | 'medium' | 'low';
  suggestion: GarmentProposal | null; saved: false;
  engine: 'vision-ai-draft'; message: string;
};

export type OutfitResponse = {
  engine: 'rules-v1' | 'ai-stylist-v1';
  ai_status?: 'ok' | 'not_requested' | 'insufficient_wardrobe' | 'unavailable' | 'rate_limited';
  candidate_count?: number;
  occasion: Occasion; missing: Category[]; message: string;
  outfits: { item_ids: string[]; title: string; why: string;
    verdict?: 'good' | 'acceptable' | 'weak';
    cautions?: string[]; styling_tip?: string; score?: number }[];
};

async function request<T>(token: string, path: string, init: RequestInit = {}): Promise<T> {
  if (!token || (await authToken.get()) !== token) throw new Error('Sessione cambiata. Riapri il guardaroba.');
  if (!API_BASE_URL) throw new Error('Collegamento al server non configurato.');
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 25_000);
  try {
    const response = await fetch(`${API_BASE_URL}/api/wardrobe${path}`, {
      ...init, signal: controller.signal, cache: 'no-store',
      headers: { ...init.headers, Authorization: `Bearer ${token}` },
    });
    if ((await authToken.get()) !== token) throw new Error('Sessione cambiata. Riapri il guardaroba.');
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail :
      response.status === 401 ? 'Accedi nuovamente a ORA.' : 'Guardaroba non disponibile. Riprova.');
    return data as T;
  } catch (error) {
    if (controller.signal.aborted) throw new Error('Il server non ha risposto. Controlla i capi prima di riprovare.');
    throw error;
  } finally { clearTimeout(timer); }
}

export const wardrobeClient = {
  token: () => authToken.get(),
  list: (token: string) => request<{ items: Garment[] }>(token, '/items'),
  save: (token: string, item: GarmentInput) => request<{ item: Garment }>(token, '/items', {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(item),
  }),
  remove: (token: string, item: Garment) => request<{ deleted: boolean }>(token,
    `/items/${encodeURIComponent(item.id)}?revision=${item.revision}`, { method: 'DELETE' }),
  photo: (token: string, item: Garment, photo: Blob) => request<{ item: Garment }>(token,
    `/items/${encodeURIComponent(item.id)}/photo?revision=${item.revision}`, {
      method: 'POST', headers: { 'Content-Type': photo.type }, body: photo,
    }),
  analyze: (token: string, photo: Blob) => request<GarmentAnalysis>(token, '/analyze', {
    method: 'POST', headers: { 'Content-Type': photo.type }, body: photo,
  }),
  outfits: (token: string, occasion: Occasion, styleNote = '') => request<OutfitResponse>(token, '/outfits', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ occasion, use_ai: true, style_note: styleNote.slice(0, 200) }),
  }),
};
