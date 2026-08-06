/**
 * ORA API client — reads Bearer token from secure storage.
 */
import { Platform } from 'react-native';
import { storage } from '@/src/utils/storage';

const BASE = process.env.EXPO_PUBLIC_BACKEND_URL;
const TOKEN_KEY = 'ora_auth_token';

export const authToken = {
  async get(): Promise<string | null> {
    return await storage.secureGet<string>(TOKEN_KEY, '' as string).then((v) => (v ? String(v) : null));
  },
  async set(token: string) {
    await storage.secureSet(TOKEN_KEY, token);
  },
  async clear() {
    await storage.secureRemove(TOKEN_KEY);
  },
};

async function request<T>(path: string, init: RequestInit = {}, auth = true): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init.headers as Record<string, string> | undefined),
  };
  if (auth) {
    const t = await authToken.get();
    if (t) headers.Authorization = `Bearer ${t}`;
  }
  const res = await fetch(`${BASE}/api${path}`, { ...init, headers });
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    let detail: any = null;
    try {
      const j = await res.json();
      detail = j.detail || j;
      msg = typeof detail === 'string' ? detail : (detail?.error || detail?.message || msg);
    } catch {}
    const err: any = new Error(msg);
    err.status = res.status;
    err.detail = detail;
    throw err;
  }
  return (await res.json()) as T;
}

// ---- Types
export type ApiUser = {
  user_id: string;
  email: string;
  name?: string | null;
  picture?: string | null;
  provider: string;
};

export type ApiAuth = { token: string; user: ApiUser };

export type AuthProvidersStatus = {
  google: { configured: boolean; platforms: Record<string, boolean>; legacy_emergent?: boolean };
  apple: {
    configured: boolean;
    platforms: Record<string, boolean>;
    web_secret_ready?: boolean;
  };
  password: { configured: boolean };
};

export type LLMProviderId = 'gemini' | 'openai' | 'ollama' | 'emergent';

export type LLMProviderInfo = {
  id: LLMProviderId;
  label: string;
  configured: boolean;
  available: boolean;
  model?: string | null;
  priority: number;
};

export type LLMProvidersStatus = {
  active: string | null;
  preferred?: string | null;
  user_preference?: string;
  configured: boolean;
  fallback_chain: string[];
  priority: string[];
  providers: LLMProviderInfo[];
  note?: string;
};

export type AuthIdentitiesResponse = {
  user_id: string;
  email?: string;
  methods: {
    password: { linked: boolean; email?: string | null };
    google: { linked: boolean; email?: string | null };
    apple: { linked: boolean; email?: string | null };
  };
  identities: Array<Record<string, unknown>>;
  can_unlink: { google: boolean; apple: boolean };
};

export type ApiTask = {
  id: string;
  user_id: string;
  title: string;
  context?: string | null;
  urgency: number;
  importance: number;
  risk: number;
  time_required_min: number;
  energy: number;
  economic_impact: number;
  personal_impact: number;
  kind?: string | null;
  metadata?: Record<string, any> | null;
  score: number;
  reason?: string | null;
  reason_tags?: string[] | null;
  status: string;
  created_at: string;
  last_resolution?: string;
};

// ---- Auth
export const api = {
  register: (email: string, password: string, name?: string) =>
    request<ApiAuth>('/auth/register', { method: 'POST', body: JSON.stringify({ email, password, name }) }, false),

  login: (email: string, password: string) =>
    request<ApiAuth>('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) }, false),

  googleSession: (session_token: string) =>
    request<ApiAuth>('/auth/google-session', { method: 'POST', body: JSON.stringify({ session_token }) }, false),

  authProviders: () =>
    request<AuthProvidersStatus>('/auth/providers', {}, false),

  authGoogle: (id_token: string, nonce?: string) =>
    request<ApiAuth>(
      '/auth/google',
      { method: 'POST', body: JSON.stringify({ id_token, nonce }) },
      false,
    ),

  authApple: (payload: {
    id_token: string;
    nonce?: string;
    email?: string | null;
    full_name?: { givenName?: string | null; familyName?: string | null } | null;
  }) =>
    request<ApiAuth>(
      '/auth/apple',
      {
        method: 'POST',
        body: JSON.stringify({
          id_token: payload.id_token,
          nonce: payload.nonce,
          email: payload.email,
          full_name: payload.full_name,
        }),
      },
      false,
    ),

  linkGoogle: (id_token: string, nonce?: string) =>
    request<{ ok: boolean }>('/auth/link/google', {
      method: 'POST',
      body: JSON.stringify({ id_token, nonce }),
    }),

  linkApple: (payload: { id_token: string; nonce?: string }) =>
    request<{ ok: boolean }>('/auth/link/apple', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  unlinkProvider: (provider: 'google' | 'apple') =>
    request<{ ok: boolean }>(`/auth/link/${provider}`, { method: 'DELETE' }),

  authIdentities: () => request<AuthIdentitiesResponse>('/auth/identities'),

  llmProviders: () => request<LLMProvidersStatus>('/llm/providers'),

  setLlmProvider: (provider: LLMProviderId | 'auto') =>
    request<{
      ok: boolean;
      user_preference: string;
      active: string | null;
      providers: LLMProviderInfo[];
      fallback_chain: string[];
    }>('/llm/preferences', {
      method: 'PATCH',
      body: JSON.stringify({ provider }),
    }),

  me: () => request<ApiUser>('/auth/me'),

  logout: () => request<{ ok: boolean }>('/auth/logout', { method: 'POST' }),

  // Priorities / Tasks
  priorities: (limit: number = 3) =>
    request<{ items: ApiTask[] }>(`/priorities?limit=${limit}`),
  listTasks: () => request<{ items: ApiTask[] }>('/tasks'),
  createTask: (t: Partial<ApiTask> & { title: string }) =>
    request<ApiTask>('/tasks', { method: 'POST', body: JSON.stringify(t) }),
  dismissTask: (id: string) => request<{ ok: boolean }>(`/tasks/${id}/dismiss`, { method: 'POST' }),
  completeTask: (id: string) => request<{ ok: boolean }>(`/tasks/${id}/complete`, { method: 'POST' }),
  resolveTask: (id: string) => request<{ solution: string; task_id: string }>(`/tasks/${id}/resolve`, { method: 'POST' }),

  // Memory
  addMemory: (content: string, tags?: string[]) =>
    request<{ id: string; content: string; tags: string[]; created_at: string }>('/memory', {
      method: 'POST',
      body: JSON.stringify({ content, tags }),
    }),
  listMemory: () =>
    request<{ items: { id: string; content: string; tags: string[]; created_at: string }[] }>('/memory'),
  askMemory: (question: string) =>
    request<{ answer: string; sources: any[] }>('/memory/ask', { method: 'POST', body: JSON.stringify({ question }) }),

  // Decisions
  topDecisions: (limit: number = 5) =>
    request<{ items: ApiDecision[] }>(`/decisions/top?limit=${limit}`),
  listDecisions: () => request<{ items: ApiDecision[] }>('/decisions'),
  getDecision: (id: string) => request<ApiDecision>(`/decisions/${id}`),

  // Explanation
  getExplanation: (id: string) =>
    request<DecisionExplanation>(`/decisions/${id}/explanation`),

  // Action Center
  startDecision: (id: string) =>
    request<{ ok: boolean; decision: ApiDecision }>(`/decisions/${id}/start`, { method: 'POST' }),
  completeDecision: (id: string, note?: string) =>
    request<{ ok: boolean; decision: ApiDecision }>(`/decisions/${id}/complete`, {
      method: 'POST',
      body: JSON.stringify({ note: note ?? null }),
    }),
  partialDecision: (id: string, completion_percentage: number, remaining_minutes?: number, optional_note?: string) =>
    request<{ ok: boolean; decision: ApiDecision }>(`/decisions/${id}/partial`, {
      method: 'POST',
      body: JSON.stringify({ completion_percentage, remaining_minutes, optional_note }),
    }),
  postponeDecision: (id: string, until_datetime: string, reason?: string) =>
    request<{ ok: boolean; decision: ApiDecision }>(`/decisions/${id}/postpone`, {
      method: 'POST',
      body: JSON.stringify({ until_datetime, reason }),
    }),
  blockDecision: (id: string, reason: string) =>
    request<{ ok: boolean; decision: ApiDecision }>(`/decisions/${id}/blocked`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),
  dismissDecision: (id: string, reason?: string) =>
    request<{ ok: boolean; decision?: ApiDecision }>(`/decisions/${id}/dismiss`, {
      method: 'POST',
      body: JSON.stringify({ reason: reason ?? null }),
    }),
  historyDecision: (id: string) =>
    request<{ items: DecisionActionHistoryItem[] }>(`/decisions/${id}/history`),

  // Daily
  dailyToday: () => request<DailySummary>('/daily/today'),
  dailyTomorrow: () => request<DailySummary>('/daily/tomorrow'),
  dailyRefresh: () => request<{ today: DailySummary; tomorrow: DailySummary }>('/daily/refresh', { method: 'POST' }),

  // Google Calendar connector (for empty states)
  googleCalendarInstances: () =>
    request<{ items: ConnectorInstance[] }>('/connectors/google-calendar/instances'),
  googleCalendarConfig: () =>
    request<GoogleCalendarConfigStatus>('/connectors/google-calendar/config-status'),
  googleCalendarOAuthStart: (opts?: { redirect_after?: string }) => {
    // Prefer the live browser origin so localhost and 127.0.0.1 both round-trip.
    let redirect_after = opts?.redirect_after;
    if (!redirect_after && typeof window !== 'undefined' && window.location?.origin) {
      redirect_after = `${window.location.origin}/settings`;
    }
    const body: Record<string, string> = {};
    if (redirect_after) body.redirect_after = redirect_after;
    return request<{ authorize_url: string; state: string; expires_at: string; provider_mode: string }>(
      '/connectors/google-calendar/oauth/start',
      { method: 'POST', body: JSON.stringify(body) },
    );
  },
  googleCalendarCalendars: (instanceId: string) =>
    request<{ items: GoogleCalendarResource[] }>(`/connectors/google-calendar/instances/${instanceId}/calendars`),
  googleCalendarSelectCalendars: (instanceId: string, calendar_ids: string[]) =>
    request<ConnectorInstance>(
      `/connectors/google-calendar/instances/${instanceId}/select-calendars`,
      { method: 'POST', body: JSON.stringify({ calendar_ids }) },
    ),
  googleCalendarSync: (instanceId: string) =>
    request<GoogleCalendarSyncResult>(`/connectors/google-calendar/instances/${instanceId}/sync`, { method: 'POST' }),
  googleCalendarInstanceStatus: (instanceId: string) =>
    request<any>(`/connectors/google-calendar/instances/${instanceId}/status`),
  googleCalendarRevoke: (instanceId: string) =>
    request<{ ok: boolean; instance: ConnectorInstance }>(
      `/connectors/google-calendar/instances/${instanceId}/revoke`,
      { method: 'POST' },
    ),

  // Apple Calendar connector (EventKit — iOS/iPadOS only)
  appleCalendarConfig: () =>
    request<AppleCalendarConfigStatus>('/connectors/apple-calendar/config-status'),
  appleCalendarInstances: () =>
    request<{ items: ConnectorInstance[] }>('/connectors/apple-calendar/instances'),
  appleCalendarConnect: (body: AppleCalendarConnectPayload) =>
    request<{ ok: boolean; instance: ConnectorInstance }>(
      '/connectors/apple-calendar/connect',
      { method: 'POST', body: JSON.stringify(body) },
    ),
  appleCalendarSelectCalendars: (instanceId: string, calendar_ids: string[]) =>
    request<ConnectorInstance>(
      `/connectors/apple-calendar/instances/${instanceId}/select-calendars`,
      { method: 'POST', body: JSON.stringify({ calendar_ids }) },
    ),
  appleCalendarSync: (instanceId: string, events: AppleRawEvent[]) =>
    request<AppleCalendarSyncResult>(
      `/connectors/apple-calendar/instances/${instanceId}/sync`,
      { method: 'POST', body: JSON.stringify({ events }) },
    ),
  appleCalendarStatus: (instanceId: string) =>
    request<any>(`/connectors/apple-calendar/instances/${instanceId}/status`),
  appleCalendarDisconnect: (instanceId: string) =>
    request<{ ok: boolean; instance: ConnectorInstance; detached_mirrored_nodes: number }>(
      `/connectors/apple-calendar/instances/${instanceId}/disconnect`,
      { method: 'POST' },
    ),

  // Home V2 — intelligence dashboard
  getHome: () => request<HomeV2Response>('/home'),
  refreshHome: () => request<HomeV2Response>('/home/refresh', { method: 'POST' }),
  getHomeSituation: () => request<HomeSituationResponse>('/home/situation'),
  homeAction: (body: HomeActionRequest) =>
    request<{ ok: boolean; action: string; item_id?: string }>('/home/actions', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  // Proactive Engine — suggestions
  listSuggestions: (params?: { status?: string; type?: string; limit?: number }) => {
    const q = new URLSearchParams();
    if (params?.status) q.set('status', params.status);
    if (params?.type) q.set('type', params.type);
    if (params?.limit) q.set('limit', String(params.limit));
    const qs = q.toString();
    return request<{ suggestions: ProactiveSuggestion[]; enabled: boolean; count: number }>(
      `/suggestions${qs ? `?${qs}` : ''}`,
    );
  },
  regenerateSuggestions: () =>
    request<{ ok: boolean; created: number; rejected: number }>('/suggestions/regenerate', {
      method: 'POST',
    }),
  acceptSuggestion: (id: string) =>
    request<{ ok: boolean; id: string; status: string; result?: Record<string, unknown> }>(
      `/suggestions/${id}/accept`,
      { method: 'POST' },
    ),
  dismissSuggestion: (id: string) =>
    request<{ ok: boolean; id: string; status: string }>(`/suggestions/${id}/dismiss`, {
      method: 'POST',
    }),
  completeSuggestion: (id: string) =>
    request<{ ok: boolean; id: string; status: string }>(`/suggestions/${id}/complete`, {
      method: 'POST',
    }),
  snoozeSuggestion: (id: string, body: { preset?: string; until?: string }) =>
    request<{ ok: boolean; id: string; status: string; snooze_until?: string }>(
      `/suggestions/${id}/snooze`,
      { method: 'POST', body: JSON.stringify(body) },
    ),
  explainSuggestion: (id: string) =>
    request<{ ok: boolean; reason: string; explain?: Record<string, unknown> }>(
      `/suggestions/${id}/explain`,
    ),

  // Conversation Engine — entry orchestrator (NOT a chatbot)
  conversationStart: (body: ConversationStartBody) =>
    request<ConversationStartResult>('/conversation/start', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  conversationGet: (sessionId: string) =>
    request<{
      ok: boolean;
      session: ConversationSession;
      action_session?: ActionEngineSession | null;
      route?: string | null;
    }>(`/conversation/sessions/${sessionId}`),
  conversationMessage: (
    sessionId: string,
    body: { text?: string; option_id?: string; value?: unknown; skip?: boolean },
  ) =>
    request<ConversationStartResult>(`/conversation/${sessionId}/message`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  conversationContinue: (sessionId: string, note?: string) =>
    request<ConversationStartResult>(`/conversation/${sessionId}/continue`, {
      method: 'POST',
      body: JSON.stringify({ note }),
    }),
  conversationCancel: (sessionId: string, reason?: string) =>
    request<{ ok: boolean; session: ConversationSession }>(
      `/conversation/${sessionId}/cancel`,
      { method: 'POST', body: JSON.stringify({ reason }) },
    ),
  conversationResume: (body: { session_id?: string; resume_token?: string }) =>
    request<ConversationStartResult>('/conversation/resume', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  conversationHistory: (sessionId: string) =>
    request<{ ok: boolean; steps: Array<Record<string, unknown>>; not_chat: boolean }>(
      `/conversation/${sessionId}/history`,
    ),
  conversationSummary: (sessionId: string) =>
    request<{
      ok: boolean;
      summary?: string;
      resume_token?: string;
      goal_id?: string;
      project_id?: string;
      action_session_id?: string;
    }>(`/conversation/${sessionId}/summary`),
  conversationList: (limit = 10) =>
    request<{ ok: boolean; sessions: ConversationSession[]; enabled: boolean }>(
      `/conversation?limit=${limit}`,
    ),

  // Action Engine — guided priority flows
  actionEngineOpen: (body: ActionEngineOpenBody) =>
    request<ActionEngineOpenResult>('/action-engine/open', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  actionEngineGetSession: (sessionId: string) =>
    request<{ session: ActionEngineSession }>(`/action-engine/sessions/${sessionId}`),
  actionEngineAnswer: (
    sessionId: string,
    body: { option_id?: string; value?: unknown; text?: string; skip?: boolean },
  ) =>
    request<ActionEngineAnswerResult>(`/action-engine/sessions/${sessionId}/answer`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  actionEngineComplete: (sessionId: string) =>
    request<ActionEngineAnswerResult>(`/action-engine/sessions/${sessionId}/complete`, {
      method: 'POST',
    }),
  actionEngineCancel: (sessionId: string) =>
    request<{ ok: boolean; session: ActionEngineSession }>(
      `/action-engine/sessions/${sessionId}/cancel`,
      { method: 'POST' },
    ),
  actionEngineMergeProject: (sessionId: string, target_project_id: string) =>
    request<{ ok: boolean; project_id?: string; session: ActionEngineSession }>(
      `/action-engine/sessions/${sessionId}/merge-project`,
      { method: 'POST', body: JSON.stringify({ target_project_id }) },
    ),
  actionEngineBack: (sessionId: string, to_turn_id?: string) =>
    request<ActionEngineAnswerResult>(`/action-engine/sessions/${sessionId}/back`, {
      method: 'POST',
      body: JSON.stringify({ to_turn_id }),
    }),
  actionEngineDraft: (sessionId: string, answers?: Record<string, unknown>) =>
    request<ActionEngineAnswerResult>(`/action-engine/sessions/${sessionId}/draft`, {
      method: 'POST',
      body: JSON.stringify({ answers }),
    }),
  actionEngineSearchDocs: (sessionId: string) =>
    request<{ ok: boolean; session: ActionEngineSession; documents?: unknown }>(
      `/action-engine/sessions/${sessionId}/search-docs`,
      { method: 'POST' },
    ),
  actionEnginePreview: (sessionId: string) =>
    request<{ ok: boolean; preview?: unknown; plan?: unknown; session?: ActionEngineSession }>(
      `/action-engine/sessions/${sessionId}/preview`,
      { method: 'POST' },
    ),
  actionEngineConfirm: (sessionId: string, body: { duplicate_action?: string; force?: boolean } = {}) =>
    request<ActionEngineAnswerResult>(`/action-engine/sessions/${sessionId}/confirm`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  // Study plans
  studyPlansList: (status?: string) =>
    request<{ items: StudyPlan[] }>(`/study-plans${status ? `?status=${status}` : ''}`),
  studyPlanGet: (planId: string) =>
    request<{ plan: StudyPlan }>(`/study-plans/${planId}`),
  studyPlanSessionAction: (
    planId: string,
    sessionId: string,
    action: 'start' | 'complete' | 'snooze' | 'skip',
    snooze_minutes?: number,
  ) =>
    request<{ ok: boolean; session?: unknown }>(
      `/study-plans/${planId}/sessions/${sessionId}/action`,
      { method: 'POST', body: JSON.stringify({ action, snooze_minutes }) },
    ),
  studyPlanUpdate: (planId: string, body: Record<string, unknown>) =>
    request<{ ok: boolean; plan?: StudyPlan }>(`/study-plans/${planId}/update`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  studyPlanDelete: (planId: string) =>
    request<{ ok: boolean }>(`/study-plans/${planId}`, { method: 'DELETE' }),
  studyPlanSync: (planId: string) =>
    request<{ ok: boolean; google_sync?: unknown }>(`/study-plans/${planId}/retry-sync`, {
      method: 'POST',
    }),

  // Travel projects
  travelProjectsList: (status?: string) =>
    request<{ items: TravelProject[] }>(`/travel-projects${status ? `?status=${status}` : ''}`),
  travelProjectGet: (projectId: string) =>
    request<{ project: TravelProject }>(`/travel-projects/${projectId}`),
  travelProjectDelete: (projectId: string, cleanupGoogle = false) =>
    request<{ ok: boolean }>(
      `/travel-projects/${projectId}?cleanup_google=${cleanupGoogle ? 'true' : 'false'}`,
      { method: 'DELETE' },
    ),
  travelProjectSync: (projectId: string) =>
    request<{ ok: boolean; google_sync?: unknown }>(`/travel-projects/${projectId}/retry-sync`, {
      method: 'POST',
    }),

  // Documents V2 — intelligent actions engine
  documentsHub: (limit = 40) =>
    request<DocumentsHubResponse>(`/documents/hub?limit=${limit}`),
  documentsSearchIntelligent: (params: {
    q?: string;
    macro_category?: string;
    pipeline_status?: string;
    has_open_actions?: boolean;
    limit?: number;
  } = {}) => {
    const qs = new URLSearchParams();
    if (params.q) qs.append('q', params.q);
    if (params.macro_category) qs.append('macro_category', params.macro_category);
    if (params.pipeline_status) qs.append('pipeline_status', params.pipeline_status);
    if (typeof params.has_open_actions === 'boolean') {
      qs.append('has_open_actions', String(params.has_open_actions));
    }
    if (params.limit) qs.append('limit', String(params.limit));
    const q = qs.toString();
    return request<DocumentsListResponse>(`/documents/search/intelligent${q ? `?${q}` : ''}`);
  },
  documentPreferences: () => request<DocumentPreferences>(`/documents/preferences`),
  setDocumentPreferences: (body: Partial<DocumentPreferences>) =>
    request<DocumentPreferences>(`/documents/preferences`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  documentsList: (params: { q?: string; tag?: string; mime?: string; archived?: boolean; sort?: string; limit?: number; offset?: number } = {}) => {
    const qs = new URLSearchParams();
    if (params.q) qs.append('q', params.q);
    if (params.tag) qs.append('tag', params.tag);
    if (params.mime) qs.append('mime', params.mime);
    if (typeof params.archived === 'boolean') qs.append('archived', String(params.archived));
    if (params.sort) qs.append('sort', params.sort);
    if (params.limit) qs.append('limit', String(params.limit));
    if (params.offset) qs.append('offset', String(params.offset));
    const q = qs.toString();
    return request<DocumentsListResponse>(`/documents${q ? `?${q}` : ''}`);
  },
  documentGet: (id: string) => request<DocumentItem>(`/documents/${id}`),
  documentInsights: (id: string) => request<DocumentInsights>(`/documents/${id}/insights`),
  documentAnalysis: (id: string) => request<DocumentAnalysisResponse>(`/documents/${id}/analysis`),
  documentAnalyze: (id: string) =>
    request<{ ok: boolean; pipeline_status?: string }>(`/documents/${id}/analyze`, { method: 'POST' }),
  documentReanalyze: (id: string) =>
    request<{ ok: boolean }>(`/documents/${id}/reanalyze`, { method: 'POST' }),
  documentPatchAnalysis: (id: string, body: {
    user_title?: string;
    analysis?: Record<string, unknown>;
    admin_analysis?: Record<string, unknown>;
    education_analysis?: Record<string, unknown>;
  }) =>
    request<DocumentAnalysisResponse>(`/documents/${id}/analysis`, { method: 'PATCH', body: JSON.stringify(body) }),
  documentClearAnalysis: (id: string) =>
    request<{ ok: boolean }>(`/documents/${id}/analysis`, { method: 'DELETE' }),
  documentConfirmEvent: (
    docId: string,
    eventId: string,
    opts?: { overrides?: Record<string, unknown>; sync_to_google?: boolean },
  ) =>
    request<{
      ok: boolean;
      calendar_event?: Record<string, unknown>;
      google_sync?: Record<string, unknown> | null;
      deduplicated?: boolean;
    }>(
      `/documents/${docId}/events/${eventId}/confirm`,
      {
        method: 'POST',
        body: JSON.stringify({
          overrides: opts?.overrides,
          sync_to_google: !!opts?.sync_to_google,
        }),
      },
    ),
  googleCalendarWriteStatus: () =>
    request<{
      connected: boolean;
      needs_reconnect?: boolean;
      account_email?: string | null;
      default_calendar_id?: string | null;
      write_capable?: boolean;
      last_sync_at?: string | null;
    }>('/documents/calendar/google/status'),
  setGoogleCalendarDefault: (calendar_id: string) =>
    request<Record<string, unknown>>('/documents/calendar/google/default', {
      method: 'PATCH',
      body: JSON.stringify({ calendar_id }),
    }),
  syncCalendarDraft: (draftId: string) =>
    request<Record<string, unknown>>(`/documents/calendar/events/${draftId}/sync`, { method: 'POST' }),
  retryCalendarDraft: (draftId: string) =>
    request<Record<string, unknown>>(`/documents/calendar/events/${draftId}/retry`, { method: 'POST' }),
  resolveCalendarConflict: (draftId: string, resolution: 'keep_google' | 'overwrite_ora' | 'unlink') =>
    request<Record<string, unknown>>(`/documents/calendar/events/${draftId}/resolve-conflict`, {
      method: 'POST',
      body: JSON.stringify({ resolution }),
    }),
  deleteCalendarDraft: (draftId: string, also_delete_google = false) =>
    request<{ ok: boolean }>(
      `/documents/calendar/events/${draftId}?also_delete_google=${also_delete_google ? 'true' : 'false'}`,
      { method: 'DELETE' },
    ),
  googleCalendarWriteCalendars: () =>
    request<{
      items: Array<{ id: string; summary?: string; primary?: boolean }>;
      default_calendar_id?: string | null;
      account_email?: string | null;
      write_capable?: boolean;
      needs_reconnect?: boolean;
    }>('/documents/calendar/google/calendars'),
  documentDismissEvent: (docId: string, eventId: string) =>
    request<{ ok: boolean }>(`/documents/${docId}/events/${eventId}/dismiss`, { method: 'POST' }),
  documentRemindEvent: (docId: string, eventId: string) =>
    request<{ ok: boolean }>(`/documents/${docId}/events/${eventId}/remind-later`, { method: 'POST' }),
  documentPatchEvent: (docId: string, eventId: string, patch: Record<string, unknown>) =>
    request<DocumentAnalysisResponse>(`/documents/${docId}/events/${eventId}`, {
      method: 'PATCH',
      body: JSON.stringify(patch),
    }),
  documentAsk: (id: string, question: string) =>
    request<{ answer: string; grounding: string; ai_used: boolean }>(`/documents/${id}/ask`, {
      method: 'POST',
      body: JSON.stringify({ question }),
    }),
  documentStudy: (id: string, action: string) =>
    request<{
      ok: boolean;
      action: string;
      result?: unknown;
      flashcards?: Flashcard[];
      quiz_session?: QuizSession;
      education_analysis?: EducationAnalysis;
    }>(`/documents/${id}/study`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    }),
  documentQuizAnswer: (id: string, answer: string) =>
    request<{ ok: boolean; quiz_session: QuizSession }>(`/documents/${id}/quiz/answer`, {
      method: 'POST',
      body: JSON.stringify({ answer }),
    }),
  documentAdminComplete: (id: string, index: number, completed = true) =>
    request<DocumentAnalysisResponse>(`/documents/${id}/admin/actions/complete`, {
      method: 'POST',
      body: JSON.stringify({ index, completed }),
    }),
  documentAdminDeadline: (id: string, sync_to_google = false) =>
    request<{ ok: boolean; calendar_event?: Record<string, unknown> }>(
      `/documents/${id}/admin/deadline-calendar`,
      { method: 'POST', body: JSON.stringify({ sync_to_google }) },
    ),
  documentPatch: (id: string, body: { filename?: string; tags?: string[]; notes?: string }) =>
    request<DocumentItem>(`/documents/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  documentArchive: (id: string) => request<DocumentItem>(`/documents/${id}/archive`, { method: 'POST' }),
  documentRestore: (id: string) => request<DocumentItem>(`/documents/${id}/restore`, { method: 'POST' }),
  documentDelete: (id: string, hard = false) =>
    request<{ ok: boolean; hard: boolean; id: string }>(`/documents/${id}${hard ? '?hard=true' : ''}`, { method: 'DELETE' }),
  documentUpload: async (file: { uri: string; name: string; type: string }, tags?: string[], notes?: string) => {
    const form = new FormData();
    if (Platform.OS === 'web') {
      // Web/Safari/Chrome: FormData does not accept the RN shape
      // {uri,name,type}. We must upload a real Blob/File. Fetch the
      // picker's blob-URI (or data-URI) and append as Blob.
      let blob: Blob;
      try {
        const r = await fetch(file.uri);
        blob = await r.blob();
      } catch (e: any) {
        throw new Error('Impossibile leggere il file dal browser: ' + (e?.message || 'errore'));
      }
      form.append('file', blob, file.name);
    } else {
      // React Native (iOS / Android app): the native FormData polyfill
      // understands this exact shape.
      // @ts-ignore RN FormData accepts { uri, name, type }
      form.append('file', file as any);
    }
    if (tags?.length) form.append('tags', tags.join(','));
    if (notes) form.append('notes', notes);
    const token = await authToken.get();
    const res = await fetch(`${BASE}/api/documents/upload`, {
      method: 'POST',
      headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: form as any,
    });
    if (!res.ok) {
      const text = await res.text();
      let msg = text;
      let detail: any = null;
      try { const j = JSON.parse(text); detail = j.detail || j; msg = detail?.message || detail?.error || msg; } catch {}
      const err: any = new Error(msg || `HTTP ${res.status}`);
      err.status = res.status;
      err.detail = detail;
      throw err;
    }
    return res.json() as Promise<{ duplicate: boolean; document: DocumentItem }>;
  },
};

// --- Documents (Iterazione 19) ---
export type DocumentItem = {
  id: string;
  user_id: string;
  filename: string;
  original_filename: string;
  mime_type: string;
  size: number;
  hash: string;
  tags: string[];
  notes: string;
  archived: boolean;
  deleted: boolean;
  life_node_id?: string | null;
  knowledge_synced?: boolean;
  upload_source?: string;
  version?: number;
  created_at: string;
  updated_at: string;
  pipeline_status?: string;
  pipeline_status_label?: string;
  display_title?: string;
  user_title?: string;
  analysis?: DocumentAnalysisPayload | null;
  event_candidates?: EventCandidate[];
  education_analysis?: EducationAnalysis | null;
};

export type DocumentAnalysisPayload = {
  suggested_title?: string;
  short_description?: string;
  macro_category?: string;
  subcategory?: string;
  confidence?: number;
  summary?: string;
  summary_detailed?: string;
  keywords?: string[];
  requires_review?: boolean;
  reasoning_summary?: string;
  ai_used?: boolean;
  local_only?: boolean;
  warnings?: string[];
};

export type EventCandidate = {
  id: string;
  title: string;
  description?: string;
  start_datetime?: string | null;
  end_datetime?: string | null;
  venue_name?: string | null;
  address?: string | null;
  city?: string | null;
  priority?: string;
  urgency?: string;
  confidence?: number;
  status?: string;
  ambiguous_date?: boolean;
  missing_fields?: string[];
  maps_url?: string | null;
  directions_url?: string | null;
  maps_query?: string | null;
  booking_reference?: string | null;
};

export type EducationAnalysis = {
  subject?: string | null;
  topic?: string | null;
  level?: string | null;
  suggested_title?: string;
  simple_explanation?: string;
  summary_short?: string;
  summary_detailed?: string;
  outline?: string[];
  key_concepts?: string[];
  definitions?: string[];
  important_people?: string[];
  important_dates?: string[];
  formulas?: string[];
  examples?: string[];
  questions_for_review?: string[];
  exam_questions?: string[];
  keywords?: string[];
  estimated_read_minutes?: number;
  difficulty?: string;
  confidence?: number;
};

export type AdminAnalysis = {
  sender?: string | null;
  recipient?: string | null;
  subject?: string | null;
  document_number?: string | null;
  amount?: string | null;
  currency?: string | null;
  issue_date?: string | null;
  due_date?: string | null;
  payment_method?: string | null;
  required_actions?: string[];
  simple_explanation?: string;
  completed?: boolean;
  priority?: string;
  urgency?: string;
  confidence?: number;
};

export type Flashcard = {
  id: string;
  question: string;
  answer: string;
  source_ref?: string | null;
  difficulty?: string;
  review_status?: string;
};

export type QuizSession = {
  id: string;
  document_id: string;
  turns: Array<{
    question: string;
    expected_points?: string[];
    user_answer?: string | null;
    feedback?: string | null;
    covered?: boolean;
  }>;
  current_index: number;
  status: string;
};

export type GenericAction = {
  action_type: string;
  title: string;
  description?: string;
  due_datetime?: string | null;
  amount?: string | null;
  completed?: boolean;
  priority?: string;
  urgency?: string;
};

export type DocumentAnalysisResponse = {
  document_id: string;
  pipeline_status?: string;
  pipeline_status_label?: string;
  pipeline_error?: string | null;
  display_title?: string;
  user_title?: string | null;
  analysis?: DocumentAnalysisPayload | null;
  event_candidates?: EventCandidate[];
  education_analysis?: EducationAnalysis | null;
  admin_analysis?: AdminAnalysis | null;
  generic_actions?: GenericAction[];
  flashcards?: Flashcard[];
  quiz_session?: QuizSession | null;
  field_provenance?: Record<string, unknown>;
  ai_consent_required_note?: string | null;
};

export type DocumentHubCard = {
  id: string;
  display_title?: string;
  original_filename?: string;
  macro_category?: string;
  subcategory?: string;
  short_description?: string;
  pipeline_status?: string;
  pipeline_status_label?: string;
  confidence?: number;
  utility?: string;
  event_start?: string | null;
  event_location?: string | null;
  open_actions?: number;
  updated_at?: string;
  mime_type?: string;
};

export type DocumentPreferences = {
  document_ai_analysis: boolean;
  calendar_auto_add_enabled: boolean;
  calendar_auto_add_threshold: number;
};

export type DocumentsHubResponse = {
  recent: DocumentHubCard[];
  needs_review: DocumentHubCard[];
  events_found: DocumentHubCard[];
  study: DocumentHubCard[];
  administrative: DocumentHubCard[];
  medical: DocumentHubCard[];
  failed: DocumentHubCard[];
  with_actions: DocumentHubCard[];
  counts: Record<string, number>;
  prefs?: DocumentPreferences;
};

export type DocumentsListResponse = {
  items: DocumentItem[];
  total: number;
  limit: number;
  offset: number;
};

// Iterazione 22 — Document Understanding Engine (deterministico, no LLM).
// Il tipo estende Iter21 in modo retrocompatibile aggiungendo:
//   - classification, schema_used, resolved_fields, hidden_fields,
//     technical_identifiers
export type ResolvedField = {
  field_key: string;
  label: string;
  value: string;
  confidence: number;
  source_snippet?: string;
  source_page?: number | null;
  resolver_rule?: string;
};

export type DocumentInsights = {
  id: string;
  filename: string;
  type_key: string;
  type_label: string;
  // Iter22 additions
  classification?: {
    type_key: string;
    type_label: string;
    confidence: number;
    matched_rules: string[];
    scores: Record<string, number>;
    threshold_visible: number;
    threshold_hidden: number;
  };
  schema_used?: {
    type_key: string;
    type_label: string;
    version: number;
    info_order: string[];
  } | null;
  resolved_fields?: ResolvedField[];
  hidden_fields?: ResolvedField[];
  technical_identifiers?: {
    grouped: Record<string, string[]>;
    flat: string[];
  };
  // Retrocompat (Iter21)
  summary: { fields: { label: string; value: string }[] };
  entities: Record<string, string[]>;
  extraction: {
    engine?: string;
    method: 'PDF' | 'OCR' | 'TEXT';
    text_extracted: boolean;
    ocr_used: boolean;
    pages?: number | null;
    language?: string | null;
    confidence?: number | null;
    duration_ms?: number | null;
    extracted_at?: string | null;
    error_code?: string | null;
  };
  technical_metadata: {
    hash?: string;
    size?: number;
    mime_type?: string;
    storage_provider?: string;
    original_filename?: string;
  };
  history: {
    created_at?: string;
    updated_at?: string;
    archived: boolean;
    deleted: boolean;
    version: number;
    upload_source?: string;
  };
  content: { text: string; length: number };
};

// Extra types
export type ApiDecision = {
  id: string;
  title: string;
  description?: string | null;
  category?: string | null;
  urgency: number; importance: number; risk: number;
  time_required_min: number;
  starts_at?: string | null;
  deadline?: string | null;
  status: string;
  score?: number | null;
  reason?: string | null;
  reason_tags?: string[] | null;
  node_ids?: string[];
  action_state?: {
    status?: string;
    completion_percentage?: number | null;
    remaining_minutes?: number | null;
    last_action?: string | null;
    last_action_at?: string | null;
    postponed_until?: string | null;
    blocked_reason?: string | null;
  } | null;
  metadata?: Record<string, any> | null;
  last_resolution?: string | null;
  created_at: string;
};

export type AppliedRule = { id: string; label: string; evidence: string[]; weight: 'low'|'medium'|'high' };
export type DataSourceItem = { source: string; confidence: string; last_updated_at?: string | null; notes?: string | null };
export type DecisionExplanation = {
  decision_id: string;
  priority_score?: number | null;
  confidence: 'high'|'medium'|'low';
  estimated_duration_minutes: number;
  estimated_impact: 'low'|'medium'|'high';
  estimated_postpone_risk: 'low'|'medium'|'high';
  generated_at: string;
  human_summary: string;
  reasoning_steps: string[];
  data_sources: DataSourceItem[];
  applied_rules: AppliedRule[];
  context_used: string[];
  version: string;
};

export type DecisionActionHistoryItem = {
  id: string; timestamp: string;
  old_status: string | null;
  new_status: string;
  user_action: string;
  completion_percentage?: number | null;
  remaining_minutes?: number | null;
  postponed_until?: string | null;
  reason?: string | null;
  note?: string | null;
};

export type DailySummary = {
  date: string; timezone: string; generated_at: string;
  score: number; confidence: 'high'|'medium'|'low';
  total_events: number; all_day_events: number;
  is_weekend: boolean; is_holiday: boolean; is_vacation_day: boolean;
  busy_minutes: number; free_minutes: number;
  consecutive_events: number; total_break_minutes: number;
  first_event_at?: string | null; last_event_at?: string | null;
  by_category: Record<string, number>;
  busy_slots: { start: string; end: string; duration_min: number; category?: string | null }[];
  free_slots: { start: string; end: string; duration_min: number }[];
  signals: string[]; warnings: string[]; opportunities: string[];
  energy_estimation: { level: 'high'|'medium'|'low'; score: number; reasons: string[] };
  version: string; source_counts?: Record<string, number>;
};

export type ConnectorInstance = {
  id: string; connector_id: string; status: string;
  display_label?: string; last_sync_at?: string | null;
  selected_resource_ids?: string[];
  consent_active?: boolean;
  provider_mode?: 'real' | 'fake';
  authorized_scopes?: string[];
  vault_status?: string;
  created_at?: string;
  updated_at?: string;
};

export type GoogleCalendarResource = {
  id: string;
  summary: string;
  description?: string | null;
  primary?: boolean | null;
  access_role?: string | null;
  color?: string | null;
  time_zone?: string | null;
  selected?: boolean | null;
};

export type GoogleCalendarSyncResult = {
  instance_id: string;
  started_at: string;
  finished_at?: string;
  total_events_received: number;
  total_events_processed: number;
  total_events_skipped: number;
  total_events_quarantined?: number;
  total_events_failed?: number;
  per_calendar: Array<{
    calendar_id: string;
    received: number;
    processed: number;
    skipped: number;
    quarantined?: number;
    failed?: number;
  }>;
  by_stage?: Record<string, { processed?: number; skipped?: number; failed?: number }>;
};

export type GoogleCalendarConfigStatus = {
  provider_mode: 'real'|'fake';
  client_id_configured: boolean;
  client_secret_configured: boolean;
  redirect_uri_configured: boolean;
  token_vault_ready: boolean;
  provider_ready: boolean;
  missing_requirements: string[];
  environment: string;
};

// --- Apple Calendar (EventKit) types ---
export type AppleCalendarConfigStatus = {
  enabled: boolean;
  connector_id: string;
  capability_id: string;
  requires_native_build: boolean;
  platforms: string[];
  environment: string;
  notes?: string;
};

export type AppleCalendarInfo = {
  id: string;
  title?: string | null;
  color?: string | null;
  allowsModifications?: boolean;
  source?: string | null;
};

export type AppleCalendarConnectPayload = {
  device_id: string;
  device_name?: string | null;
  platform?: 'ios' | 'ipados' | null;
  calendars?: AppleCalendarInfo[];
};

export type AppleRawEvent = {
  id: string;
  calendarId?: string;
  calendarTitle?: string;
  title?: string | null;
  notes?: string | null;
  startDate?: string;
  endDate?: string;
  allDay?: boolean;
  location?: string | null;
  timeZone?: string | null;
  status?: string;
  organizer?: string | null;
  attendees?: string[];
  recurrenceRule?: string | null;
  lastModified?: string | null;
  availability?: string | null;
};

export type AppleCalendarSyncOutcome = {
  external_id: string;
  status: 'processed' | 'skipped' | 'mirrored' | 'quarantined' | 'failed';
  event_id?: string;
  node_id?: string;
  primary_provider?: string;
  error_code?: string;
};

export type AppleCalendarSyncResult = {
  instance_id: string;
  totals: {
    received: number;
    processed: number;
    skipped: number;
    mirrored: number;
    quarantined: number;
    failed: number;
  };
  outcomes: AppleCalendarSyncOutcome[];
};

// --- Home V2 ---
export type HomePriorityBand = 'critical' | 'today' | 'this_week' | 'waiting' | 'later';
export type HomeItemType =
  | 'event' | 'travel' | 'bill' | 'study' | 'verify' | 'visit'
  | 'reply' | 'activity' | 'payment' | 'needs_review' | 'insight' | 'resume' | 'generic';

export type HomeActionDef = {
  id: string;
  label: string;
  kind: string;
  route?: string | null;
  params?: Record<string, unknown>;
  primary?: boolean;
};

export type HomeReasonFactor = {
  code: string;
  label: string;
  weight: number;
  detail?: string | null;
};

export type HomeSupportingDetail = {
  kind: string;
  label: string;
  source_type?: string;
  source_id?: string;
  when?: string;
  next_session?: string;
  phase?: string;
  exam_in_days?: number;
  days_until?: number;
  skipped?: number;
  missing_prep?: string[] | string;
  resume_kind?: string;
};

export type HomeItem = {
  id: string;
  type: HomeItemType;
  subtype?: string | null;
  title: string;
  description?: string | null;
  source_type: string;
  source_id: string;
  priority: HomePriorityBand;
  urgency: string;
  confidence?: number | null;
  due_at?: string | null;
  start_at?: string | null;
  end_at?: string | null;
  duration_minutes?: number | null;
  location?: string | null;
  amount?: string | null;
  status: string;
  actions: HomeActionDef[];
  reason_factors: HomeReasonFactor[];
  reason_summary?: string | null;
  ranking_version?: string;
  created_at?: string | null;
  updated_at?: string | null;
  meta?: Record<string, unknown>;
  /** Goal context (invisible layer — no Goal screens). Present when linked. */
  goal_id?: string | null;
  goal_title?: string | null;
  goal_type?: string | null;
  goal_status?: string | null;
  goal_progress?: number | null;
  goal_progress_label?: string | null;
  goal_next_action?: string | null;
  goal_target_date?: string | null;
  goal_blockers?: string[] | null;
  goal_project_id?: string | null;
  /** Presentation Aggregation Layer — one card per Goal */
  presentation_id?: string | null;
  card_type?: string | null;
  subtitle?: string | null;
  next_action?: string | null;
  supporting_details?: HomeSupportingDetail[] | null;
  source_refs?: { type: string; id: string; item_id?: string; title?: string }[] | null;
  hidden_artifact_count?: number | null;
  presentation_badges?: string[] | null;
  presentation_version?: string | null;
  generated_at?: string | null;
};

export type HomeExplanation = {
  summary: string;
  factors: HomeReasonFactor[];
  sources: { type: string; id: string; title?: string }[];
  confidence?: number | null;
  missing_data: string[];
  ranking_version: string;
  item_id?: string | null;
};

export type HomeSituationIndicator = {
  id: string;
  label: string;
  value: string;
  tone: 'default' | 'warning' | 'success' | 'info';
  detail?: string | null;
};

export type HomeCurrentSituation = {
  indicators: HomeSituationIndicator[];
  free_window?: string | null;
  next_commitment?: string | null;
  open_actions_count: number;
  needs_review_count: number;
  cta_label: string;
  cta_route: string;
};

export type HomePriorityGroup = {
  key: HomePriorityBand;
  label: string;
  items: HomeItem[];
};

export type HomeInsight = {
  id: string;
  text: string;
  source: string;
  action?: HomeActionDef | null;
  status: string;
  created_at: string;
  valid_until?: string | null;
  dedupe_key: string;
};

export type HomeConnectionWarning = {
  code: string;
  message: string;
  severity: 'info' | 'warning';
  dismissible: boolean;
};

export type ProactiveSuggestionAction = {
  kind: string;
  label: string;
  route?: string | null;
  params?: Record<string, unknown>;
};

export type ProactiveSuggestion = {
  id: string;
  title: string;
  description?: string | null;
  reason?: string;
  type?: string;
  priority?: string;
  importance?: number;
  urgency?: number;
  confidence?: number;
  source?: string;
  goal_id?: string | null;
  project_id?: string | null;
  document_id?: string | null;
  study_plan_id?: string | null;
  travel_project_id?: string | null;
  action?: ProactiveSuggestionAction | null;
  status?: string;
  expires_at?: string | null;
  snooze_until?: string | null;
  created_at?: string;
};

export type HomeV2Response = {
  primary_focus: HomeItem | null;
  explanation: HomeExplanation | null;
  current_situation: HomeCurrentSituation;
  priorities: HomePriorityGroup[];
  insights: HomeInsight[];
  resume_item: HomeItem | null;
  ora_ti_consiglia?: ProactiveSuggestion[];
  connection_warnings: HomeConnectionWarning[];
  google_calendar: {
    connected: boolean;
    show_banner: boolean;
    last_sync_at?: string | null;
    instance_id?: string | null;
  };
  generated_at: string;
  ranking_version: string;
  partial: boolean;
};

export type HomeSituationResponse = {
  generated_at: string;
  ranking_version: string;
  current_situation: HomeCurrentSituation;
  priorities: HomePriorityGroup[];
  primary_focus: HomeItem | null;
  connection_warnings: HomeConnectionWarning[];
  google_calendar: HomeV2Response['google_calendar'];
};

export type HomeActionRequest = {
  item_id: string;
  action: string;
  until?: string;
  reason?: string;
  priority?: HomePriorityBand;
  note?: string;
};

// --- Action Engine ---
export type ActionEngineSession = {
  id: string;
  status: 'active' | 'completed' | 'cancelled';
  flow: string;
  engine_version: string;
  title: string;
  description?: string | null;
  source_type?: string | null;
  source_id?: string | null;
  home_item_id?: string | null;
  home_item_type?: string | null;
  current_turn: {
    id: string;
    question: string;
    explanation?: string | null;
    input_kind: string;
    options: { id: string; label: string; value?: unknown }[];
    allow_skip?: boolean;
    required?: boolean;
    meta?: Record<string, unknown>;
  } | null;
  answers: Record<string, unknown>;
  progress: number;
  done: boolean;
  proposed_actions: {
    id: string;
    kind: string;
    label: string;
    detail?: string | null;
    status: string;
    meta?: Record<string, unknown>;
  }[];
  project?: {
    project_id: string;
    title: string;
    created: boolean;
    merge_candidate_id?: string | null;
    merge_candidate_title?: string | null;
  } | null;
  brain_node_id?: string | null;
  effects?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  completed_at?: string | null;
  meta?: Record<string, unknown>;
};

export type StudyPlan = {
  id: string;
  status: string;
  exam_name: string;
  subject?: string | null;
  exam_date?: string | null;
  intensity?: string;
  daily_minutes?: number;
  available_days?: number[];
  tools?: string[];
  document_ids?: string[];
  calendar_sync?: boolean;
  sessions?: Array<Record<string, unknown>>;
  flashcard_document_ids?: string[];
  interrogami_document_ids?: string[];
  google_sync?: Record<string, unknown>;
  preview?: Record<string, unknown>;
  progress?: Record<string, unknown>;
  confirmed_at?: string | null;
};

export type TravelProject = {
  id: string;
  status: string;
  title: string;
  destination?: string | null;
  departure_place?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  transport?: string | null;
  bookings?: string | null;
  companions?: number | null;
  calendar_sync?: boolean;
  calendar_events?: Array<Record<string, unknown>>;
  maps?: Record<string, unknown>;
  prep_items?: Array<Record<string, unknown>>;
  document_ids?: string[];
  google_sync?: Record<string, unknown>;
  preview?: Record<string, unknown>;
  phase?: string;
  days_until?: number | null;
  weather?: Record<string, unknown>;
  departure_advice?: Record<string, unknown>;
  email_search?: Record<string, unknown>;
  confirmed_at?: string | null;
};

export type ActionEngineOpenBody = {
  home_item?: Partial<HomeItem> | Record<string, unknown>;
  home_item_id?: string;
  source_type?: string;
  source_id?: string;
  item_type?: string;
  title?: string;
  description?: string;
  location?: string;
  due_at?: string;
  start_at?: string;
  meta?: Record<string, unknown>;
  force_new?: boolean;
  /** Precomputed Intent from Intent Classification Engine */
  intent?: Record<string, unknown>;
};

export type ActionEngineOpenResult = {
  session: ActionEngineSession;
  resumed?: boolean;
  merge_proposal?: { project_id: string; title?: string } | null;
};

export type ActionEngineAnswerResult = {
  ok: boolean;
  session: ActionEngineSession;
  completed?: boolean;
  home_invalidate?: boolean;
  next_focus_hint?: string | null;
  error?: string;
  message?: string;
  upload_required?: boolean;
  upload_route?: string;
  plan?: StudyPlan | Record<string, unknown>;
  opened_plan_id?: string;
};

/** Conversation Engine — orchestration session (not a chat thread). */
export type ConversationSession = {
  id: string;
  status: string;
  origin: string;
  input?: string | null;
  intent?: Record<string, unknown> | null;
  goal_id?: string | null;
  project_id?: string | null;
  action_session_id?: string | null;
  current_step?: string | null;
  artifacts?: Array<{ kind: string; id: string; label?: string | null }>;
  summary?: string | null;
  resume_token?: string;
  engine_version?: string;
  known_slots?: Record<string, unknown>;
  extracted_entities?: Record<string, unknown>;
  confirmed_entities?: Record<string, unknown>;
  missing_slots?: string[];
  ambiguous_slots?: string[];
  extraction_version?: string | null;
  last_extraction_at?: string | null;
  /** Human labels only: Partenza / Destinazione / Ritorno … */
  understood_summary?: Record<string, string>;
  meta?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
};

export type ConversationStartBody = {
  text?: string;
  origin?: string;
  voice_meta?: Record<string, unknown>;
  suggestion_id?: string;
  context?: Record<string, unknown>;
  force_new?: boolean;
};

export type ConversationStartResult = {
  ok: boolean;
  enabled?: boolean;
  session?: ConversationSession;
  action_session?: ActionEngineSession | null;
  route?: string | null;
  first_question?: string | null;
  synthetic_prompt?: string | null;
  ui_mode?: string;
  resumed?: boolean;
  stub?: boolean;
  honesty?: string;
  error?: string;
  handoff?: string;
  completed?: boolean;
};
