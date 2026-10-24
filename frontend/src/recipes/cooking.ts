/** Pure kitchen helpers — testable in Node, no React. */

const FRACTIONS: Record<string, number> = { '½': 0.5, '¼': 0.25, '¾': 0.75, '⅓': 1 / 3, '⅔': 2 / 3 };

function format(value: number): string {
  const rounded = value >= 10 ? Math.round(value) : Math.round(value * 4) / 4;
  if (Number.isInteger(rounded)) return String(rounded);
  return rounded.toLocaleString('it-IT', { maximumFractionDigits: 2 });
}

/**
 * Scale the leading quantity of an ingredient line. Only the first number is
 * touched ("200 g farina 00" keeps the "00"); lines without a leading number
 * ("sale q.b.") are left as written — a guess is worse than no number.
 */
export function scaleLine(line: string, factor: number): string {
  if (!Number.isFinite(factor) || factor <= 0 || Math.abs(factor - 1) < 1e-9) return line;
  const match = line.match(/^(\s*)(\d+(?:[.,]\d+)?(?:\s*\/\s*\d+)?|[½¼¾⅓⅔])(\s*[½¼¾⅓⅔])?/);
  if (!match) return line;
  const raw = match[2];
  let value: number;
  if (raw in FRACTIONS) value = FRACTIONS[raw];
  else if (raw.includes('/')) {
    const [a, b] = raw.split('/').map(x => Number(x.trim().replace(',', '.')));
    if (!b) return line;
    value = a / b;
  } else value = Number(raw.replace(',', '.'));
  if (match[3]) value += FRACTIONS[match[3].trim()] ?? 0;
  if (!Number.isFinite(value) || value <= 0) return line;
  return match[1] + format(value * factor) + line.slice(match[0].length);
}

/** Minutes a step asks to wait, when it says so ("cuoci 20 minuti", "1 ora"). */
export function stepTimerMinutes(step: string): number | null {
  const text = step.toLocaleLowerCase('it');
  const range = text.match(/(\d+)\s*(?:-|–|o|a)\s*(\d+)\s*(minuti|min\b|ore|ora)/);
  if (range) {
    const top = Number(range[2]);
    return range[3].startsWith('or') ? top * 60 : top;
  }
  const hours = text.match(/(\d+(?:[.,]\d+)?)\s*(?:ore|ora)\b/);
  const mins = text.match(/(\d+)\s*(?:minuti|minuto|min\b)/);
  let total = 0;
  if (hours) total += Math.round(Number(hours[1].replace(',', '.')) * 60);
  if (mins) total += Number(mins[1]);
  if (!total && /mezz'?ora/.test(text)) total = 30;
  return total > 0 && total <= 24 * 60 ? total : null;
}

export function minutesLabel(total: number | null | undefined): string {
  if (!total) return '';
  if (total < 60) return `${total} min`;
  const h = Math.floor(total / 60); const m = total % 60;
  return m ? `${h} h ${m} min` : `${h} h`;
}

export type RecipeFilter = 'all' | 'favorite' | 'to_try' | 'quick';

export function matchesFilter(
  recipe: { favorite: boolean; status: string; total_minutes?: number | null; tags: string[] },
  filter: RecipeFilter | `tag:${string}`,
): boolean {
  if (filter === 'all') return true;
  if (filter === 'favorite') return recipe.favorite;
  if (filter === 'to_try') return recipe.status !== 'cooked';
  if (filter === 'quick') return !!recipe.total_minutes && recipe.total_minutes <= 30;
  return recipe.tags.map(t => t.toLocaleLowerCase('it')).includes(filter.slice(4));
}
