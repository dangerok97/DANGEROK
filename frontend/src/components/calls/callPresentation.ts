/**
 * How a call reads, and how it looks.
 *
 * The words come from the backend — it is the only side that knows what was
 * actually confirmed, and letting the client invent a summary would mean
 * letting it say "done" about something nobody did. What lives here is the
 * other half: how strongly each state should be drawn, and how to say a
 * duration or a date to a person.
 *
 * Quiet Premium means the page does not shout. A failed call is not red and
 * a successful one is not green-and-proud; the one state that gets any real
 * weight is the one that needs something from the person reading.
 */
import type { CallCard } from '@/src/api/client';
import type { SemanticColors } from '@/src/theme/palettes';

export type CallTone = 'neutral' | 'quiet' | 'attention' | 'positive';

/**
 * How loudly a state is allowed to speak.
 *
 * Only `serve_una_decisione` gets `attention`, and it earns it: it is the one
 * state where nothing moves until the person does something. Everything else
 * is information, and information that competes for attention stops being
 * information.
 */
const TONE: Record<CallCard['presentation_status'], CallTone> = {
  in_corso: 'neutral',
  completata: 'positive',
  serve_una_decisione: 'attention',
  nessuna_risposta: 'quiet',
  occupato: 'quiet',
  segreteria: 'quiet',
  non_riuscita: 'neutral',
  interrotta: 'neutral',
};

export function toneOf(status: CallCard['presentation_status']): CallTone {
  return TONE[status] ?? 'neutral';
}

/** The pill's colours, drawn from the theme rather than invented here. */
export function toneColors(tone: CallTone, colors: SemanticColors) {
  switch (tone) {
    case 'positive':
      return { bg: colors.successBg, fg: colors.success };
    case 'attention':
      return { bg: colors.warningBg, fg: colors.warning };
    case 'quiet':
      return { bg: colors.backgroundSecondary, fg: colors.textTertiary };
    default:
      return { bg: colors.backgroundSecondary, fg: colors.textSecondary };
  }
}

/**
 * A duration, said the way a person says it.
 *
 * "00:46" is a stopwatch; "46 secondi" is an answer. Under a minute we do not
 * pretend to minutes, and over a minute the seconds stop mattering enough to
 * print them alone.
 */
export function howLong(seconds?: number | null): string {
  if (seconds === null || seconds === undefined) return '';
  if (seconds < 60) return `${seconds} s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return s === 0 ? `${m} min` : `${m} min ${s} s`;
}

/**
 * When it happened, relative to today.
 *
 * Someone opening this screen is almost always looking for the call from an
 * hour ago, so today and yesterday get names instead of dates.
 */
export function whenItHappened(iso?: string | null): string {
  if (!iso) return '';
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return '';

  const ora = when.toLocaleTimeString('it-IT', {
    hour: '2-digit',
    minute: '2-digit',
  });
  const oggi = new Date();
  const stessoGiorno = (a: Date, b: Date) =>
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate();

  if (stessoGiorno(when, oggi)) return `Oggi · ${ora}`;

  const ieri = new Date(oggi);
  ieri.setDate(oggi.getDate() - 1);
  if (stessoGiorno(when, ieri)) return `Ieri · ${ora}`;

  const giorno = when.toLocaleDateString('it-IT', {
    day: 'numeric',
    month: 'long',
  });
  return `${giorno} · ${ora}`;
}

/**
 * The line under the name: when, and how long.
 *
 * A call nobody answered has no duration, and printing "0 s" next to it would
 * suggest a conversation that lasted no time rather than one that never
 * started.
 */
export function whenAndHowLong(call: CallCard): string {
  const quando = whenItHappened(call.started_at || call.created_at);
  const durata = howLong(call.duration_seconds);
  return durata ? `${quando} · ${durata}` : quando;
}

/** Who was called, when there is no name to show. */
export function whoWasCalled(call: CallCard): string {
  return call.counterparty_name?.trim() || call.counterparty_number || 'Numero sconosciuto';
}
