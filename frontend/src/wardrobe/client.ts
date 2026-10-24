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
export const VISUAL_FIELDS = {
  pattern: [
    { value: 'solid', label: 'Tinta unita' }, { value: 'striped', label: 'Righe' },
    { value: 'checked', label: 'Quadri' }, { value: 'printed', label: 'Stampa' },
    { value: 'mixed', label: 'Misto' }, { value: 'uncertain', label: 'Incerto' },
  ],
  shape: [
    { value: 'tailored', label: 'Strutturato' }, { value: 'regular', label: 'Regolare' },
    { value: 'relaxed', label: 'Morbido' }, { value: 'sporty', label: 'Sportivo' },
    { value: 'uncertain', label: 'Incerto' },
  ],
  surface: [
    { value: 'smooth', label: 'Liscio' }, { value: 'knit_like', label: 'Simile a maglia' },
    { value: 'denim_like', label: 'Aspetto denim' }, { value: 'leather_like', label: 'Aspetto pelle' },
    { value: 'textured', label: 'Testurizzato' }, { value: 'uncertain', label: 'Incerto' },
  ],
  tone: [
    { value: 'warm', label: 'Caldo' }, { value: 'cool', label: 'Freddo' },
    { value: 'neutral', label: 'Neutro' }, { value: 'uncertain', label: 'Incerto' },
  ],
  back_graphic: [
    { value: 'none', label: 'Senza stampa' }, { value: 'small', label: 'Piccola stampa' },
    { value: 'large', label: 'Grafica vistosa' }, { value: 'uncertain', label: 'Incerto' },
  ],
  back_style: [
    { value: 'none', label: 'Nessun impatto' }, { value: 'casual', label: 'Più casual' },
    { value: 'streetwear', label: 'Streetwear' }, { value: 'uncertain', label: 'Incerto' },
  ],
} as const;
export type VisualField = keyof typeof VISUAL_FIELDS;
export type VisualAppearance = {
  pattern: typeof VISUAL_FIELDS.pattern[number]['value'];
  shape: typeof VISUAL_FIELDS.shape[number]['value'];
  surface: typeof VISUAL_FIELDS.surface[number]['value'];
  tone: typeof VISUAL_FIELDS.tone[number]['value'];
  back_graphic: typeof VISUAL_FIELDS.back_graphic[number]['value'];
  back_style: typeof VISUAL_FIELDS.back_style[number]['value'];
  confidence: 'high' | 'medium';
};
export type VisualProfile = VisualAppearance & { reviewed_at: string };
export type AppearanceAnalysis = {
  recognized: boolean; stored: false; draft: VisualAppearance | null;
  revision: number; photo_sha256?: string; message: string; views_analyzed?: 1 | 2;
};
export type AppearancePending = {
  itemId: string; revision: number; photo_sha256: string; draft: VisualAppearance;
};
export type Garment = GarmentInput & {
  photo: string | null; back_photo?: string | null; has_back?: boolean;
  created_at: string; updated_at: string;
  visual_profile?: VisualProfile | null;
};
export const OCCASIONS = [
  { value: 'everyday', label: 'Tutti i giorni' },
  { value: 'work', label: 'Lavoro' },
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
  engine: 'rules-v1' | 'ai-stylist-v1' | 'preference-v1';
  ai_status?: 'ok' | 'not_requested' | 'insufficient_wardrobe' | 'unavailable' | 'invalid_response' | 'rate_limited' | 'not_preferred';
  candidate_count?: number;
  occasion: Occasion; missing: Category[]; message: string;
  outfits: { item_ids: string[]; title: string; why: string;
    verdict?: 'good' | 'acceptable' | 'weak';
    cautions?: string[]; styling_tip?: string; score?: number;
    feedback?: 'like' | 'dislike' | null;
    visual_coverage?: { reviewed: number; total: number } }[];
  /** Today's weather where the person is, when ORA could read it. */
  weather?: { temperature_c: number; condition: string; label: string; place: string };
  /** Cold enough for a jacket, but none is available. */
  layer_missing?: boolean;
};

export const SEASONS: { value: Season; label: string }[] = [
  { value: 'spring', label: 'Primavera' },
  { value: 'summer', label: 'Estate' },
  { value: 'fall', label: 'Autunno' },
  { value: 'winter', label: 'Inverno' },
];

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
  backPhoto: (token: string, item: Garment, photo: Blob) => request<{ item: Garment }>(token,
    `/items/${encodeURIComponent(item.id)}/photo/back?revision=${item.revision}`, {
      method: 'POST', headers: { 'Content-Type': photo.type }, body: photo,
    }),
  removeBackPhoto: (token: string, item: Garment) => request<{ item: Garment }>(token,
    `/items/${encodeURIComponent(item.id)}/photo/back?revision=${item.revision}`, {
      method: 'DELETE',
    }),
  analyze: (token: string, photo: Blob) => request<GarmentAnalysis>(token, '/analyze', {
    method: 'POST', headers: { 'Content-Type': photo.type }, body: photo,
  }),
  analyzeAppearance: (token: string, item: Garment) => request<AppearanceAnalysis>(token,
    `/items/${encodeURIComponent(item.id)}/appearance/analyze?revision=${item.revision}`, { method: 'POST' }),
  confirmAppearance: (token: string, pending: AppearancePending) => request<{ item: Garment }>(token,
    `/items/${encodeURIComponent(pending.itemId)}/appearance`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...pending.draft, revision: pending.revision,
        photo_sha256: pending.photo_sha256 }),
    }),
  clearAppearance: (token: string, item: Garment) => request<{ item: Garment }>(token,
    `/items/${encodeURIComponent(item.id)}/appearance?revision=${item.revision}`, { method: 'DELETE' }),
  feedback: (token: string, occasion: Occasion, itemIds: string[], reaction: 'like' | 'dislike') =>
    request<{ stored: boolean; reaction: 'like' | 'dislike' }>(token, '/outfits/feedback', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ occasion, item_ids: itemIds, reaction }),
    }),
  outfits: (token: string, occasion: Occasion, styleNote = '') => request<OutfitResponse>(token, '/outfits', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ occasion, use_ai: true, style_note: styleNote.slice(0, 200) }),
  }),
};
