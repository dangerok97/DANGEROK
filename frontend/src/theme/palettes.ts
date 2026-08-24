/**
 * ORA Quiet Premium — semantic color palettes (light + dark).
 * Accent: Deep Indigo (calm, not electric blue / not purple).
 * Dark surfaces are deep charcoal, never pure #000.
 * Light surfaces are warm off-white, designed (not inverted).
 */

export type SemanticColors = {
  // Backgrounds
  backgroundPrimary: string;
  backgroundSecondary: string;
  // Surfaces
  surface: string;
  surfaceElevated: string;
  surfaceGlass: string;
  /**
   * PX1.2 — the warm surface the Home hero sits on.
   *
   * Not a new palette: it is the same warm off-white family as
   * `backgroundPrimary`, one step toward the light, and exists so the single
   * most important card on the product reads as its own surface instead of
   * another white rectangle among white rectangles. Warmth is what makes the
   * hero feel editorial rather than administrative.
   */
  surfaceWarm: string;
  // Borders
  divider: string;
  border: string;
  borderStrong: string;
  // Text
  textPrimary: string;
  textSecondary: string;
  textTertiary: string;
  placeholder: string;
  // Semantic
  success: string;
  warning: string;
  error: string;
  info: string;
  successBg: string;
  warningBg: string;
  errorBg: string;
  infoBg: string;
  // Accent
  accent: string;
  onAccent: string;
  accentMuted: string;
  focusGlow: string;
  // Overlays
  scrim: string;
  skeleton: string;
  skeletonShine: string;
};

/** Deep Indigo — primary accent for Quiet Premium */
export const ACCENT_DEEP_INDIGO = '#3D4A8C';
export const ACCENT_ON = '#FFFFFF';
export const ACCENT_MUTED_LIGHT = '#E8EAF4';
export const ACCENT_MUTED_DARK = '#2A3158';

export const darkColors: SemanticColors = {
  backgroundPrimary: '#0E0E12',
  backgroundSecondary: '#16161C',
  surface: '#1A1A22',
  surfaceElevated: '#22222C',
  surfaceGlass: 'rgba(26, 26, 34, 0.82)',
  surfaceWarm: '#211F1D',
  divider: '#2C2C36',
  border: '#2E2E3A',
  borderStrong: '#3C3C4A',
  textPrimary: '#F4F4F6',
  textSecondary: '#A1A1AA',
  textTertiary: '#71717A',
  placeholder: '#63636E',
  success: '#34C759',
  warning: '#FF9F0A',
  error: '#FF453A',
  info: '#5B6CDB',
  successBg: '#13281A',
  warningBg: '#2A1F0C',
  errorBg: '#2A1414',
  infoBg: '#1A1F3A',
  accent: ACCENT_DEEP_INDIGO,
  onAccent: ACCENT_ON,
  accentMuted: ACCENT_MUTED_DARK,
  focusGlow: 'rgba(61, 74, 140, 0.45)',
  scrim: 'rgba(8, 8, 12, 0.55)',
  skeleton: '#22222C',
  skeletonShine: '#2E2E3A',
};

export const lightColors: SemanticColors = {
  backgroundPrimary: '#F6F4F1',
  backgroundSecondary: '#EFECE7',
  surface: '#FFFFFF',
  surfaceElevated: '#FFFFFF',
  surfaceGlass: 'rgba(255, 255, 255, 0.78)',
  surfaceWarm: '#FBF6EE',
  divider: '#E5E2DC',
  border: '#DAD6CF',
  borderStrong: '#C4C0B8',
  textPrimary: '#1C1C1E',
  textSecondary: '#5C5C66',
  textTertiary: '#8E8E96',
  placeholder: '#A1A1AA',
  success: '#248A3D',
  warning: '#C77C00',
  error: '#D70015',
  info: '#3D4A8C',
  successBg: '#E8F5EC',
  warningBg: '#FFF4E0',
  errorBg: '#FDECEC',
  infoBg: '#ECEEF8',
  accent: ACCENT_DEEP_INDIGO,
  onAccent: ACCENT_ON,
  accentMuted: ACCENT_MUTED_LIGHT,
  focusGlow: 'rgba(61, 74, 140, 0.28)',
  scrim: 'rgba(28, 28, 30, 0.40)',
  skeleton: '#E8E5DF',
  skeletonShine: '#F2F0EB',
};
