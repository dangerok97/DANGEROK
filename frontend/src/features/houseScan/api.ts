import { authToken, sessionRequest } from '@/src/api/client';
import type { HouseCapture, HouseScan, HouseScanPatch, HouseScanSummary, ManualRoomInput } from './types';

/** Freeze the session before opening the camera; never borrow a later login. */
async function request<T>(token: string, path: string, init: RequestInit = {}): Promise<T> {
  if (!token || (await authToken.get()) !== token) {
    throw new Error('La sessione è cambiata. Riapri Casa nel tuo account.');
  }
  const result = await sessionRequest<T>(`/house-scans${path}`, token, init);
  if ((await authToken.get()) !== token) {
    throw new Error('La sessione è cambiata. Riapri Casa nel tuo account.');
  }
  return result;
}

export const houseScanApi = {
  token: () => authToken.get(),
  list: (token: string, offset = 0) => request<{ scans: HouseScanSummary[]; has_more: boolean; next_offset: number | null }>(token, `?limit=50&offset=${offset}`),
  get: (token: string, id: string) => request<{ scan: HouseScan }>(token, `/${encodeURIComponent(id)}`),
  create: (token: string, capture: HouseCapture, title = 'Casa') =>
    request<{ scan: HouseScan; created: boolean }>(token, '', {
      method: 'POST', body: JSON.stringify({ title, capture }),
    }),
  patch: (token: string, id: string, patch: HouseScanPatch) =>
    request<{ scan: HouseScan }>(token, `/${encodeURIComponent(id)}`, {
      method: 'PATCH', body: JSON.stringify(patch),
    }),
  /** A room measured by hand: starts a plan, or joins a plan made the same way. */
  addManualRoom: (token: string, room: ManualRoomInput, plan?: { id: string; revision: number }, title = 'Casa') =>
    request<{ scan: HouseScan; created: boolean }>(token, '/manual-rooms', {
      method: 'POST',
      body: JSON.stringify(plan ? { room, scan_id: plan.id, revision: plan.revision } : { room, title }),
    }),
  removeRoom: (token: string, scan: HouseScanSummary, roomId: string) =>
    request<{ scan: HouseScan }>(token, `/${encodeURIComponent(scan.id)}/rooms/${encodeURIComponent(roomId)}?revision=${scan.revision}`, { method: 'DELETE' }),
  remove: (token: string, scan: HouseScanSummary) =>
    request<{ deleted: boolean }>(token, `/${encodeURIComponent(scan.id)}?revision=${scan.revision}`, { method: 'DELETE' }),
};
