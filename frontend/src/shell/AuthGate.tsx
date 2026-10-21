import { useEffect, useRef } from 'react';
import { ActivityIndicator, Pressable, Text, View } from 'react-native';
import { useGlobalSearchParams, usePathname, useRouter } from 'expo-router';

import { useAuth } from '@/src/contexts/AuthContext';
import { tokens } from '@/src/theme/tokens';
import { useSessionCleanup } from '@/src/ambient/usePushRegistration';
import { sessionCleanup } from '@/src/ambient/pushRegistration';

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
const PUBLIC_PREFIXES = ['/login', '/google-auth-complete', '/privacy', '/terms', '/+not-found', '/_sitemap'];

function isPublic(pathname: string): boolean {
  return PUBLIC_PREFIXES.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

export function AuthGate({ children }: { children: React.ReactNode }) {
  const { user, loading, refreshing, recovery, refresh } = useAuth();
  const cleanup = useSessionCleanup();
  const router = useRouter();
  const pathname = usePathname();
  const params = useGlobalSearchParams<{ scan?: string }>();
  // Preserve only this bounded, non-secret action through native sign-in.
  const destination = pathname === '/casa' && params.scan === '1' ? '/casa?scan=1' : pathname;
  const sent = useRef<string | null>(null);

  const publicRoute = isPublic(pathname || '/');
  const anonymous = !loading && !user && !recovery && !publicRoute;

  useEffect(() => {
    if (!anonymous) {
      sent.current = null;
      return;
    }
    // Redirect once per destination: without this the effect re-runs on every
    // render while the replace is in flight and stacks navigations.
    if (sent.current === destination) return;
    sent.current = destination;
    router.replace(loginHrefFor(destination) as any);
  }, [anonymous, destination, router]);

  if (recovery && !user && !publicRoute) {
    return (
      <View testID="auth-session-recovery" style={{
        flex: 1, justifyContent: 'center', padding: tokens.spacing.xl,
        backgroundColor: tokens.color.backgroundPrimary,
      }}>
        <RecoveryNotice
          message="Non riesco a verificare la sessione. Riprovo appena torna la connessione."
          busy={refreshing}
          onRetry={() => void refresh()}
        />
      </View>
    );
  }

  const notices = (
    <>
      {recovery && user ? <RecoveryNotice
        message="La connessione a ORA è interrotta. La tua sessione è conservata."
        busy={refreshing} onRetry={() => void refresh()}
      /> : null}
      {cleanup.pending || cleanup.storageError ? <RecoveryNotice
        message={cleanup.storageError
          ? 'Non riesco ancora a leggere o salvare le sessioni in attesa di chiusura. Riprovo appena possibile.'
          : 'L’uscita locale è completata. La connessione non ha ancora confermato la revoca sul server.'}
        busy={cleanup.busy} onRetry={() => void sessionCleanup.flush()}
        testID="session-revocation-pending"
      /> : null}
    </>
  );

  // The root route runs its own gate and shows its own splash; letting this
  // one render over it would flash two spinners on every cold start.
  if (publicRoute || pathname === '/') return <View style={{ flex: 1 }}>{notices}{children}</View>;

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

  return <View style={{ flex: 1 }}>{notices}{children}</View>;
}

function RecoveryNotice({ message, busy, onRetry, testID = 'auth-recovery-notice' }: {
  message: string; busy: boolean; onRetry: () => void; testID?: string;
}) {
  return (
    <View testID={testID} style={{
      paddingHorizontal: tokens.spacing.lg, paddingVertical: tokens.spacing.sm,
      backgroundColor: tokens.color.backgroundSecondary,
      flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: tokens.spacing.md,
    }}>
      <Text accessibilityLiveRegion="polite" style={{
        flexGrow: 1, flexShrink: 1, flexBasis: 220,
        fontSize: 14, lineHeight: 20, color: tokens.color.textSecondary,
      }}>{message}</Text>
      <Pressable onPress={onRetry} disabled={busy} accessibilityRole="button"
        testID={`${testID}-retry`} style={{ minHeight: 44, justifyContent: 'center' }}>
        <Text style={{ fontSize: 14, fontWeight: '600', color: tokens.color.accent }}>
          {busy ? 'Riprovo…' : 'Riprova'}
        </Text>
      </Pressable>
    </View>
  );
}
