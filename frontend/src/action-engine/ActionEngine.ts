/**
 * Central Action Engine entry — Home Apri / Organizza / Inizia / card press.
 * No scattered switch logic in UI screens.
 */
import { Router } from 'expo-router';
import { api, ActionEngineOpenResult, ActionEngineSession, HomeItem } from '@/src/api/client';

export type ActionEngineItem = Pick<
  HomeItem,
  'id' | 'type' | 'title' | 'description' | 'source_type' | 'source_id' | 'location' | 'due_at' | 'start_at' | 'amount' | 'meta'
> & { actions?: HomeItem['actions'] };

async function openSession(item: ActionEngineItem): Promise<ActionEngineOpenResult> {
  const meta = item.meta || {};
  const precomputed =
    (meta as any).classified_intent ||
    ((meta as any).intent
      ? {
          intent: (meta as any).intent,
          subtype: (meta as any).intent_subtype,
          confidence: (meta as any).intent_confidence ?? 0.9,
          entities: (meta as any).intent_entities || {},
          needs_clarify: false,
          reason: 'home_meta',
        }
      : undefined);
  return api.actionEngineOpen({
    home_item: {
      id: item.id,
      type: item.type,
      title: item.title,
      description: item.description,
      source_type: item.source_type,
      source_id: item.source_id,
      location: item.location,
      due_at: item.due_at,
      start_at: item.start_at,
      amount: item.amount,
      meta,
      intent: (meta as any).intent,
      intent_subtype: (meta as any).intent_subtype,
      intent_confidence: (meta as any).intent_confidence,
      intent_entities: (meta as any).intent_entities,
    },
    home_item_id: item.id,
    source_type: item.source_type,
    source_id: item.source_id,
    // item_type is informational only — Intent Engine owns flow choice
    item_type: item.type,
    title: item.title,
    description: item.description || undefined,
    location: item.location || undefined,
    due_at: item.due_at || undefined,
    start_at: item.start_at || undefined,
    intent: precomputed,
    meta,
  });
}

/**
 * Open a guided flow for a Home priority.
 * Always navigates to a conversational screen with a first question —
 * never an empty page.
 */
export const ActionEngine = {
  async open(item: ActionEngineItem, router: Router): Promise<ActionEngineSession> {
    // Resume existing action session route directly
    if (item.source_type === 'action_session' && item.source_id) {
      router.push(`/action/${item.source_id}` as any);
      const existing = await api.actionEngineGetSession(item.source_id);
      return existing.session;
    }

    const result = await openSession(item);
    const session = result.session;
    if (!session?.id) {
      throw new Error('Action Engine non ha creato una sessione');
    }
    if (session.status === 'active' && !session.current_turn) {
      throw new Error('Flusso senza domanda — riprova');
    }
    router.push(`/action/${session.id}` as any);
    return session;
  },

  async answer(
    sessionId: string,
    payload: { option_id?: string; value?: unknown; text?: string; skip?: boolean },
  ) {
    return api.actionEngineAnswer(sessionId, payload);
  },

  async complete(sessionId: string) {
    return api.actionEngineComplete(sessionId);
  },

  async cancel(sessionId: string) {
    return api.actionEngineCancel(sessionId);
  },

  async get(sessionId: string) {
    return api.actionEngineGetSession(sessionId);
  },
};

export default ActionEngine;
