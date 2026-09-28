import type { HomeActionDef } from '@/src/api/client';

/** Use the guide only when Home did not supply a real destination. */
export function isGuidedAction(action: HomeActionDef): boolean {
  if (action.route === '/action/open') return true;
  // A concrete destination is authoritative, even when the label is "Apri".
  if (action.route) return false;
  if (action.kind === 'guide' || action.kind === 'open') return true;
  const labels = (action.label || '').toLowerCase();
  return ['apri', 'organizza', 'inizia'].some((l) => labels === l || labels.startsWith(l + ' '));
}
