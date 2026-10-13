import { API_BASE_URL, authToken } from '@/src/api/client';

export const FORMATS = ['CODE_128', 'EAN_13', 'EAN_8', 'UPC_A', 'CODE_39', 'ITF', 'QR_CODE'] as const;
export type CodeFormat = typeof FORMATS[number];
export type CardInput = {
  id: string; name: string; format: CodeFormat; code: string;
  static_confirmed: boolean; source: 'manual' | 'image'; revision: number; favorite: boolean;
};
export type LoyaltyCard = CardInput & {
  image: string; created_at: string; updated_at: string;
  acceptance: 'not_verified_at_checkout';
};
export type Candidate = { format: CodeFormat; code: string };

async function request<T>(token: string, path: string, init: RequestInit = {}): Promise<T> {
  if (!token || (await authToken.get()) !== token) throw new Error('Sessione cambiata. Riapri il portafoglio.');
  if (!API_BASE_URL) throw new Error('Collegamento al server non configurato.');
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 25_000);
  try {
    const response = await fetch(`${API_BASE_URL}/api/wallet${path}`, {
      ...init, signal: controller.signal, cache: 'no-store',
      headers: { ...init.headers, Authorization: `Bearer ${token}` },
    });
    if ((await authToken.get()) !== token) throw new Error('Sessione cambiata. Riapri il portafoglio.');
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const message = typeof data.detail === 'string' ? data.detail
        : response.status === 422 ? 'Controlla nome, formato e codice della tessera originale.'
        : response.status === 401 ? 'Accedi nuovamente a ORA.' : 'Portafoglio non disponibile. Riprova.';
      throw new Error(message);
    }
    return data as T;
  } catch (error) {
    if (controller.signal.aborted) throw new Error('Il server non ha risposto. Riprova: il salvataggio non viene duplicato.');
    throw error;
  } finally { clearTimeout(timer); }
}

export const walletClient = {
  token: () => authToken.get(),
  list: (token: string) => request<{ cards: LoyaltyCard[] }>(token, '/cards'),
  save: (token: string, card: CardInput) => request<{ card: LoyaltyCard }>(token, '/cards', {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(card),
  }),
  remove: (token: string, card: LoyaltyCard) => request<{ deleted: boolean }>(token,
    `/cards/${encodeURIComponent(card.id)}?revision=${card.revision}`, { method: 'DELETE' }),
  decode: (token: string, photo: Blob) => request<{ candidates: Candidate[] }>(token, '/decode', {
    method: 'POST', headers: { 'Content-Type': photo.type }, body: photo,
  }),
};
