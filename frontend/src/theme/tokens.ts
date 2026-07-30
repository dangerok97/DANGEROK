/**
 * ORA Design Tokens — dark-first, monochromatic, Apple HIG inspired.
 */
export const tokens = {
  color: {
    surface: '#000000',
    surfaceSecondary: '#121212',
    surfaceTertiary: '#1C1C1E',
    onSurface: '#F2F2F2',
    onSurfaceMuted: '#8E8E93',
    onSurfaceDim: '#6B6B70',
    brand: '#FAFAFA',
    onBrand: '#000000',
    border: '#2C2C2E',
    borderStrong: '#3A3A3C',
    divider: '#2C2C2E',
    success: '#30D158',
    warning: '#FF9F0A',
    error: '#FF453A',
    info: '#0A84FF',
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
} as const;
