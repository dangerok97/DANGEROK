/**
 * Conversation Engine entry — NOT a chatbot.
 * Starts orchestration then bridges to Action Engine one-question UI.
 */
import { Router } from 'expo-router';
import {
  api,
  ConversationStartBody,
  ConversationStartResult,
  ConversationSession,
} from '@/src/api/client';

export type ConversationOrigin =
  | 'home'
  | 'voice'
  | 'text'
  | 'documents'
  | 'notifications'
  | 'proactive'
  | 'email'
  | 'whatsapp'
  | 'open_banking';

function routeFromResult(result: ConversationStartResult): string | null {
  if (result.route) return result.route;
  const actionId =
    result.action_session?.id || result.session?.action_session_id || null;
  if (actionId) return `/action/${actionId}`;
  return null;
}

export const ConversationEngine = {
  async start(
    text: string,
    router: Router,
    opts?: {
      origin?: ConversationOrigin;
      voice_meta?: Record<string, unknown>;
      suggestion_id?: string;
      context?: Record<string, unknown>;
    },
  ): Promise<ConversationStartResult> {
    const body: ConversationStartBody = {
      text: text.trim(),
      origin: opts?.origin || 'home',
      voice_meta: opts?.voice_meta,
      suggestion_id: opts?.suggestion_id,
      context: opts?.context,
    };
    const result = await api.conversationStart(body);
    if (result.stub) {
      throw new Error(result.honesty || 'Origine non ancora disponibile');
    }
    if (!result.ok && result.error) {
      throw new Error(result.error);
    }
    const route = routeFromResult(result);
    if (!route) {
      throw new Error('Conversation Engine non ha aperto una guida');
    }
    // Bridge to AE one-question UI — never a chat thread
    router.push(route as any);
    return result;
  },

  async resume(
    router: Router,
    opts: { session_id?: string; resume_token?: string },
  ): Promise<ConversationStartResult> {
    const result = await api.conversationResume(opts);
    if (!result.ok) {
      throw new Error(result.error || 'Impossibile riprendere');
    }
    const route = routeFromResult(result);
    if (route) router.push(route as any);
    return result;
  },

  async get(sessionId: string): Promise<{ session: ConversationSession; route?: string | null }> {
    const res = await api.conversationGet(sessionId);
    return { session: res.session, route: res.route };
  },

  /** Voice-ready stub — same path as text; STT not implemented. */
  async startFromVoiceStub(
    text: string,
    router: Router,
  ): Promise<ConversationStartResult> {
    return this.start(text, router, {
      origin: 'voice',
      voice_meta: { stt: 'stub', honesty: 'Mic uses same Conversation Engine; STT not wired.' },
    });
  },
};

export default ConversationEngine;
