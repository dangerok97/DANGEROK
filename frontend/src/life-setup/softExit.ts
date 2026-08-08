/**
 * Soft-exit (Esci / Più tardi) visibility for Life Setup.
 * Source of truth: resume route param + start.resumed — never wrap `done` alone.
 */

export type SoftExitInput = {
  /** Precomputed: Boolean(resumeParam) || Boolean(start.resumed). */
  allowSoftExit?: boolean;
  resumed?: boolean | null;
  resumeParam?: string | string[] | null;
  done: boolean;
};

/** True when the user is on a returning/resume flow (not mandatory first-run). */
export function computeAllowSoftExit(input: {
  resumed?: boolean | null;
  resumeParam?: string | string[] | null;
}): boolean {
  const raw = Array.isArray(input.resumeParam) ? input.resumeParam[0] : input.resumeParam;
  const resumeParam = typeof raw === 'string' ? raw.trim() : '';
  return Boolean(resumeParam) || Boolean(input.resumed);
}

/** showEsci / showPostpone = allowSoftExit && !done */
export function shouldShowSoftExit(input: SoftExitInput): boolean {
  const allow =
    typeof input.allowSoftExit === 'boolean'
      ? input.allowSoftExit
      : computeAllowSoftExit(input);
  return allow && !input.done;
}
