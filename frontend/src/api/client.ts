/**
 * ORA API client — reads Bearer token from secure storage.
 */
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
  googleCalendarOAuthStart: () =>
    request<{ authorize_url: string; state: string; expires_at: string; provider_mode: string }>(
      '/connectors/google-calendar/oauth/start',
      { method: 'POST', body: JSON.stringify({}) },
    ),
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

  // Documents (Iterazione 19)
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
  documentPatch: (id: string, body: { filename?: string; tags?: string[]; notes?: string }) =>
    request<DocumentItem>(`/documents/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  documentArchive: (id: string) => request<DocumentItem>(`/documents/${id}/archive`, { method: 'POST' }),
  documentRestore: (id: string) => request<DocumentItem>(`/documents/${id}/restore`, { method: 'POST' }),
  documentDelete: (id: string, hard = false) =>
    request<{ ok: boolean; hard: boolean; id: string }>(`/documents/${id}${hard ? '?hard=true' : ''}`, { method: 'DELETE' }),
  documentUpload: async (file: { uri: string; name: string; type: string }, tags?: string[], notes?: string) => {
    // Multipart upload — reuse the fetch layer since request() uses JSON only.
    const form = new FormData();
    // @ts-ignore RN FormData accepts { uri, name, type }
    form.append('file', file as any);
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
      try { msg = JSON.parse(text)?.detail?.message || msg; } catch {}
      throw new Error(msg || `HTTP ${res.status}`);
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
};

export type DocumentsListResponse = {
  items: DocumentItem[];
  total: number;
  limit: number;
  offset: number;
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
