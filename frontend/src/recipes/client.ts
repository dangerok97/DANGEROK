import { API_BASE_URL, authToken } from '@/src/api/client';

/** An explicit source is always retained; only user-reviewed data is saved. */
export type RecipeWrite = {
  revision: number;
  title: string;
  source_url: string;
  source_text: string;
  ingredients: string[];
  steps: string[];
  tags: string[];
  servings: number | null;
  favorite: boolean;
  status: 'to_try' | 'cooked';
  image_url?: string;
  total_minutes?: number | null;
};
export type Recipe = RecipeWrite & {
  id: string;
  created_at: string;
  updated_at: string;
};
export type RecipePreview = {
  draft: Omit<RecipeWrite, 'revision'>;
  quality: 'link_only' | 'structured_text' | 'partial_text' | 'structured_page'
    | 'ai_from_caption' | 'ai_from_text' | 'ai_from_photo' | 'unreadable';
  warnings: string[];
  source_label?: string;
};

export function toRecipeWrite(item: Recipe): RecipeWrite {
  const { revision, title, source_url, source_text, ingredients, steps, tags, servings, favorite, status } = item;
  return { revision, title, source_url, source_text, ingredients, steps, tags, servings, favorite, status,
    image_url: item.image_url || '', total_minutes: item.total_minutes ?? null };
}

async function request<T>(token: string, path: string, init: RequestInit = {}, waitMs = 20000): Promise<T> {
  if (!token || (await authToken.get()) !== token) throw new Error('La sessione è cambiata. Riapri Cucina.');
  if (!API_BASE_URL) throw new Error('Collegamento a ORA non configurato.');
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), waitMs);
  try {
    const response = await fetch(`${API_BASE_URL}/api/recipes${path}`, {
      ...init,
      signal: controller.signal,
      cache: 'no-store',
      headers: { 'Content-Type': 'application/json', ...init.headers, Authorization: `Bearer ${token}` },
    });
    if ((await authToken.get()) !== token) throw new Error('La sessione è cambiata. Riapri Cucina.');
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(typeof data.detail === 'string' ? data.detail :
        response.status === 401 ? 'Accedi nuovamente a ORA.' : 'Cucina non disponibile. Riprova.');
    }
    return data as T;
  } catch (e) {
    if (controller.signal.aborted) throw new Error('ORA non ha risposto. Controlla il ricettario prima di riprovare.');
    throw e;
  } finally {
    clearTimeout(timeout);
  }
}

export const recipesClient = {
  token: () => authToken.get(),
  list: (token: string) => request<{ items: Recipe[] }>(token, '/items'),
  // Reading a page or a caption with AI can take a while: wait longer.
  preview: (token: string, source: string) => request<RecipePreview>(token, '/preview', {
    method: 'POST', body: JSON.stringify({ source }),
  }, 55000),
  previewPhoto: (token: string, photo: Blob) => request<RecipePreview>(token, '/preview-photo', {
    method: 'POST', headers: { 'Content-Type': photo.type || 'image/jpeg' }, body: photo,
  }, 55000),
  addToShopping: async (token: string, names: string[]) => {
    const monday = new Date(); monday.setHours(12, 0, 0, 0);
    monday.setDate(monday.getDate() - ((monday.getDay() + 6) % 7));
    const week = monday.toISOString().slice(0, 10);
    for (const name of names) {
      const res = await fetch(`${API_BASE_URL}/api/cooking/shopping-list/manual?week_start=${week}`, {
        method: 'POST', cache: 'no-store',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ name: name.slice(0, 180) }),
      });
      if (!res.ok) throw new Error('Lista della spesa non disponibile. Riprova.');
    }
    return week;
  },
  create: (token: string, body: RecipeWrite) => request<{ item: Recipe; created: boolean }>(token, '/items', {
    method: 'POST', body: JSON.stringify(body),
  }),
  update: (token: string, id: string, body: RecipeWrite) => request<{ item: Recipe }>(token,
    `/items/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify(body) }),
  remove: (token: string, item: Recipe) => request<{ deleted: boolean }>(token,
    `/items/${encodeURIComponent(item.id)}?revision=${item.revision}`, { method: 'DELETE' }),
};
