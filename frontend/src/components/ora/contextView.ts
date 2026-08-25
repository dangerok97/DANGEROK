/**
 * Pure shaping for the ORA conversation surface.
 *
 * Deliberately free of imports: this is the part that decides what a person
 * reads, and it should be checkable without a network, a theme or a bundler.
 */

export type OraContextView = {
  /** The goal, as the person named it. */
  goal: string;
  /** The step this conversation is about, when one was passed. */
  step?: string | null;
  /** The material ORA prepared, when the conversation opened on one. */
  material?: string | null;
};

/**
 * What ORA already has in hand, read off the plan bundle that already exists.
 *
 * Returns null rather than a placeholder: a header that says nothing real is
 * worse than no header, because it teaches the user to ignore the space where
 * the real thing appears.
 */
export function contextFromPlanBundle(
  bundle: any,
  { objectId, planItemId }: { objectId?: string | null; planItemId?: string | null },
): OraContextView | null {
  const goal = String(bundle?.plan?.summary || '').trim();
  if (!goal) return null;

  const objects: any[] = Array.isArray(bundle?.objects) ? bundle.objects : [];
  const material = objectId
    ? String(objects.find((o) => o?.id === objectId)?.title || '').trim() || null
    : null;

  const items: any[] = Array.isArray(bundle?.plan?.items) ? bundle.plan.items : [];
  const named = planItemId ? items.find((i) => i?.id === planItemId) : null;
  // Fall back to whatever the plan itself considers next — the same step the
  // Workspace shows under ADESSO, so the two surfaces agree.
  const step = String(named?.title || bundle?.next_item?.title || '').trim() || null;

  return { goal, step, material };
}

/**
 * The conversation's own words for a failure, or null when it has no opinion.
 *
 * The app-wide translator serves setup screens and dev surfaces, where "check
 * EXPO_PUBLIC_BACKEND_URL" is genuinely the right advice. In a conversation it
 * is not: the user cannot start a backend, and being told to is worse than
 * being told nothing. Connectivity and server failures get one plain sentence
 * here; anything else falls through to the shared translation.
 */
export function oraErrorSentence(err: any): string | null {
  const code = String(err?.code || '').toLowerCase();
  const raw = String(err?.message || '').toLowerCase();
  const offline =
    code === 'network_unreachable' ||
    code === 'backend_url_missing' ||
    Boolean(err?.network) ||
    /failed to fetch|network request failed|load failed|networkerror|offline/.test(raw);
  if (offline) return 'Non riesco a raggiungere ORA in questo momento. Riprova fra poco.';
  if (Number(err?.status || 0) >= 500) return 'ORA ha avuto un problema nel rispondere. Riprova fra poco.';
  return null;
}
