/**
 * Production entry into AI Core — frontend is not cognition.
 * Starts/resumes via API then navigates to /ora/{sessionId}.
 *
 * Canonical Home handoff:
 * - Backend runs ONE cognitive turn on start/message (persists user message).
 * - Response may include ora_text and/or pending_turn / client_actions.
 * - Navigation carries ONLY opaque session id (never user text / coords).
 * - OraConversationScreen mount loads history + pending_turn and fulfills
 *   client capabilities / renders completed answers — never re-sends the text.
 */
import type { Router } from 'expo-router';
import { api } from '@/src/api/client';
import { buildOraConversationHref, type OraEntryPoint } from '@/src/ora/oraNav';

export type StartOraOptions = {
  text: string;
  entryPoint: OraEntryPoint;
  origin?: string;
  planId?: string | null;
  objectId?: string | null;
  planItemId?: string | null;
  /** Existing session to continue (Goal Workspace). */
  sessionId?: string | null;
};

/**
 * Send first message (or bind focus + open existing session) and navigate.
 * Message is persisted by the backend before navigation — never put text in the URL.
 */
export async function startOraConversation(
  router: Router,
  opts: StartOraOptions,
): Promise<{ sessionId: string }> {
  const text = (opts.text || '').trim();
  const existing = opts.sessionId ? String(opts.sessionId) : '';

  if (existing && !text) {
    if (opts.planId || opts.objectId) {
      try {
        await api.lifeOsSessionFocus({
          session_id: existing,
          object_id: opts.objectId || undefined,
          plan_id: opts.planId || undefined,
          plan_item_id: opts.planItemId || undefined,
          event_type: 'object_opened',
        });
      } catch {
        /* soft */
      }
    }
    router.push(
      buildOraConversationHref({
        sessionId: existing,
        planId: opts.planId,
        objectId: opts.objectId,
        planItemId: opts.planItemId,
        entryPoint: opts.entryPoint,
      }) as any,
    );
    return { sessionId: existing };
  }

  if (!text) {
    throw new Error('text_required');
  }

  if (existing) {
    if (opts.planId || opts.objectId) {
      try {
        await api.lifeOsSessionFocus({
          session_id: existing,
          object_id: opts.objectId || undefined,
          plan_id: opts.planId || undefined,
          plan_item_id: opts.planItemId || undefined,
          event_type: 'object_opened',
        });
      } catch {
        /* soft */
      }
    }
    await api.aiCoreMessage(existing, { text });
    router.push(
      buildOraConversationHref({
        sessionId: existing,
        planId: opts.planId,
        objectId: opts.objectId,
        planItemId: opts.planItemId,
        entryPoint: opts.entryPoint,
      }) as any,
    );
    return { sessionId: existing };
  }

  const res = await api.aiCoreStart({
    text,
    origin: opts.origin || opts.entryPoint || 'home',
    entry_point: opts.entryPoint,
    plan_id: opts.planId || undefined,
    object_id: opts.objectId || undefined,
  });
  const id = res.session_id;
  if (!id) throw new Error('Nessuna sessione');

  router.push(
    buildOraConversationHref({
      sessionId: id,
      planId: opts.planId,
      objectId: opts.objectId,
      planItemId: opts.planItemId,
      entryPoint: opts.entryPoint,
    }) as any,
  );
  return { sessionId: id };
}
