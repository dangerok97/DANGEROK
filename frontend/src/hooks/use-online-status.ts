/**
 * Lightweight cross-platform online detector.
 * Uses navigator.onLine + online/offline events on web.
 * On native, we optimistically assume online and downgrade only when
 * a request throws a network error (surfaced from the caller).
 */
import { useEffect, useState, useCallback } from 'react';
import { Platform } from 'react-native';

export function useOnlineStatus() {
  const [online, setOnline] = useState<boolean>(true);

  useEffect(() => {
    if (Platform.OS !== 'web') return;
    const win: any = typeof window !== 'undefined' ? window : null;
    if (!win) return;
    const update = () => setOnline(Boolean(win.navigator?.onLine));
    update();
    win.addEventListener('online', update);
    win.addEventListener('offline', update);
    return () => {
      win.removeEventListener('online', update);
      win.removeEventListener('offline', update);
    };
  }, []);

  const markOffline = useCallback(() => setOnline(false), []);
  const markOnline = useCallback(() => setOnline(true), []);

  return { online, markOffline, markOnline };
}

/**
 * Detects "network error"-style errors coming from fetch. HTTP errors with
 * a status code are treated as ONLINE (server responded, just not 2xx).
 */
export function isNetworkError(err: any): boolean {
  if (!err) return false;
  if (err.status && typeof err.status === 'number') return false;
  const msg = String(err?.message || '').toLowerCase();
  return (
    msg.includes('network request failed') ||
    msg.includes('failed to fetch') ||
    msg.includes('load failed') ||
    msg.includes('networkerror') ||
    msg.includes('typeerror: network')
  );
}
