/**
 * ORA Quiet Premium — design tokens (static export for StyleSheet compat).
 *
 * New semantic names live alongside legacy aliases so existing screens keep working.
 * Dynamic light/dark resolution goes through ThemeProvider + useTheme().
 *
 * PX1.1 — static `tokens.color` resolves to the LIGHT Quiet Premium palette.
 * This is load-bearing, not cosmetic: roughly forty screens and components read
 * `tokens.color.*` inside `StyleSheet.create`, which runs once at module load and
 * therefore cannot see the provider. While this default was dark, every one of
 * those surfaces rendered dark no matter what the user or the provider chose —
 * which is exactly why Profilo/Impostazioni/Documenti flipped to dark while the
 * navigation rail beside them stayed light. Consumer V1 is light everywhere, so
 * the static default and the provider must agree. Dark stays fully expressible
 * via `colorDark`/`darkColors` for a future themed pass.
 */

import { darkColors, lightColors, type SemanticColors } from './palettes';
import { spacing as spacingScale } from './spacing';
import { radius as radiusScale } from './radius';
import { typography, fsLegacy } from './typography';
import { motion as motionTokens } from './motion';
import { iconSize, iconStroke } from './icons';
import { getShadows } from './shadows';

export type { SemanticColors };
export { darkColors, lightColors, ACCENT_DEEP_INDIGO } from './palettes';
export { typography } from './typography';
export { spacing as spacingScale } from './spacing';
export { radius as radiusScale } from './radius';
export { motion as motionTokens } from './motion';
export { haptics, triggerHaptic } from './haptics';
export { iconSize, iconStroke } from './icons';
export { getShadows, shadowStyle } from './shadows';

/** Map semantic palette → color object with legacy aliases */
export function colorsFromPalette(c: SemanticColors) {
  return {
    // —— New Quiet Premium semantic ——
    backgroundPrimary: c.backgroundPrimary,
    backgroundSecondary: c.backgroundSecondary,
    surface: c.surface,
    surfaceElevated: c.surfaceElevated,
    surfaceGlass: c.surfaceGlass,
    divider: c.divider,
    border: c.border,
    borderStrong: c.borderStrong,
    textPrimary: c.textPrimary,
    textSecondary: c.textSecondary,
    textTertiary: c.textTertiary,
    placeholder: c.placeholder,
    success: c.success,
    warning: c.warning,
    error: c.error,
    info: c.info,
    successBg: c.successBg,
    warningBg: c.warningBg,
    errorBg: c.errorBg,
    infoBg: c.infoBg,
    accent: c.accent,
    onAccent: c.onAccent,
    accentMuted: c.accentMuted,
    focusGlow: c.focusGlow,
    scrim: c.scrim,
    skeleton: c.skeleton,
    skeletonShine: c.skeletonShine,

    // —— Legacy aliases (do not remove — used across app) ——
    surfaceSecondary: c.backgroundSecondary,
    surfaceTertiary: c.surface,
    surfaceQuaternary: c.surfaceElevated,
    onSurface: c.textPrimary,
    onSurfaceMuted: c.textSecondary,
    onSurfaceDim: c.textTertiary,
    brand: c.accent,
    onBrand: c.onAccent,
  } as const;
}

/** Legacy spacing keys preserved for StyleSheet.create consumers */
const legacySpacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
  xxxl: 48,
  // New scale also available by number-like names
  '4': spacingScale[4],
  '8': spacingScale[8],
  '12': spacingScale[12],
  '16': spacingScale[16],
  '20': spacingScale[20],
  '24': spacingScale[24],
  '32': spacingScale[32],
  '40': spacingScale[40],
  '48': spacingScale[48],
  '64': spacingScale[64],
  '80': spacingScale[80],
} as const;

const legacyRadius = {
  xs: radiusScale.xs,
  sm: radiusScale.sm,
  md: radiusScale.md,
  lg: radiusScale.lg,
  xl: radiusScale.xl,
  '2xl': radiusScale['2xl'],
  full: radiusScale.full,
  pill: radiusScale.pill,
} as const;

const legacyMotion = {
  fast: motionTokens.duration.fast,
  base: motionTokens.duration.normal,
  normal: motionTokens.duration.normal,
  slow: motionTokens.duration.slow,
  hero: motionTokens.duration.hero,
  press: motionTokens.press,
  fadeIn: motionTokens.fadeIn,
  sheet: motionTokens.sheet,
  pressScale: motionTokens.pressScale,
  stagger: motionTokens.stagger,
  curve: motionTokens.curve,
} as const;

export const tokens = {
  language: 'ORA Quiet Premium' as const,
  color: colorsFromPalette(lightColors),
  colorLight: colorsFromPalette(lightColors),
  colorDark: colorsFromPalette(darkColors),
  spacing: legacySpacing,
  radius: legacyRadius,
  fs: fsLegacy,
  typography,
  motion: legacyMotion,
  touch: {
    min: 44,
  },
  icon: {
    size: iconSize,
    stroke: iconStroke,
  },
  shadow: getShadows('light'),
  shadowLight: getShadows('light'),
  shadowDark: getShadows('dark'),
  responsive: {
    phoneMax: 767,
    tabletMax: 1023,
    desktopMin: 1024,
  },
  a11y: {
    minTouch: 44,
    preferReducedMotionKey: 'reduceMotion',
  },
} as const;

export type AppTokens = typeof tokens;
export type AppColorTokens = ReturnType<typeof colorsFromPalette>;
