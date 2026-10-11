/** Contract for ORA Vision X-Ray. Never store photo bytes in app memory/state beyond a scan. */
import { API_BASE_URL, authToken } from '@/src/api/client';

export type XrayPart = {
  id: string;
  name: string;
  function: string;
  how_it_works: string;
  certainty: 'visible' | 'typical';
  visual_kind: 'body' | 'board' | 'button' | 'battery' | 'sensor' | 'connector' | 'other';
};

export type XrayResult = {
  object_name: string;
  object_category: string;
  what_i_see: string;
  confidence: 'high' | 'medium' | 'low';
  parts: XrayPart[];
  safety_note: string;
  unknowns: string;
  visualization: 'illustrative_exploded_2d';
  verified_3d_model: false;
};

const MAX_IMAGE_BYTES = 6 * 1024 * 1024;

export async function scanObject(dataUri: string): Promise<XrayResult> {
  const match = /^data:(image\/(?:png|jpeg|webp));base64,([A-Za-z0-9+/=]+)$/.exec(dataUri);
  if (!match) throw new Error('Usa una foto JPEG, PNG o WebP.');
  const raw = match[2];
  if (raw.length > Math.ceil(MAX_IMAGE_BYTES / 3) * 4) {
    throw new Error('Foto troppo grande. Il limite è 6 MB.');
  }
  if (!API_BASE_URL) throw new Error('Collegamento al motore di ORA non configurato.');
  const token = await authToken.get();
  if (!token) throw new Error('Accedi a ORA per analizzare l’oggetto.');
  const controller = new AbortController();
  const deadline = setTimeout(() => controller.abort(), 55_000);
  try {
    const response = await fetch(API_BASE_URL + '/api/vision-xray/scan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token },
      body: JSON.stringify({ mime_type: match[1], image_base64: raw }),
      signal: controller.signal,
    });
    const result = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = result?.detail;
      throw new Error(typeof detail === 'string' ? detail : 'ORA non riesce ad analizzare questa foto.');
    }
    return result as XrayResult;
  } catch (error: any) {
    if (error?.name === 'AbortError') throw new Error('L’analisi è scaduta. Riprova.');
    throw error;
  } finally {
    clearTimeout(deadline);
  }
}

/** Browser blob URL or native picker URI => ephemeral data URI. */
export async function imageUriAsData(uri: string, declaredType?: string): Promise<string> {
  const response = await fetch(uri);
  if (!response.ok) throw new Error('Impossibile aprire la foto.');
  const original = await response.blob();
  if (original.size > MAX_IMAGE_BYTES) throw new Error('Foto troppo grande. Il limite è 6 MB.');
  const mime = original.type || declaredType || '';
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(mime)) {
    throw new Error('Formato non supportato. Prova con JPEG, PNG o WebP.');
  }
  return await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error('Non riesco a leggere la foto.'));
    reader.onload = () => {
      const value = String(reader.result || '');
      if (!value.startsWith('data:')) return reject(new Error('Foto non leggibile.'));
      resolve(value);
    };
    reader.readAsDataURL(original);
  });
}
