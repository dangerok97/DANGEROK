import { useReducedMotion } from './useReducedMotion';
import { SHELL_TRANSITION_MS } from './constants';

/**
 * Ambient ↔ Focus foundation duration (~220–280ms).
 * Returns 0 when system reduce-motion is on.
 */
export function useShellTransitionMs(): number {
  const reduced = useReducedMotion();
  return reduced ? 0 : SHELL_TRANSITION_MS;
}

export function shellTransitionMs(reducedMotion: boolean): number {
  return reducedMotion ? 0 : SHELL_TRANSITION_MS;
}
