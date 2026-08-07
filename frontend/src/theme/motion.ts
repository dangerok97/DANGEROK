/**
 * ORA Quiet Premium — motion tokens.
 * Calm, intentional; no dashboard flash.
 */

export const motion = {
  duration: {
    fast: 120,
    normal: 220,
    slow: 360,
    hero: 480,
  },
  curve: {
    /** Ease out — most UI */
    standard: 'cubic-bezier(0.25, 0.1, 0.25, 1)',
    /** Soft spring feel (JS-driven) */
    spring: { damping: 18, stiffness: 220, mass: 0.9 },
    /** Gentle entrance */
    easeOut: 'cubic-bezier(0.16, 1, 0.3, 1)',
    /** Press / dismiss */
    easeIn: 'cubic-bezier(0.4, 0, 1, 1)',
  },
  pressScale: 0.97,
  fade: { from: 0, to: 1 },
  slide: { distance: 16 },
  stagger: 40,
  /** Legacy keys used by existing screens */
  press: { scale: 0.97, duration: 120 },
  fadeIn: { duration: 220 },
  sheet: { duration: 320 },
} as const;
