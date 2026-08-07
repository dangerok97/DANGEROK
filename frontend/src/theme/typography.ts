/**
 * ORA Quiet Premium — typography scale (Apple HIG-inspired).
 * Geist remains the app font family when loaded; sizes/weights are semantic.
 */

export type TypeStyle = {
  fontSize: number;
  fontWeight: '400' | '500' | '600' | '700';
  lineHeight: number;
  letterSpacing: number;
};

export const typography = {
  display: { fontSize: 40, fontWeight: '700', lineHeight: 48, letterSpacing: -1.2 } satisfies TypeStyle,
  hero: { fontSize: 32, fontWeight: '700', lineHeight: 40, letterSpacing: -0.8 } satisfies TypeStyle,
  title: { fontSize: 28, fontWeight: '700', lineHeight: 34, letterSpacing: -0.5 } satisfies TypeStyle,
  headline: { fontSize: 22, fontWeight: '600', lineHeight: 28, letterSpacing: -0.3 } satisfies TypeStyle,
  body: { fontSize: 17, fontWeight: '400', lineHeight: 24, letterSpacing: -0.2 } satisfies TypeStyle,
  bodySmall: { fontSize: 15, fontWeight: '400', lineHeight: 22, letterSpacing: -0.1 } satisfies TypeStyle,
  caption: { fontSize: 13, fontWeight: '400', lineHeight: 18, letterSpacing: 0 } satisfies TypeStyle,
  footnote: { fontSize: 12, fontWeight: '400', lineHeight: 16, letterSpacing: 0.1 } satisfies TypeStyle,
  label: { fontSize: 13, fontWeight: '600', lineHeight: 18, letterSpacing: 0.1 } satisfies TypeStyle,
  button: { fontSize: 16, fontWeight: '600', lineHeight: 22, letterSpacing: -0.2 } satisfies TypeStyle,
} as const;

/** Legacy font-size aliases used across the app */
export const fsLegacy = {
  sm: typography.footnote.fontSize,
  base: typography.caption.fontSize,
  lg: typography.bodySmall.fontSize,
  xl: typography.body.fontSize,
  xxl: typography.headline.fontSize,
  xxxl: typography.title.fontSize,
  display: typography.display.fontSize,
} as const;
