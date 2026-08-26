import { useEffect, useRef } from 'react';
import { ActivityIndicator, View } from 'react-native';
import { usePathname, useRouter } from 'expo-router';

import { useAuth } from '@/src/contexts/AuthContext';
import { tokens } from '@/src/theme/tokens';

import { loginHrefFor } from './nextTarget';

/**
 * "I don't know yet" is not "no".
 *
 * Before this, exactly one route in the product asked whether anyone was
 * signed in: `/`. Everything else — a document, a workspace, a conversation,
 * an account subpage — mounted, fetched, got a 401 and told the person their
 * session had expired. Opening a shared link while signed out ended on a
 * dead-end error page with a "Torna indietro" that had no history to go back
 * to, and no way to sign in from there.
 *
 * The distinction this exists to hold is the one the old code did not have:
 *
 *   hydrating  → say nothing, show the shape of a page arriving
 *   anonymous  → go to login, carrying where they meant to be
 *   signed in  → get out of the way
 *
 * It is deliberately the whole tree's business rather than each screen's.
 * Every screen that forgets is a screen that tells someone their session
 * expired when it simply had not been read yet.
 */

/** Routes that must render without a session — otherwise nobody can sign in. */
const PUBLIC_PREFIXES = ['/login', '/+not-found', '/_sitemap'];

function isPublic(pathname: string): boolean {
  return PUBLIC_PREFIXES.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

export function AuthGate({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const sent = useRef<string | null>(null);

  const publicRoute = isPublic(pathname || '/');
  const anonymous = !loading && !user && !publicRoute;

  useEffect(() => {
    if (!anonymous) {
      sent.current = null;
      return;
    }
    // Redirect once per destination: without this the effect re-runs on every
    // render while the replace is in flight and stacks navigations.
    if (sent.current === pathname) return;
    sent.current = pathname;
    router.replace(loginHrefFor(pathname) as any);
  }, [anonymous, pathname, router]);

  // The root route runs its own gate and shows its own splash; letting this
  // one render over it would flash two spinners on every cold start.
  if (publicRoute || pathname === '/') return <>{children}</>;

  if (loading || anonymous) {
    return (
      <View
        testID="auth-gate-hydrating"
        style={{
          flex: 1,
          backgroundColor: tokens.color.backgroundPrimary,
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <ActivityIndicator color={tokens.color.onSurfaceMuted} />
      </View>
    );
  }

  return <>{children}</>;
}
