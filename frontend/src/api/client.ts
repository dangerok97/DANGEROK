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
    try {
      const j = await res.json();
      msg = j.detail || j.message || msg;
    } catch {}
    throw new Error(msg);
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
  priorities: () => request<{ items: ApiTask[] }>('/priorities'),
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
};
