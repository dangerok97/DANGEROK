/**
 * Durations, in the words a person would use.
 *
 * The bug this replaces: two copies of the same function, both computing
 * hours and minutes independently and rounding the minutes on their own. Three
 * hours and fifty-nine and a half minutes came out as "3h 60m" — a duration
 * that does not exist, printed to somebody about their own evening.
 *
 * Rounding happens once, to the whole number of minutes, and the hours are
 * derived from that. There is no path left on which the minutes can reach
 * sixty.
 */

/**
 * `null` under a minute: "sei qui da 12 secondi" is noise, not information.
 *
 *   59m → "59m"      60m → "1h"       61m → "1h 1m"
 *   3h59m → "3h 59m" 3h60m → "4h"     4h0m → "4h"
 */
export function formatDuration(seconds?: number | null): string | null {
  if (seconds === null || seconds === undefined) return null;
  const totalMinutes = Math.round(seconds / 60);
  if (totalMinutes < 1) return null;

  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (hours && minutes) return `${hours}h ${minutes}m`;
  if (hours) return `${hours}h`;
  return `${minutes}m`;
}
