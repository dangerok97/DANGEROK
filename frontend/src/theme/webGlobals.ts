import { Platform } from 'react-native';

/**
 * The two things a React Native tree cannot say about itself on the web.
 *
 * `app/+html.tsx` looks like the place for this and is not: with
 * `web.output: "single"` Expo serves its own shell and never evaluates that
 * file, so the rules already sitting in it have no effect. This runs once from
 * the root layout instead, which is true in dev and in the shipped bundle.
 *
 * 1. The document's language. ORA is written in Italian and the shell declares
 *    English, so a screen reader reads every sentence in the product with an
 *    English voice — "Scade tra 11 giorni" pronounced as if it were English is
 *    not a small inconvenience, it is unusable.
 *
 * 2. One focus ring. Every control was falling back to the browser's own
 *    outline, which changes shape between engines and reads as a rendering
 *    artefact against ORA's rounded, low-contrast surfaces. This is the accent
 *    at a legible weight, offset so it never sits on top of what it marks, and
 *    scoped to `:focus-visible` so mouse and touch are untouched. The outline
 *    is replaced, never removed.
 */
const STYLE_ID = 'ora-web-globals';

const CSS = `
:focus { outline: none; }
:focus-visible,
[tabindex]:focus-visible,
[role="button"]:focus-visible,
[role="tab"]:focus-visible,
[role="radio"]:focus-visible,
[role="switch"]:focus-visible,
button:focus-visible,
a:focus-visible,
input:focus-visible,
textarea:focus-visible {
  outline: 2px solid #3D4A8C;
  outline-offset: 2px;
  border-radius: 6px;
}
@media (prefers-contrast: more) {
  :focus-visible { outline-width: 3px; }
}
`;

export function installWebGlobals(): void {
  if (Platform.OS !== 'web') return;
  if (typeof document === 'undefined') return;

  document.documentElement.lang = 'it';

  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement('style');
  style.id = STYLE_ID;
  style.textContent = CSS;
  document.head.appendChild(style);
}
