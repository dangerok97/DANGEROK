/** Minimal session shape for Focus chrome labels (avoids pulling API client into shell). */
export type ActionProgressSource = {
  flow?: string | null;
  progress?: number | null;
  done?: boolean;
  answers?: Record<string, unknown> | null;
  meta?: Record<string, unknown> | null;
};

/** Map Action Engine flow → human context label (or omit). */
export function flowContextLabel(flow?: string | null): string | null {
  const f = (flow || '').toLowerCase();
  if (f === 'study' || f === 'studio') return 'Studio';
  if (f === 'travel' || f === 'viaggio') return 'Viaggio';
  if (f === 'home' || f === 'casa' || f === 'household') return 'Casa';
  if (f === 'work' || f === 'lavoro') return 'Lavoro';
  return null;
}

/**
 * Prefer "N di M" when steps are knowable from answers + progress.
 * Never return a fake "0%" — hide when unknown.
 */
export function actionProgressLabel(session: ActionProgressSource | null | undefined): string | null {
  if (!session) return null;
  const meta = (session.meta || {}) as Record<string, unknown>;
  const metaN = Number(meta.step_index ?? meta.turn_index ?? meta.current_step);
  const metaM = Number(meta.step_count ?? meta.turn_count ?? meta.total_steps);
  if (Number.isFinite(metaN) && Number.isFinite(metaM) && metaM > 0) {
    return `${Math.max(1, metaN)} di ${metaM}`;
  }

  const answered = Object.keys(session.answers || {}).length;
  const progress = typeof session.progress === 'number' ? session.progress : 0;
  if (progress > 0 && answered >= 0) {
    const total = Math.max(
      answered + (session.done ? 0 : 1),
      Math.round(answered / progress) || Math.round(1 / progress),
    );
    const current = session.done ? total : Math.min(total, answered + 1);
    if (total >= 1 && current >= 1) return `${current} di ${total}`;
  }
  return null;
}
