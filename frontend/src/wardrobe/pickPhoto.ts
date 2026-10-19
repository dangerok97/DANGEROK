import { Platform } from 'react-native';
import * as DocumentPicker from 'expo-document-picker';

/** Explicit foreground selection. Never uploads to a third-party AI provider. */
export async function pickGarmentPhoto(): Promise<Blob | null> {
  if (Platform.OS === 'web' && typeof document !== 'undefined') {
    return new Promise((resolve, reject) => {
      const input = document.createElement('input');
      input.type = 'file'; input.accept = 'image/jpeg,image/png,image/webp';
      input.style.display = 'none';
      let done = false;
      const end = (file: File | null) => {
        if (done) return;
        done = true;
        window.removeEventListener('focus', focus);
        input.remove();
        if (file && file.size > 5 * 1024 * 1024) reject(new Error('Foto troppo grande: massimo 5 MB.'));
        else resolve(file);
      };
      const focus = () => setTimeout(() => { if (!input.files?.length) end(null); }, 700);
      input.onchange = () => end(input.files?.[0] ?? null);
      input.addEventListener('cancel', () => end(null), { once: true });
      window.addEventListener('focus', focus, { once: true });
      document.body.appendChild(input);
      input.click();
    });
  }
  const picked = await DocumentPicker.getDocumentAsync({
    type: ['image/jpeg', 'image/png', 'image/webp'], copyToCacheDirectory: true, multiple: false,
  });
  if (picked.canceled || !picked.assets?.[0]) return null;
  const asset = picked.assets[0];
  if ((asset.size ?? 0) > 5 * 1024 * 1024) throw new Error('Foto troppo grande: massimo 5 MB.');
  const data = await (await fetch(asset.uri)).blob();
  if (data.size > 5 * 1024 * 1024) throw new Error('Foto troppo grande: massimo 5 MB.');
  return new Blob([data], { type: asset.mimeType || data.type || 'image/jpeg' });
}
