/** Ambient bottom clearance (bar height before safe-area). */
export const AMBIENT_BAR_HEIGHT = 64;

/** Extra scroll padding so content clears floating Ambient bar. */
export const AMBIENT_BOTTOM_CLEARANCE = 108;

/** Compact Ambient Rail width on desktop breakpoint (72–88 band). */
export const AMBIENT_RAIL_WIDTH = 80;

/**
 * Action Focus decision column — narrower than shell/Home editorial width.
 * Continua CTA stays full-width inside this container.
 */
export const FOCUS_DECISION_MAX_WIDTH = 720;

/**
 * PX1.1 — the shell-wide decision column (`PageContainer`).
 *
 * Reading measure is a human constant, not a share of the viewport: past this
 * width a line of text stops being comfortable however large the display is.
 * Extra viewport width becomes margin on both sides, never a longer line.
 */
export const DECISION_COLUMN_MAX_WIDTH = 800;

/**
 * Reserved width for the optional contextual rail. Nothing renders it yet —
 * PX1.3+ owns its content. Declared here so the geometry is agreed once,
 * rather than guessed separately by each surface that eventually wants one.
 */
export const CONTEXT_RAIL_WIDTH = 320;

/** Ambient ↔ Focus transition (ms). Respect reduced motion → 0. */
export const SHELL_TRANSITION_MS = 240;
