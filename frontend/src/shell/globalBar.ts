/** Where the global phone bar is drawn — pure, so it can be tested in Node. */
/**
 * Top-level segments that never show the bar: their own bottom input or
 * controls, a full-screen camera, or no session. Vision (24/10 screenshot):
 * the bar covered Ricomponi, Apertura and Spegni, the only way out.
 */
export const BAR_HIDDEN_SEGMENTS = new Set([
  '(tabs)', 'login', 'google-auth-complete', 'benvenuto', 'privacy', 'terms',
  'ora', 'ora-ai', 'conversation', 'notifica', '+not-found', '_sitemap',
  'vision-xray', 'chiamate',
]);

export function shouldShowGlobalBar(segment: string | undefined, signedIn: boolean, desktop: boolean): boolean {
  return signedIn && !desktop && !!segment && !BAR_HIDDEN_SEGMENTS.has(segment);
}

