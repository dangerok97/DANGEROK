/**
 * ORA's motion language, as numbers.
 *
 * The rule the whole product follows: motion exists to explain a change, never
 * to decorate one. Content that has arrived fades up; nothing slides, bounces,
 * springs, zooms or pulses. Three bands, and the numbers matter far less than
 * using the same one for the same kind of change everywhere:
 *
 *   micro    ~140ms  a control acknowledging a press
 *   standard ~200ms  content replacing a skeleton, a section opening
 *   surface  ~240ms  a dialog or a sheet arriving
 *
 * Import-free on purpose, so the contract can be asserted without a renderer.
 */
export const QUIET_MOTION = {
  micro: 140,
  standard: 200,
  surface: 240,
} as const;

/** Ease-out: quick to commit, slow to settle. Nothing overshoots. */
export const QUIET_EASING = { x1: 0.16, y1: 1, x2: 0.3, y2: 1 } as const;
