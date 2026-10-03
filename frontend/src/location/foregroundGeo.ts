/**
 * Device geolocation helpers.
 *
 * Browser requests stay on the browser API. Installed iOS/Android builds use
 * expo-location. The distinction matters because AI Core asks the *client* for
 * a current fix; a native client must never answer that request with the old
 * web-only "native_unsupported" result.
 *
 * Default getCurrentPosition options:
 * - enableHighAccuracy: false
 * - timeout: 12000ms (override via timeoutMs)
 * - maximumAge: 60000ms default; pass maximumAgeMs: 0 for forced fresh fix (STALE refresh)
 */
import { Platform } from 'react-native';

export type ForegroundGeoResult =
  | { ok: true; latitude: number; longitude: number; accuracyMeters?: number }
  | {
      ok: false;
      reason:
        | 'unavailable'
        | 'denied'
        | 'timeout'
        | 'position_unavailable'
        | 'native_unsupported';
    };

export function isWebGeolocationAvailable(): boolean {
  if (Platform.OS !== 'web') return false;
  const geo = (globalThis as any)?.navigator?.geolocation;
  return Boolean(geo?.getCurrentPosition);
}

/** Browser Geolocation — never put coords in URL. */
export function requestForegroundPosition(
  opts?: { timeoutMs?: number; maximumAgeMs?: number },
): Promise<ForegroundGeoResult> {
  if (Platform.OS !== 'web') {
    return Promise.resolve({ ok: false, reason: 'native_unsupported' });
  }
  const geo = (globalThis as any)?.navigator?.geolocation;
  if (!geo?.getCurrentPosition) {
    return Promise.resolve({ ok: false, reason: 'unavailable' });
  }
  return new Promise((resolve) => {
    try {
      geo.getCurrentPosition(
        (pos: {
          coords?: { latitude?: number; longitude?: number; accuracy?: number };
        }) => {
          const lat = pos?.coords?.latitude;
          const lon = pos?.coords?.longitude;
          if (typeof lat === 'number' && typeof lon === 'number') {
            resolve({
              ok: true,
              latitude: lat,
              longitude: lon,
              accuracyMeters:
                typeof pos?.coords?.accuracy === 'number'
                  ? pos.coords.accuracy
                  : undefined,
            });
          } else {
            resolve({ ok: false, reason: 'unavailable' });
          }
        },
        (err: { code?: number }) => {
          // 1 PERMISSION_DENIED, 2 POSITION_UNAVAILABLE, 3 TIMEOUT
          if (err?.code === 1) resolve({ ok: false, reason: 'denied' });
          else if (err?.code === 3) resolve({ ok: false, reason: 'timeout' });
          else if (err?.code === 2)
            resolve({ ok: false, reason: 'position_unavailable' });
          else resolve({ ok: false, reason: 'unavailable' });
        },
        {
          enableHighAccuracy: false,
          timeout: opts?.timeoutMs ?? 12000,
          maximumAge: opts?.maximumAgeMs ?? 60000,
        },
      );
    } catch {
      resolve({ ok: false, reason: 'unavailable' });
    }
  });
}

/**
 * Current device fix for an AI Core client action.
 *
 * The server intentionally asks the client instead of guessing what hardware
 * it has. Web uses navigator.geolocation; installed iOS/Android builds use the
 * same balanced native acquisition used by continuous presence.
 */
export async function requestCurrentPosition(
  opts?: { timeoutMs?: number; maximumAgeMs?: number },
): Promise<ForegroundGeoResult> {
  if (Platform.OS === 'web') {
    return requestForegroundPosition(opts);
  }
  if (Platform.OS !== 'ios' && Platform.OS !== 'android') {
    return { ok: false, reason: 'native_unsupported' };
  }
  try {
    // Keep the native module out of the web bundle, like presenceRuntime does.
    const Location = await import('expo-location');
    const currentPermission = await Location.getForegroundPermissionsAsync();
    let status = currentPermission.status;
    if (status !== 'granted') {
      status = (await Location.requestForegroundPermissionsAsync()).status;
    }
    if (status !== 'granted') return { ok: false, reason: 'denied' };

    const fix = await Location.getCurrentPositionAsync({
      accuracy: Location.Accuracy.Balanced,
    });
    return {
      ok: true,
      latitude: fix.coords.latitude,
      longitude: fix.coords.longitude,
      accuracyMeters: fix.coords.accuracy ?? undefined,
    };
  } catch {
    return { ok: false, reason: 'position_unavailable' };
  }
}

/** Fresh departure fix, including installed iOS/Android builds. */
export async function requestDeparturePosition(): Promise<ForegroundGeoResult> {
  return requestCurrentPosition({ timeoutMs: 12000, maximumAgeMs: 0 });
}

export const LOCATION_PERMISSION_COPY =
  "ORA può usare la tua posizione mentre usi l'app per capire meglio dove ti trovi e aiutarti quando il luogo è rilevante.";
