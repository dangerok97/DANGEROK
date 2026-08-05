import { Linking, Platform } from 'react-native';
import { Router } from 'expo-router';
import { HomeActionDef, HomeItem } from '@/src/api/client';

export function openMapsQuery(query?: string | null) {
  if (!query) return;
  const q = encodeURIComponent(query);
  const url = Platform.select({
    ios: `maps:0,0?q=${q}`,
    android: `geo:0,0?q=${q}`,
    default: `https://www.google.com/maps/search/?api=1&query=${q}`,
  })!;
  Linking.openURL(url).catch(() => {
    Linking.openURL(`https://www.google.com/maps/search/?api=1&query=${q}`);
  });
}

export function navigateHomeAction(router: Router, action: HomeActionDef, item?: HomeItem | null) {
  if (action.kind === 'maps') {
    openMapsQuery((action.params?.query as string) || item?.location || item?.title);
    return;
  }
  const route = action.route || (item ? routeForItem(item) : null);
  if (!route) return;
  const mode = action.params?.mode;
  if (mode && route.startsWith('/document/')) {
    router.push({ pathname: route as any, params: { mode: String(mode) } } as any);
    return;
  }
  router.push(route as any);
}

export function routeForItem(item: HomeItem): string {
  const st = item.source_type;
  const sid = item.source_id;
  if (['document', 'event_candidate', 'document_action', 'study', 'admin', 'quiz_session'].includes(st)) {
    return `/document/${sid}`;
  }
  if (st === 'life_node' || st === 'google_calendar' || st === 'internal_calendar') {
    return '/situazione';
  }
  return '/situazione';
}

export function formatWhen(iso?: string | null): string | null {
  if (!iso) return null;
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return null;
    return d.toLocaleString('it-IT', {
      weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return null;
  }
}
