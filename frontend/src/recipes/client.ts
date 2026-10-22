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
};
export type Recipe = RecipeWrite & {
  id: string;
  created_at: string;
  updated_at: string;
};
export type RecipePreview = {
  draft: Omit<RecipeWrite, 'revision'>;
  quality: 'link_only' | 'structured_text' | 'partial_text';
  warnings: string[];
};

export function toRecipeWrite(item: Recipe): RecipeWrite {
  const { revision, title, source_url, source_text, ingredients, steps, tags, servings, favorite, status } = item;
  return { revision, title, source_url, source_text, ingredients, steps, tags, servings, favorite, status };
}

async function request<T>(token: string, path: string, init: RequestInit = {}): Promise<T> {
  if (!token || (await authToken.get()) !== token) throw new Error('La sessione è cambiata. Riapri Cucina.');
  if (!API_BASE_URL) throw new Error('Collegamento a ORA non configurato.');
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 20000);
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
  preview: (token: string, source: string) => request<RecipePreview>(token, '/preview', {
    method: 'POST', body: JSON.stringify({ source }),
  }),
  create: (token: string, body: RecipeWrite) => request<{ item: Recipe; created: boolean }>(token, '/items', {
    method: 'POST', body: JSON.stringify(body),
  }),
  update: (token: string, id: string, body: RecipeWrite) => request<{ item: Recipe }>(token,
    `/items/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify(body) }),
  remove: (token: string, item: Recipe) => request<{ deleted: boolean }>(token,
    `/items/${encodeURIComponent(item.id)}?revision=${item.revision}`, { method: 'DELETE' }),
};
