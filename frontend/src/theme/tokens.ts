/**
 * ORA Design Tokens — dark-first, monochromatic, Apple HIG inspired.
 * Semantic colors are consistent between fill/on/soft variants so components
 * can express state (info/success/warning/error) without hard-coded hex values.
 */
export const tokens = {
  color: {
    // Surfaces
    surface: '#000000',
    surfaceSecondary: '#121212',
    surfaceTertiary: '#1C1C1E',
    surfaceQuaternary: '#242426',
    surfaceElevated: '#1A1A1C',

    // Text
    onSurface: '#F2F2F2',
    onSurfaceMuted: '#8E8E93',
    onSurfaceDim: '#6B6B70',

    // Brand (light-on-dark)
    brand: '#FAFAFA',
    onBrand: '#000000',

    // Borders
    border: '#2C2C2E',
    borderStrong: '#3A3A3C',
    divider: '#2C2C2E',

    // Semantic — foreground
    success: '#30D158',
    warning: '#FF9F0A',
    error: '#FF453A',
    info: '#0A84FF',

    // Semantic — background (soft tints for banners / chips)
    successBg: '#0F2A15',
    warningBg: '#2E1F09',
    errorBg: '#2E1414',
    infoBg: '#0C1E33',

    // Overlays
    scrim: 'rgba(0,0,0,0.55)',
    skeleton: '#1A1A1C',
    skeletonShine: '#26262A',
  },
  spacing: {
    xs: 4,
    sm: 8,
    md: 12,
    lg: 16,
    xl: 24,
    xxl: 32,
    xxxl: 48,
  },
  radius: {
    sm: 6,
    md: 12,
    lg: 20,
    xl: 28,
    pill: 999,
  },
  fs: {
    sm: 12,
    base: 14,
    lg: 16,
    xl: 20,
    xxl: 24,
    xxxl: 32,
    display: 40,
  },
  motion: {
    fast: 180,
    base: 240,
    slow: 320,
  },
  touch: {
    min: 44,
  },
} as const;
