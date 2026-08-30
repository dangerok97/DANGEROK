/**
 * A real map, with the pin nailed to the centre and the world moving under it.
 *
 *     GOOGLE SUGGESTS. MAP VISUALIZES. USER CONFIRMS.
 *
 * The pattern is deliberate. A draggable marker asks somebody to hit a target
 * a few pixels wide with a thumb that covers forty; a fixed centre lets them
 * move the whole map with the gesture phones are best at, and the point is
 * wherever the crosshair ends up. It is also honest about what is being
 * chosen: the thing in the middle.
 *
 * Google's pin is a suggestion, not an answer. It lands on the street outside,
 * and the entrance is often round the back — so whatever the person leaves in
 * the centre wins, and the caller records that it came from the map.
 *
 * Web only. The Maps JavaScript API is a browser API; on a device this renders
 * an honest refusal rather than a grey rectangle, and the key comes from the
 * environment (see src/config/maps.ts) and never from this file.
 */
import * as React from 'react';
import { ActivityIndicator, Platform, StyleSheet, Text, View } from 'react-native';

import { mapsScriptUrl, mapsStatus } from '@/src/config/maps';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';

export type MapPoint = { latitude: number; longitude: number };

type Props = {
  /** Where to open. The caller decides; this never invents a location. */
  center: MapPoint;
  /** Fired as the map settles, with whatever is under the crosshair. */
  onPointChange: (point: MapPoint) => void;
  height?: number;
  testID?: string;
};

type Status = 'idle' | 'loading' | 'ready' | 'unavailable' | 'failed';

let scriptPromise: Promise<void> | null = null;

/**
 * Load the Maps script once per page.
 *
 * Two pickers on one screen must not append two script tags; the second would
 * race the first and one of them would lose.
 */
function loadMaps(): Promise<void> {
  if (typeof document === 'undefined') return Promise.reject(new Error('no-dom'));
  if ((globalThis as any).google?.maps) return Promise.resolve();
  if (scriptPromise) return scriptPromise;

  const url = mapsScriptUrl({ language: 'it', region: 'IT' });
  if (!url) return Promise.reject(new Error('no-key'));

  scriptPromise = new Promise<void>((resolve, reject) => {
    const script = document.createElement('script');
    script.src = url;
    script.async = true;
    script.onload = () =>
      (globalThis as any).google?.maps ? resolve() : reject(new Error('no-maps'));
    // A referrer the key does not authorise fails here, and the person is told
    // the map is unavailable rather than left looking at nothing.
    script.onerror = () => {
      scriptPromise = null;
      reject(new Error('script-error'));
    };
    document.head.appendChild(script);
  });
  return scriptPromise;
}

export function MapPicker({ center, onPointChange, height = 260, testID }: Props) {
  const { colors } = useTheme();
  const [status, setStatus] = React.useState<Status>('idle');
  const container = React.useRef<any>(null);
  const map = React.useRef<any>(null);
  const latest = React.useRef(onPointChange);
  latest.current = onPointChange;

  React.useEffect(() => {
    if (Platform.OS !== 'web') {
      setStatus('unavailable');
      return;
    }
    if (!mapsStatus().available) {
      setStatus('unavailable');
      return;
    }

    let cancelled = false;
    setStatus('loading');
    loadMaps()
      .then(() => {
        if (cancelled || !container.current) return;
        const g = (globalThis as any).google.maps;
        map.current = new g.Map(container.current, {
          center: { lat: center.latitude, lng: center.longitude },
          zoom: 17,
          // Quiet: this is a picker, not Google Maps. Points of interest and
          // transit lines compete with the one thing being chosen.
          disableDefaultUI: true,
          zoomControl: true,
          gestureHandling: 'greedy',
          clickableIcons: false,
          styles: [
            { featureType: 'poi', stylers: [{ visibility: 'off' }] },
            { featureType: 'transit', stylers: [{ visibility: 'off' }] },
          ],
        });
        // `idle` rather than `center_changed`: the latter fires for every pixel
        // of a drag, and the answer is where the map came to rest.
        map.current.addListener('idle', () => {
          const c = map.current.getCenter();
          latest.current({ latitude: c.lat(), longitude: c.lng() });
        });
        setStatus('ready');
      })
      .catch(() => {
        if (!cancelled) setStatus('failed');
      });

    return () => {
      cancelled = true;
    };
    // Only the first centre matters: re-centring on every parent render would
    // fight the person's own dragging.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /** Re-centre when the caller genuinely moves it — a new address picked. */
  React.useEffect(() => {
    if (status !== 'ready' || !map.current) return;
    const c = map.current.getCenter();
    const moved =
      Math.abs(c.lat() - center.latitude) > 1e-6 ||
      Math.abs(c.lng() - center.longitude) > 1e-6;
    if (moved) {
      map.current.panTo({ lat: center.latitude, lng: center.longitude });
    }
  }, [center.latitude, center.longitude, status]);

  if (status === 'unavailable' || status === 'failed') {
    return (
      <View
        style={[styles.fallback, { height, borderColor: colors.border, backgroundColor: colors.surface }]}
        testID={testID ? `${testID}-unavailable` : undefined}
      >
        <Text style={[styles.fallbackText, { color: colors.textSecondary }]}>
          {Platform.OS !== 'web'
            ? 'La mappa è disponibile nella versione web di ORA.'
            : status === 'failed'
              ? 'Non riesco a caricare la mappa in questo momento. Puoi salvare il luogo e sistemare il punto più tardi.'
              : 'La mappa non è configurata su questa installazione.'}
        </Text>
      </View>
    );
  }

  return (
    <View style={[styles.frame, { height, borderColor: colors.border }]} testID={testID}>
      {/* On web this ref is the DOM node the Maps API mounts into. */}
      <View ref={container} style={styles.canvas} />
      {status !== 'ready' ? (
        <View style={[styles.loading, { backgroundColor: colors.surface }]}>
          <ActivityIndicator color={colors.textTertiary} />
        </View>
      ) : null}
      {/* The crosshair. Never moves; the map does.

          `pointerEvents="none"` is repeated on the children on purpose: React
          Native Web writes `pointer-events: auto` onto every View, which
          overrides the parent's `none` in CSS. Without it the pin sits exactly
          where a drag begins and swallows it, and the map cannot be moved at
          all — found by QA, because the pin looked right and did nothing. */}
      <View pointerEvents="none" style={styles.pinLayer}>
        <View
          pointerEvents="none"
          style={[styles.pin, { backgroundColor: colors.accent, borderColor: colors.surface }]}
        />
        <View
          pointerEvents="none"
          style={[styles.pinStem, { backgroundColor: colors.accent }]}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  frame: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.md,
    overflow: 'hidden',
    position: 'relative',
  },
  canvas: { flex: 1, width: '100%', height: '100%' },
  loading: { ...StyleSheet.absoluteFillObject, alignItems: 'center', justifyContent: 'center' },
  pinLayer: {
    ...StyleSheet.absoluteFillObject,
    alignItems: 'center',
    justifyContent: 'center',
  },
  pin: {
    width: 16,
    height: 16,
    borderRadius: 8,
    borderWidth: 3,
    // Lifted by half the stem so the point of contact is the exact centre.
    marginBottom: 14,
  },
  pinStem: { position: 'absolute', width: 2, height: 14, marginTop: 8 },
  fallback: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.md,
    alignItems: 'center',
    justifyContent: 'center',
    padding: tokens.spacing.lg,
  },
  fallbackText: { fontSize: 13, lineHeight: 18, textAlign: 'center' },
});
