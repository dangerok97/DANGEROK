/**
 * Where to go back to after signing in.
 *
 * Opening a link to a document while signed out has to end at that document,
 * not at Home — otherwise every shared link costs the person a second search
 * through the app for the thing they were already looking at.
 *
 * The value travels through the URL, which means it is untrusted input: it
 * arrives from wherever the link came from. So it is validated as a route
 * rather than sanitised as a string. Only an in-app absolute path under a
 * known prefix survives; anything that could leave the app — a scheme, a
 * protocol-relative host, a backslash, an encoded one — resolves to nothing
 * and the person lands on Home, which is never wrong, only less specific.
 *
 * Import-free on purpose: this is the security-shaped decision, and it is
 * testable without a router.
 */

/** Route prefixes a person can be sent back to. Everything else is refused. */
const ALLOWED = [
  '/(tabs)',
  '/document/',
  '/documenti',
  '/goal-workspace/',
  '/life-area/',
  '/ora',
  '/attivita',
  '/contesti',
  '/account/',
  '/settings',
  '/memory-clarify/',
  '/situazione',
  '/manage-calendars',
];

/** Never a destination: you would arrive where you just were. */
const REFUSED = ['/login', '/life-setup'];

/** Space, control characters and DEL. Checked by code point, not by regex. */
function hasUnsafeChars(value: string): boolean {
  for (let i = 0; i < value.length; i += 1) {
    const c = value.charCodeAt(i);
    if (c <= 0x20 || c === 0x7f) return true;
  }
  return false;
}

export function safeNextTarget(raw?: string | null): string | null {
  if (!raw) return null;

  let value = String(raw);
  // A link may arrive encoded once; decoding twice is how "%252F%252Fevil"
  // becomes "//evil", so it is decoded exactly once and then judged.
  try {
    value = decodeURIComponent(value);
  } catch {
    return null;
  }

  if (hasUnsafeChars(value)) return null;
  if (value.length > 512) return null;
  if (!value.startsWith('/')) return null;
  // "//host" is protocol-relative and leaves the app; a backslash is the same
  // trick spelled the way some parsers normalise.
  if (value.startsWith('//')) return null;
  if (value.includes('\\')) return null;

  const path = value.split('?')[0].split('#')[0];
  if (REFUSED.some((r) => path === r || path.startsWith(`${r}/`))) return null;
  if (
    !ALLOWED.some((p) =>
      p.endsWith('/') ? path.startsWith(p) : path === p || path.startsWith(`${p}/`),
    )
  ) {
    return null;
  }
  return value;
}

/** The login route to send someone to, carrying where they meant to be. */
export function loginHrefFor(path?: string | null): string {
  const next = safeNextTarget(path);
  return next ? `/login?next=${encodeURIComponent(next)}` : '/login';
}
