import { View, Text, StyleSheet, Pressable, ScrollView } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { useRouter } from 'expo-router';

import { tokens } from '@/src/theme/tokens';
import { useAuth } from '@/src/contexts/AuthContext';
import { useAmbientInset } from '@/src/shell';

type Row = {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  sub?: string;
  disabled?: boolean;
  testID: string;
  onPress?: () => void;
};

export default function ProfiloScreen() {
  const ambient = useAmbientInset();
  const { user, signOut } = useAuth();
  const router = useRouter();

  const doLogout = async () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    await signOut();
    router.replace('/login');
  };

  const activeRows: Row[] = [
    {
      icon: 'settings-outline',
      label: 'Impostazioni',
      sub: 'Account collegati',
      testID: 'profile-row-settings',
      onPress: () => router.push('/settings'),
    },
    {
      icon: 'document-text-outline',
      label: 'Documenti',
      sub: 'File caricati e archivio',
      testID: 'profile-row-documenti',
      onPress: () => router.push('/(tabs)/documenti'),
    },
  ];

  const futureRows: Row[] = [
    { icon: 'wallet-outline', label: 'Dashboard spese', sub: 'In arrivo', disabled: true, testID: 'profile-row-spese' },
    { icon: 'flag-outline', label: 'Obiettivi', sub: 'In arrivo', disabled: true, testID: 'profile-row-obiettivi' },
    { icon: 'mail-outline', label: 'Email & Messaggi', sub: 'In arrivo', disabled: true, testID: 'profile-row-email' },
    { icon: 'card-outline', label: 'Banche & Wallet', sub: 'In arrivo', disabled: true, testID: 'profile-row-banche' },
  ];

  const renderRow = (r: Row, i: number, total: number) => {
    const body = (
      <>
        <Ionicons
          name={r.icon}
          size={20}
          color={r.disabled ? tokens.color.onSurfaceMuted : tokens.color.onSurface}
        />
        <View style={{ flex: 1 }}>
          <Text style={[styles.rowLabel, r.disabled && { color: tokens.color.onSurfaceMuted }]}>{r.label}</Text>
          {r.sub ? <Text style={styles.rowSub}>{r.sub}</Text> : null}
        </View>
        <Ionicons name="chevron-forward" size={16} color={tokens.color.onSurfaceDim} />
      </>
    );

    const rowStyle = [
      styles.row,
      i < total - 1 && styles.rowDivider,
      r.disabled && styles.rowDisabled,
    ];

    if (r.disabled || !r.onPress) {
      return (
        <View key={r.testID} style={rowStyle} testID={r.testID}>
          {body}
        </View>
      );
    }

    return (
      <Pressable
        key={r.testID}
        testID={r.testID}
        onPress={() => {
          Haptics.selectionAsync();
          r.onPress?.();
        }}
        style={({ pressed }) => [...rowStyle, pressed && styles.pressed]}
      >
        {body}
      </Pressable>
    );
  };

  return (
    <SafeAreaView edges={['top']} style={styles.root}>
      <ScrollView
        contentContainerStyle={[styles.scroll, { paddingBottom: ambient.paddingBottom }]}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.header}>
          <Text style={styles.brand}>PROFILO</Text>
          <Text style={styles.h1}>{user?.name ? `Ciao,\n${user.name}.` : 'Il tuo\nprofilo.'}</Text>
          <Text style={styles.email} testID="profile-email-text">{user?.email}</Text>
        </View>

        <Text style={styles.sectionLabel}>IL TUO SPAZIO</Text>
        <View style={styles.group}>
          {activeRows.map((r, i) => renderRow(r, i, activeRows.length))}
        </View>

        <Text style={styles.sectionLabel}>PROSSIMAMENTE</Text>
        <View style={styles.group}>
          {futureRows.map((r, i) => renderRow(r, i, futureRows.length))}
        </View>

        <Text style={styles.sectionLabel}>ACCOUNT</Text>
        <View style={styles.group}>
          <Pressable
            testID="profile-logout-button"
            onPress={doLogout}
            style={({ pressed }) => [styles.row, pressed && styles.pressed]}
          >
            <Ionicons name="log-out-outline" size={20} color={tokens.color.error} />
            <Text style={[styles.rowLabel, { color: tokens.color.error }]}>Esci</Text>
          </Pressable>
        </View>

        <Text style={styles.footNote}>
          ORA v1 · Il sistema operativo{'\n'}della tua vita quotidiana.
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: tokens.color.surface },
  scroll: { paddingHorizontal: tokens.spacing.lg, paddingTop: tokens.spacing.sm },
  header: { paddingHorizontal: tokens.spacing.xs, marginBottom: tokens.spacing.xl, gap: tokens.spacing.xs },
  brand: { color: tokens.color.onSurfaceMuted, fontSize: tokens.fs.sm, fontWeight: '700', letterSpacing: 2 },
  h1: { color: tokens.color.onSurface, fontSize: tokens.fs.xxxl, fontWeight: '700', lineHeight: 38, letterSpacing: -0.8 },
  email: { color: tokens.color.onSurfaceMuted, fontSize: tokens.fs.base, marginTop: tokens.spacing.sm },
  sectionLabel: {
    color: tokens.color.onSurfaceMuted,
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 1.6,
    paddingHorizontal: tokens.spacing.md,
    marginTop: tokens.spacing.lg,
    marginBottom: tokens.spacing.sm,
  },
  group: {
    borderRadius: tokens.radius.lg,
    backgroundColor: tokens.color.surfaceSecondary,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: tokens.color.border,
    overflow: 'hidden',
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: tokens.spacing.md,
    paddingHorizontal: tokens.spacing.lg,
    minHeight: 56,
  },
  rowDivider: { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: tokens.color.border },
  rowDisabled: { opacity: 0.5 },
  rowLabel: { color: tokens.color.onSurface, fontSize: tokens.fs.lg, fontWeight: '500' },
  rowSub: { color: tokens.color.onSurfaceMuted, fontSize: tokens.fs.sm, marginTop: 2 },
  pressed: { opacity: 0.6 },
  footNote: {
    color: tokens.color.onSurfaceDim,
    fontSize: tokens.fs.sm,
    textAlign: 'center',
    marginTop: tokens.spacing.xxl,
    lineHeight: 20,
  },
});
