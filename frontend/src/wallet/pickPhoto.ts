import { Platform } from 'react-native';
import * as DocumentPicker from 'expo-document-picker';

/** Foreground selection only. A photo is uploaded to ORA, not to an AI provider. */
export async function pickPhoto(camera = false): Promise<Blob | null> {
  if (Platform.OS === 'web' && typeof document !== 'undefined') {
    return new Promise((resolve, reject) => {
      const input = document.createElement('input');
      input.type = 'file'; input.accept = 'image/jpeg,image/png,image/webp';
      if (camera) input.setAttribute('capture', 'environment');
      input.style.display = 'none';
      let done = false;
      const finish = (file: File | null) => {
        if (done) return;
        done = true;
        window.removeEventListener('focus', focused);
        input.remove();
        if (file && file.size > 8 * 1024 * 1024) reject(new Error('La foto supera 8 MB. Ritaglia il codice.'));
        else resolve(file);
      };
      const focused = () => setTimeout(() => { if (!input.files?.length) finish(null); }, 700);
      input.onchange = () => finish(input.files?.[0] ?? null);
      input.addEventListener('cancel', () => finish(null), { once: true });
      window.addEventListener('focus', focused, { once: true });
      document.body.appendChild(input);
      input.click();
    });
  }
  const picked = await DocumentPicker.getDocumentAsync({
    type: ['image/jpeg', 'image/png', 'image/webp'], copyToCacheDirectory: true, multiple: false,
  });
  if (picked.canceled) return null;
  const asset = picked.assets[0];
  if ((asset.size ?? 0) > 8 * 1024 * 1024) throw new Error('La foto supera 8 MB. Ritaglia il codice.');
  const blob = await (await fetch(asset.uri)).blob();
  return new Blob([blob], { type: asset.mimeType || blob.type || 'image/jpeg' });
}
