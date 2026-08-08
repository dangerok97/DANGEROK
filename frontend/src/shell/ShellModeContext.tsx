import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { OraShellMode } from './types';

type ShellModeContextValue = {
  mode: OraShellMode;
  setMode: (mode: OraShellMode) => void;
};

const ShellModeContext = createContext<ShellModeContextValue | null>(null);

export function ShellModeProvider({ children }: { children: React.ReactNode }) {
  const [mode, setModeState] = useState<OraShellMode>('ambient');
  const setMode = useCallback((next: OraShellMode) => {
    setModeState(next);
  }, []);

  const value = useMemo(() => ({ mode, setMode }), [mode, setMode]);

  return <ShellModeContext.Provider value={value}>{children}</ShellModeContext.Provider>;
}

export function useShellMode(): ShellModeContextValue {
  const ctx = useContext(ShellModeContext);
  if (!ctx) {
    return {
      mode: 'ambient',
      setMode: () => undefined,
    };
  }
  return ctx;
}

/** Declare shell mode for the lifetime of a screen. Restores ambient on unmount. */
export function useDeclareShellMode(mode: OraShellMode) {
  const { setMode } = useShellMode();
  useEffect(() => {
    setMode(mode);
    return () => setMode('ambient');
  }, [mode, setMode]);
}
