import { Linking, Platform } from 'react-native';
import { Router } from 'expo-router';
import { HomeActionDef, HomeItem } from '@/src/api/client';
import { ActionEngine } from '@/src/action-engine';
import { ConversationEngine } from '@/src/conversation-engine';

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

/** True when this action must open the guided Action Engine (never empty page). */
export function isGuidedAction(action: HomeActionDef): boolean {
  if (action.kind === 'guide') return true;
  if (action.kind === 'open') return true;
  if (action.route === '/action/open') return true;
  if (action.route?.startsWith('/action/') && action.kind === 'resume') return false;
  const labels = (action.label || '').toLowerCase();
  return ['apri', 'organizza', 'inizia'].some((l) => labels === l || labels.startsWith(l + ' '));
}

export async function navigateHomeAction(
  router: Router,
  action: HomeActionDef,
  item?: HomeItem | null,
) {
  if (action.kind === 'maps') {
    openMapsQuery((action.params?.query as string) || item?.location || item?.title);
    return;
  }

  // Resume Conversation Engine → bridge to AE one-question UI
  const cesId =
    (action.params?.conversation_session_id as string | undefined) ||
    (item?.source_type === 'conversation_session' ? item.source_id : undefined) ||
    (item?.meta?.conversation_session_id as string | undefined);
  if (action.kind === 'resume' && cesId && item?.source_type === 'conversation_session') {
    await ConversationEngine.resume(router, { session_id: cesId });
    return;
  }

  // Resume existing action session
  if (action.kind === 'resume' && action.route?.startsWith('/action/')) {
    router.push(action.route as any);
    return;
  }

  if (action.kind === 'resume' && action.route?.startsWith('/conversation')) {
    if (cesId) {
      await ConversationEngine.resume(router, { session_id: cesId });
      return;
    }
    router.push(action.route as any);
    return;
  }

  // Central Action Engine — Apri / Organizza / Inizia / guide
  if (item && isGuidedAction(action)) {
    await ActionEngine.open(item, router);
    return;
  }

  // Document study modes (flashcards/quiz) stay on document route
  const route = action.route || (item ? routeForItem(item) : null);
  if (!route) {
    if (item) {
      await ActionEngine.open(item, router);
    }
    return;
  }
  if (route === '/action/open' && item) {
    await ActionEngine.open(item, router);
    return;
  }
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
  if (st === 'conversation_session') {
    const actionSid = item.meta?.action_session_id as string | undefined;
    if (actionSid) return `/action/${actionSid}`;
    return `/conversation?resume=${sid}`;
  }
  if (st === 'action_session') return `/action/${sid}`;
  if (st === 'action_project') return '/action/open';
  // Card press → Action Engine (guided), not empty document/situazione
  return '/action/open';
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
