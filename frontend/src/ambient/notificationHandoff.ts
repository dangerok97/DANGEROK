/**
 * Validate a notification handoff without trusting a URL from Expo payloads.
 *
 * A push is merely a transport envelope. The backend owns the allowed
 * destinations; the client accepts only the same known relative routes.
 * Never open a scheme, external site, arbitrary nested route or write action.
 */
export type NotificationHandoff = {
  planId: string;
  route: string;
};

const OPAQUE_ID = '[A-Za-z0-9_-]{4,80}';
const PLAN_ID = /^dlv_[A-Za-z0-9_-]{6,80}$/;
const OPPORTUNITY = new RegExp(`^/aggiornamento/${OPAQUE_ID}$`);
const CONVERSATION = new RegExp(`^/ora\\?sessionId=${OPAQUE_ID}&entry=notification$`);
const AGENT_NEED = new RegExp(`^/ora\\?needId=${OPAQUE_ID}&goalId=${OPAQUE_ID}&entry=agent_need$`);

export function parseNotificationHandoff(payload: unknown): NotificationHandoff | null {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return null;
  const data = payload as Record<string, unknown>;
  const planId = data.plan_id;
  const route = data.deep_link;
  if (typeof planId !== 'string' || !PLAN_ID.test(planId)) return null;
  if (typeof route !== 'string' || route.length > 300) return null;
  if (
    route !== '/'
    && !OPPORTUNITY.test(route)
    && !CONVERSATION.test(route)
    && !AGENT_NEED.test(route)
  ) return null;
  return { planId, route };
}


/**
 * Server acknowledgement, not Expo payload, decides the actual destination.
 * Both sources must agree; an error/foreign owner may never open a route.
 */
export function canonicalNotificationRoute(
  handoff: NotificationHandoff,
  reply: unknown,
): string | null {
  if (!reply || typeof reply !== 'object' || Array.isArray(reply)) return null;
  const result = reply as Record<string, unknown>;
  if (result.ok !== true || result.outcome !== 'opened'
      || result.route !== handoff.route) return null;
  return typeof result.route === 'string' && result.route.length <= 300
    && parseNotificationHandoff({
      plan_id: handoff.planId,
      deep_link: result.route,
    }) !== null
    ? result.route : null;
}
