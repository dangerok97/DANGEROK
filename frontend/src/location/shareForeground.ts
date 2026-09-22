import { api } from '@/src/api/client';
import { requestForegroundPosition } from './foregroundGeo';

/** Called by an explicit location action, or after existing ORA consent. */
export async function shareForegroundPosition(): Promise<void> {
  const fix = await requestForegroundPosition({ maximumAgeMs: 0 });
  if (!fix.ok) {
    const state = fix.reason === 'native_unsupported' ? 'unavailable' : fix.reason;
    await api.locationPermissionOutcome(state).catch(() => undefined);
    throw new Error(fix.reason === 'denied'
      ? 'La posizione è bloccata. Consenti la posizione nelle impostazioni del sito del browser e riprova.'
      : fix.reason === 'timeout'
        ? 'Il dispositivo non ha risposto in tempo. Riprova a rilevare la posizione.'
        : 'Il dispositivo non riesce a rilevare la posizione. Verifica che i servizi di localizzazione siano attivi.');
  }
  await api.locationSetPreference('while_using');
  await api.locationPostSignal({ latitude: fix.latitude, longitude: fix.longitude,
    accuracy_meters: fix.accuracyMeters, reverse_geocode: true });
}

let refreshing = false;
let refreshedAt = 0;
export async function refreshConsentedPosition(): Promise<boolean> {
  if (refreshing || Date.now() - refreshedAt < 300_000) return false;
  refreshing = true;
  try {
    const preference = await api.locationGetPreference();
    if (preference.mode !== 'while_using') return false;
    await shareForegroundPosition();
    refreshedAt = Date.now();
    return true;
  } finally { refreshing = false; }
}
