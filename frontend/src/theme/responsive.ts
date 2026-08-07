import { useWindowDimensions } from 'react-native';
import { tokens } from './tokens';

export type Breakpoint = 'phone' | 'tablet' | 'desktop';

export function breakpointForWidth(width: number): Breakpoint {
  if (width <= tokens.responsive.phoneMax) return 'phone';
  if (width <= tokens.responsive.tabletMax) return 'tablet';
  return 'desktop';
}

export function useBreakpoint(): Breakpoint {
  const { width } = useWindowDimensions();
  return breakpointForWidth(width);
}

export function useResponsiveValue<T>(map: Partial<Record<Breakpoint, T>> & { phone: T }): T {
  const bp = useBreakpoint();
  return map[bp] ?? map.tablet ?? map.phone;
}

/** Content max width for desktop web — keeps editorial calm, not dashboard stretch */
export const contentMaxWidth = {
  phone: undefined as number | undefined,
  tablet: 720,
  desktop: 840,
} as const;
