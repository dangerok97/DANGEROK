import { useCallback, useRef } from 'react';

/**
 * One press, one request.
 *
 * `setBusy(true)` does not take effect until React re-renders, so three taps
 * inside the same tick all read `busy === false` and all fire. Measured on the
 * documents preference: three rapid presses on the switch sent three PATCHes,
 * and the last one to answer decided the value. A ref changes synchronously,
 * which is the only thing fast enough to stop the second press.
 *
 * This does not replace the visible busy state — the control still has to say
 * it is working. It stops the request the person did not mean to make.
 */
export function useInflight() {
  const running = useRef(false);
  return useCallback(async (run: () => Promise<void> | void): Promise<void> => {
    if (running.current) return;
    running.current = true;
    try {
      await run();
    } finally {
      running.current = false;
    }
  }, []);
}
