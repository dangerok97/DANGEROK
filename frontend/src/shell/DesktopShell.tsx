/**
 * Il guscio desktop per le schermate che non vivono dentro `(tabs)`.
 *
 * La conversazione, Conosciamoci, la preparazione di una telefonata: sul
 * desktop hanno la stessa barra laterale della Home, e la voce accesa è quella
 * a cui appartengono. Su telefono non aggiunge niente — ORA 1.0 è iOS, e lì la
 * navigazione è un'altra cosa.
 */
import type { ReactNode } from 'react';
import { StyleSheet, View } from 'react-native';
import { usePathname, useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useBreakpoint } from '@/src/theme/responsive';
import { ora } from '@/src/theme/oraSurface';
import { AMBIENT_NAV_ITEMS } from './navItems';
import { SideRail, type RailKey } from './SideRail';

const ROTTE: Record<string, string> = {
  index: '/',
  contesti: '/contesti',
  ora: '/ora',
  chiamate: '/chiamate',
  attivita: '/attivita',
  documenti: '/documenti',
  profilo: '/profilo',
};

/** Quale voce della barra accendere per un indirizzo. */
export function railKeyFor(pathname: string): RailKey {
  if (pathname === '/' || pathname === '') return 'index';
  if (pathname.startsWith('/ora')) return 'ora';
  if (pathname.startsWith('/life-setup') || pathname.startsWith('/contesti')) return 'contesti';
  if (pathname.startsWith('/prepara-chiamata') || pathname.startsWith('/chiamate')) return 'chiamate';
  if (pathname.startsWith('/document')) return 'documenti';
  if (pathname.startsWith('/attivita')) return 'attivita';
  if (pathname.startsWith('/profilo')) return 'profilo';
  return null;
}

export function DesktopShell({ children, active }: { children: ReactNode; active?: RailKey }) {
  const bp = useBreakpoint();
  const router = useRouter();
  const pathname = usePathname();
  const insets = useSafeAreaInsets();

  if (bp !== 'desktop') return <>{children}</>;

  return (
    <View style={[styles.row, { backgroundColor: ora.canvas }]}>
      <SideRail
        active={active ?? railKeyFor(pathname)}
        topInset={insets.top}
        bottomInset={insets.bottom}
        onNavigate={(key) => {
          const dove = AMBIENT_NAV_ITEMS.find((i) => i.key === key)?.href || ROTTE[key] || '/';
          router.push(dove as any);
        }}
      />
      <View style={styles.content}>{children}</View>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flex: 1, flexDirection: 'row' },
  content: { flex: 1, minWidth: 0 },
});
