/**
 * A real map, with the pin nailed to the centre and the world moving under it.
 *
 * Google Maps is preferred when this installation has a browser key. When it
 * does not, the web picker falls back to Leaflet + OpenStreetMap so adding a
 * Life Place never depends on an unrelated cloud credential.
 *
 * The map is only a visual chooser. The exact centre selected by the person is
 * returned to PlaceEditor; no map provider gets to decide what the place means.
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
type MapProvider = 'google' | 'leaflet';

let googleScriptPromise: Promise<void> | null = null;
let leafletScriptPromise: Promise<void> | null = null;

function loadGoogleMaps(): Promise<void> {
  if (typeof document === 'undefined') return Promise.reject(new Error('no-dom'));
  if ((globalThis as any).google?.maps) return Promise.resolve();
  if (googleScriptPromise) return googleScriptPromise;

  const url = mapsScriptUrl({ language: 'it', region: 'IT' });
  if (!url) return Promise.reject(new Error('no-key'));

  googleScriptPromise = new Promise<void>((resolve, reject) => {
    const script = document.createElement('script');
    script.src = url;
    script.async = true;
    script.onload = () =>
      (globalThis as any).google?.maps ? resolve() : reject(new Error('no-maps'));
    script.onerror = () => {
      googleScriptPromise = null;
      reject(new Error('script-error'));
    };
    document.head.appendChild(script);
  });
  return googleScriptPromise;
}

function loadLeaflet(): Promise<void> {
  if (typeof document === 'undefined') return Promise.reject(new Error('no-dom'));
  if ((globalThis as any).L?.map) return Promise.resolve();
  if (leafletScriptPromise) return leafletScriptPromise;

  const cssId = 'ora-leaflet-css';
  if (!document.getElementById(cssId)) {
    const css = document.createElement('link');
    css.id = cssId;
    css.rel = 'stylesheet';
    css.href = 'https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css';
    css.crossOrigin = 'anonymous';
    document.head.appendChild(css);
  }

  leafletScriptPromise = new Promise<void>((resolve, reject) => {
    const existing = document.getElementById('ora-leaflet-js') as HTMLScriptElement | null;
    if (existing) {
      const check = () =>
        (globalThis as any).L?.map ? resolve() : reject(new Error('no-leaflet'));
      if ((globalThis as any).L?.map) {
        resolve();
      } else {
        existing.addEventListener('load', check, { once: true });
        existing.addEventListener('error', () => reject(new Error('leaflet-script-error')), {
          once: true,
        });
      }
      return;
    }

    const script = document.createElement('script');
    script.id = 'ora-leaflet-js';
    script.src = 'https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js';
    script.async = true;
    script.crossOrigin = 'anonymous';
    script.onload = () =>
      (globalThis as any).L?.map ? resolve() : reject(new Error('no-leaflet'));
    script.onerror = () => {
      leafletScriptPromise = null;
      reject(new Error('leaflet-script-error'));
    };
    document.head.appendChild(script);
  });

  return leafletScriptPromise;
}

function currentCentre(instance: any, provider: MapProvider | null): MapPoint | null {
  if (!instance || !provider) return null;
  try {
    const c = instance.getCenter();
    if (provider === 'google') {
      return { latitude: c.lat(), longitude: c.lng() };
    }
    return { latitude: Number(c.lat), longitude: Number(c.lng) };
  } catch {
    return null;
  }
}

function panTo(instance: any, provider: MapProvider | null, point: MapPoint): void {
  if (!instance || !provider) return;
  if (provider === 'google') {
    instance.panTo({ lat: point.latitude, lng: point.longitude });
  } else {
    instance.panTo([point.latitude, point.longitude], { animate: false });
  }
}

export function MapPicker({ center, onPointChange, height = 260, testID }: Props) {
  const { colors } = useTheme();
  const [status, setStatus] = React.useState<Status>('idle');
  const container = React.useRef<any>(null);
  const map = React.useRef<any>(null);
  const provider = React.useRef<MapProvider | null>(null);
  const resizeObserver = React.useRef<any>(null);
  const windowResizeHandler = React.useRef<(() => void) | null>(null);
  const latest = React.useRef(onPointChange);
  latest.current = onPointChange;

  React.useEffect(() => {
    if (Platform.OS !== 'web') {
      setStatus('unavailable');
      return;
    }

    let cancelled = false;
    setStatus('loading');

    const notifyCentre = () => {
      const point = currentCentre(map.current, provider.current);
      if (point) latest.current(point);
    };

    const keepCentreOnResize = () => {
      const point = currentCentre(map.current, provider.current);
      if (!map.current || !point) return;

      if (provider.current === 'google') {
        const g = (globalThis as any).google?.maps;
        try {
          g?.event?.trigger(map.current, 'resize');
        } catch {}
        map.current.setCenter({ lat: point.latitude, lng: point.longitude });
        return;
      }

      try {
        map.current.invalidateSize({ pan: false, debounceMoveend: true });
        map.current.setView(
          [point.latitude, point.longitude],
          map.current.getZoom(),
          { animate: false },
        );
      } catch {}
    };

    const observeSize = () => {
      if (!container.current) return;
      if (typeof ResizeObserver !== 'undefined') {
        resizeObserver.current = new ResizeObserver(() => {
          requestAnimationFrame(keepCentreOnResize);
        });
        resizeObserver.current.observe(container.current);
      } else if (typeof window !== 'undefined') {
        windowResizeHandler.current = keepCentreOnResize;
        window.addEventListener('resize', keepCentreOnResize);
      }
      requestAnimationFrame(() => requestAnimationFrame(keepCentreOnResize));
    };

    const startGoogle = async () => {
      await loadGoogleMaps();
      if (cancelled || !container.current) return false;

      const g = (globalThis as any).google.maps;
      provider.current = 'google';
      map.current = new g.Map(container.current, {
        center: { lat: center.latitude, lng: center.longitude },
        zoom: 17,
        disableDefaultUI: true,
        zoomControl: true,
        gestureHandling: 'greedy',
        clickableIcons: false,
        styles: [
          { featureType: 'poi', stylers: [{ visibility: 'off' }] },
          { featureType: 'transit', stylers: [{ visibility: 'off' }] },
        ],
      });
      map.current.addListener('idle', notifyCentre);
      observeSize();
      setStatus('ready');
      return true;
    };

    const startLeaflet = async () => {
      await loadLeaflet();
      if (cancelled || !container.current) return false;

      const L = (globalThis as any).L;
      provider.current = 'leaflet';
      map.current = L.map(container.current, {
        center: [center.latitude, center.longitude],
        zoom: 17,
        zoomControl: true,
        attributionControl: true,
      });
      L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '&copy; OpenStreetMap contributors',
      }).addTo(map.current);
      map.current.on('moveend', notifyCentre);
      observeSize();
      setStatus('ready');
      return true;
    };

    const boot = async () => {
      if (mapsStatus().available) {
        try {
          if (await startGoogle()) return;
        } catch {
          // A missing/referrer-rejected Google key must not make Places unusable.
          provider.current = null;
          map.current = null;
        }
      }

      try {
        await startLeaflet();
      } catch {
        if (!cancelled) setStatus('failed');
      }
    };

    void boot();

    return () => {
      cancelled = true;
      try {
        resizeObserver.current?.disconnect?.();
      } catch {}
      resizeObserver.current = null;

      if (typeof window !== 'undefined' && windowResizeHandler.current) {
        window.removeEventListener('resize', windowResizeHandler.current);
      }
      windowResizeHandler.current = null;

      try {
        if (provider.current === 'leaflet') {
          map.current?.off?.();
          map.current?.remove?.();
        } else if (provider.current === 'google') {
          (globalThis as any).google?.maps?.event?.clearInstanceListeners?.(map.current);
        }
      } catch {}
      map.current = null;
      provider.current = null;
    };
    // Only the first centre matters: re-centring on every parent render would
    // fight the person's own dragging.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /** Re-centre when the caller genuinely moves it — a new address picked. */
  React.useEffect(() => {
    if (status !== 'ready' || !map.current) return;
    const current = currentCentre(map.current, provider.current);
    if (!current) return;
    const moved =
      Math.abs(current.latitude - center.latitude) > 1e-6 ||
      Math.abs(current.longitude - center.longitude) > 1e-6;
    if (moved) {
      panTo(map.current, provider.current, center);
    }
  }, [center.latitude, center.longitude, status]);

  if (status === 'unavailable' || status === 'failed') {
    return (
      <View
        style={[
          styles.fallback,
          { height, borderColor: colors.border, backgroundColor: colors.surface },
        ]}
        testID={testID ? `${testID}-unavailable` : undefined}
      >
        <Text style={[styles.fallbackText, { color: colors.textSecondary }]}>
          {Platform.OS !== 'web'
            ? 'La mappa è disponibile nella versione web di ORA.'
            : 'Non riesco a caricare la mappa in questo momento. Puoi salvare il luogo e sistemare il punto più tardi.'}
        </Text>
      </View>
    );
  }

  return (
    <View style={[styles.frame, { height, borderColor: colors.border }]} testID={testID}>
      <View ref={container} style={styles.canvas} />
      {status !== 'ready' ? (
        <View style={[styles.loading, { backgroundColor: colors.surface }]}>
          <ActivityIndicator color={colors.textTertiary} />
        </View>
      ) : null}
      <View pointerEvents="none" style={styles.pinLayer}>
        <View
          pointerEvents="none"
          style={[
            styles.pin,
            { backgroundColor: colors.accent, borderColor: colors.surface },
          ]}
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
    width: '100%',
    minWidth: 0,
  },
  canvas: { flex: 1, width: '100%', height: '100%' },
  loading: {
    ...StyleSheet.absoluteFillObject,
    alignItems: 'center',
    justifyContent: 'center',
  },
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
