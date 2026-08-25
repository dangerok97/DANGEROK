/**
 * Profilo — your own space, and what you have decided ORA may do in it.
 *
 * A person arriving here is asking three questions in order: who am I in this
 * product, what is attached to it, and what is ORA allowed to use. The page is
 * arranged to answer them in that order — identity first, then the four
 * surfaces that hold the answers, then a quiet way out.
 *
 * Composition only. Every row leads to something that already works; the
 * capabilities a settings screen usually advertises and ORA does not have —
 * a plan, a verified badge, backups, two-factor, device sessions, notification
 * preferences — are absent rather than greyed out. This is the one page in the
 * product where a promise is indistinguishable from a lie.
 */
import { useCallback, useState } from 'react';
import { ScrollView, StyleSheet, View, useWindowDimensions } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect, useRouter } from 'expo-router';

import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { ErrorState } from '@/src/components/ui/ErrorState';
import { useAmbientInset } from '@/src/shell';
import { useAuth } from '@/src/contexts/AuthContext';
import { haptic } from '@/src/utils/haptic';
import {
  ACCOUNT_MAX_WIDTH,
  ACCOUNT_RAIL_WIDTH,
  ACCOUNT_TWO_COLUMN_MIN,
  AccessPanel,
  AccountHeader,
  AccountSkeleton,
  IdentityCard,
  InlineError,
  LogoutRow,
  PartialNote,
  PhotoDialog,
  SectionRow,
  SummaryPanel,
  WhyAccountDialog,
  shownMethods,
  primaryAccessLabel,
  sectionsFor,
  summaryRows,
  useAccount,
} from '@/src/components/account';

export default function ProfiloScreen() {
  const { colors } = useTheme();
  const ambient = useAmbientInset();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const { signOut } = useAuth();
  const { data, loading, error, reload } = useAccount();

  const twoColumn = width >= ACCOUNT_TWO_COLUMN_MIN;
  const padH = width < 380 ? tokens.spacing.lg : tokens.spacing.xl;

  const [whyOpen, setWhyOpen] = useState(false);
  const [photoOpen, setPhotoOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);

  useFocusEffect(
    useCallback(() => {
      void reload({ silent: true });
    }, [reload]),
  );

  const doLogout = useCallback(async () => {
    haptic('medium');
    setSigningOut(true);
    await signOut();
    router.replace('/login');
  }, [router, signOut]);

  const snapshot = data?.snapshot;

  if (loading && !snapshot) {
    return (
      <SafeAreaView
        edges={['top']}
        style={[styles.root, { backgroundColor: colors.backgroundPrimary }]}
        testID="profilo-screen"
      >
        <ScrollView
          contentContainerStyle={[
            styles.scroll,
            { paddingHorizontal: padH, paddingBottom: ambient.paddingBottom + tokens.spacing.xxl },
          ]}
        >
          <AccountSkeleton wide={twoColumn} />
        </ScrollView>
      </SafeAreaView>
    );
  }

  if (!snapshot) {
    return (
      <SafeAreaView
        edges={['top']}
        style={[styles.root, { backgroundColor: colors.backgroundPrimary }]}
        testID="profilo-screen"
      >
        <ScrollView
          contentContainerStyle={[
            styles.scroll,
            { paddingHorizontal: padH, paddingBottom: ambient.paddingBottom + tokens.spacing.xxl },
          ]}
        >
          <ErrorState
            title="Non riesco a caricare il tuo profilo"
            message={error || 'Riprova tra un momento.'}
            onRetry={() => void reload()}
          />
        </ScrollView>
      </SafeAreaView>
    );
  }

  const sections = sectionsFor(snapshot);
  const access = primaryAccessLabel(snapshot.methods);

  const main = (
    <>
      <IdentityCard snapshot={snapshot} onChangePhoto={() => setPhotoOpen(true)} />

      <View
        style={[styles.rows, { backgroundColor: colors.surface, borderColor: colors.border }]}
        testID="account-sections"
      >
        {sections.map((s, i) => (
          <SectionRow
            key={s.id}
            section={s}
            first={i === 0}
            onPress={() => {
              haptic('tap');
              router.push(s.href as any);
            }}
          />
        ))}
      </View>
    </>
  );

  const rail = (
    <>
      <SummaryPanel rows={summaryRows(snapshot)} />
      <AccessPanel
        methods={shownMethods(snapshot.methods)}
        onOpen={() => {
          haptic('tap');
          router.push('/account/permessi' as any);
        }}
      />
    </>
  );

  return (
    <SafeAreaView
      edges={['top']}
      style={[styles.root, { backgroundColor: colors.backgroundPrimary }]}
      testID="profilo-screen"
    >
      <ScrollView
        contentContainerStyle={[
          styles.scroll,
          { paddingHorizontal: padH, paddingBottom: ambient.paddingBottom + tokens.spacing.xxl },
        ]}
        showsVerticalScrollIndicator={false}
        testID="account-scroll"
      >
        <AccountHeader onWhy={() => setWhyOpen(true)} />

        {snapshot.partial ? (
          <PartialNote>Alcune informazioni non sono disponibili al momento.</PartialNote>
        ) : null}
        {error ? <InlineError>{error}</InlineError> : null}

        {twoColumn ? (
          <View style={styles.row}>
            <View style={styles.mainCol}>{main}</View>
            <View style={[styles.railCol, { width: ACCOUNT_RAIL_WIDTH }]}>{rail}</View>
          </View>
        ) : (
          // Phone: the same order, stacked. The rail becomes a closing summary
          // rather than being dropped.
          <View style={styles.stackAll}>
            {main}
            {rail}
          </View>
        )}

        <LogoutRow onPress={() => void doLogout()} busy={signingOut} />
      </ScrollView>

      <WhyAccountDialog open={whyOpen} onClose={() => setWhyOpen(false)} />
      <PhotoDialog open={photoOpen} onClose={() => setPhotoOpen(false)} accessLabel={access} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  scroll: {
    paddingTop: tokens.spacing.lg,
    maxWidth: ACCOUNT_MAX_WIDTH,
    width: '100%',
    alignSelf: 'center',
    gap: tokens.spacing.xl,
  },
  row: { flexDirection: 'row', gap: tokens.spacing.xl, alignItems: 'flex-start' },
  mainCol: { flex: 1, minWidth: 0, gap: tokens.spacing.lg },
  railCol: { gap: tokens.spacing.lg },
  stackAll: { gap: tokens.spacing.lg },
  rows: {
    borderRadius: tokens.radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    overflow: 'hidden',
  },
});
