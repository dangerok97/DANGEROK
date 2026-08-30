/**
 * The browser key for Maps JavaScript, read from the environment.
 *
 * A Maps JS key is a browser key by definition — it ships in the bundle and
 * anybody can read it out of the page. That is not a leak, it is how the API
 * works, and its safety comes from the restrictions set on it in Google Cloud:
 * Maps JavaScript API only, and only from authorised referrers. A key with
 * those restrictions is worth nothing to somebody who copies it.
 *
 * What must not happen is the key living in the repository. It arrives through
 * `EXPO_PUBLIC_MAPS_WEB_KEY`, which Expo inlines at bundle time from an
 * ignored `.env` or from the shell — the same mechanism the Google sign-in
 * client ids already use. Only the variable name appears here.
 *
 * The Places key is deliberately not in this file and must never be: Places
 * (New) opens a far larger surface than a map tile, so it stays server-side.
 */
import { Platform } from 'react-native';

export const MAPS_WEB_KEY_ENV = 'EXPO_PUBLIC_MAPS_WEB_KEY';

function key(): string {
  return (process.env.EXPO_PUBLIC_MAPS_WEB_KEY || '').trim();
}

/** Whether an interactive map can be shown at all here. */
export function mapsAvailable(): boolean {
  return Boolean(key());
}

/**
 * What a caller needs to decide whether to render a map, without handing the
 * key to anything that does not need it.
 */
export function mapsStatus(): {
  available: boolean;
  platform: string;
  reason?: string;
} {
  if (!key()) {
    return {
      available: false,
      platform: Platform.OS,
      reason: `Maps non configurato: manca ${MAPS_WEB_KEY_ENV}.`,
    };
  }
  return { available: true, platform: Platform.OS };
}

/**
 * The script URL for the Maps JavaScript API.
 *
 * Returns null rather than a URL with an empty key: a script tag that fails to
 * authorise leaves a grey box and a console error, and a caller that knows the
 * map is unavailable can say so instead.
 */
export function mapsScriptUrl(
  options: { libraries?: string[]; language?: string; region?: string } = {},
): string | null {
  const apiKey = key();
  if (!apiKey) return null;

  const params = new URLSearchParams({ key: apiKey, v: 'weekly' });
  if (options.libraries?.length) params.set('libraries', options.libraries.join(','));
  params.set('language', options.language ?? 'it');
  if (options.region) params.set('region', options.region);
  return `https://maps.googleapis.com/maps/api/js?${params.toString()}`;
}
