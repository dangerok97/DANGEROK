/**
 * The phone bar on every screen, not only inside the tabs.
 *
 * Owner feedback 24/10/2026: Home showed Home · Vita · ORA · Attività ·
 * Documenti, but Vita, Conosciamoci and every other page outside `(tabs)` lost
 * it, leaving only "Indietro". Here the same bar is drawn from the address,
 * not from a tab navigator. Screens with their own input at the bottom (the
 * ORA conversation) and sign-in pages keep the whole height.
 */
import { useSegments, usePathname, useRouter } from 'expo-router';

import { useAuth } from '@/src/contexts/AuthContext';
import { useBreakpoint } from '@/src/theme/responsive';
import { AmbientBar } from './AmbientTabBar';
import { railKeyFor } from './DesktopShell';
import { AMBIENT_NAV_ITEMS } from './navItems';
import { shouldShowGlobalBar } from './globalBar';
export { BAR_HIDDEN_SEGMENTS, shouldShowGlobalBar } from './globalBar';

const ROUTES: Record<string, string> = {
  index: '/', contesti: '/vita', ora: '/ora', attivita: '/attivita', documenti: '/documenti',
  chiamate: '/chiamate', luoghi: '/luoghi', profilo: '/profilo',
};

export function useGlobalBarVisible(): boolean {
  const segments = useSegments() as string[];
  const { user } = useAuth();
  const desktop = useBreakpoint() === 'desktop';
  return shouldShowGlobalBar(segments[0], !!user, desktop);
}

export function GlobalPhoneBar() {
  const visible = useGlobalBarVisible();
  const pathname = usePathname();
  const router = useRouter();
  if (!visible) return null;
  const routes = AMBIENT_NAV_ITEMS.map((i) => ({ key: i.route, name: i.route, params: undefined }));
  const active = railKeyFor(pathname);
  const index = Math.max(-1, routes.findIndex((r) => r.name === active));
  const state = { routes, index, key: 'global-bar', routeNames: routes.map((r) => r.name), type: 'tab', stale: false, history: [], preloadedRouteKeys: [] };
  const navigation = {
    navigate: (name: string) => router.push((ROUTES[name] || '/') as any),
    emit: () => ({ defaultPrevented: false }),
  };
  return <AmbientBar state={state as any} navigation={navigation as any} />;
}
