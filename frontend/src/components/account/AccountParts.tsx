import * as React from 'react';
import {
  ActivityIndicator,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';

import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { Avatar, titleCase } from '@/src/shell';
import { haptic } from '@/src/utils/haptic';

import {
  connectionLabel,
  displayName,
  memberSinceLabel,
  type AccountSnapshot,
  type ConnectionState,
  type Section,
  type SummaryRow,
} from './accountModel';

/** The reading column the other PX1.x surfaces use. */
export const ACCOUNT_MAX_WIDTH = 1220;
export const ACCOUNT_RAIL_WIDTH = 300;
export const ACCOUNT_TWO_COLUMN_MIN = 1060;
/** A subpage is one column of prose and controls, never a dashboard. */
export const SUBPAGE_MAX_WIDTH = 720;

/* -------------------------------------------------------------------------- */
/* Header                                                                     */
/* -------------------------------------------------------------------------- */

export function AccountHeader({ onWhy }: { onWhy: () => void }) {
  const { colors } = useTheme();
  return (
    <View style={styles.header} testID="account-header">
      <View style={styles.headerText}>
        <Text
          style={[styles.title, { color: colors.textPrimary }]}
          accessibilityRole="header"
          aria-level={1}
        >
          Profilo
        </Text>
        <Text style={[styles.sub, { color: colors.textSecondary }]}>
          Gestisci il tuo account, le preferenze e i permessi.
        </Text>
      </View>
      <Pressable
        onPress={onWhy}
        style={({ pressed }) => [
          styles.whyBtn,
          { backgroundColor: colors.surface, borderColor: colors.border },
          pressed && styles.pressed,
        ]}
        accessibilityRole="button"
        testID="account-why"
      >
        <Ionicons name="sparkles-outline" size={14} color={colors.accent} />
        <Text style={[styles.whyLabel, { color: colors.textSecondary }]}>Perché conta?</Text>
      </Pressable>
    </View>
  );
}

/**
 * What this place is for.
 *
 * Three sentences, and the last one is the one that matters: the actions that
 * need agreement keep needing it. Nothing about plans, storage or security
 * theatre — this is a person asking what they control, and being told.
 */
export function WhyAccountDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { colors } = useTheme();
  const lines = [
    'Qui controlli come ORA lavora con te: quali servizi può usare, quali permessi ha e come gestisce i tuoi dati.',
    'Le azioni che richiedono il tuo consenso restano sotto il tuo controllo.',
  ];
  return (
    <Modal visible={open} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable
        style={[styles.scrim, { backgroundColor: colors.scrim }]}
        onPress={onClose}
        accessibilityLabel="Chiudi"
      >
        <View
          style={[
            styles.dialog,
            { backgroundColor: colors.surfaceElevated, borderColor: colors.border },
          ]}
          onStartShouldSetResponder={() => true}
          accessibilityViewIsModal
          testID="account-why-dialog"
        >
          <View style={styles.dialogHead}>
            <Text
              style={[styles.dialogTitle, { color: colors.textPrimary }]}
              accessibilityRole="header"
              aria-level={2}
            >
              Perché conta
            </Text>
            <Pressable
              onPress={onClose}
              hitSlop={8}
              style={({ pressed }) => [styles.close, pressed && styles.pressed]}
              accessibilityRole="button"
              accessibilityLabel="Chiudi"
              testID="account-why-close"
            >
              <Ionicons name="close" size={20} color={colors.textTertiary} />
            </Pressable>
          </View>
          {lines.map((l) => (
            <Text key={l} style={[styles.dialogLine, { color: colors.textSecondary }]}>
              {l}
            </Text>
          ))}
        </View>
      </Pressable>
    </Modal>
  );
}

/* -------------------------------------------------------------------------- */
/* Identity                                                                   */
/* -------------------------------------------------------------------------- */

/**
 * Who you are, at the top of your own page.
 *
 * The reference puts an "edit profile" button here. Name and email in ORA come
 * from the way you signed in and there is no endpoint that changes either, so
 * the button says what it does: the photo is the part of this card a person
 * can actually change.
 */
export function IdentityCard({
  snapshot,
  onChangePhoto,
  busy,
}: {
  snapshot: AccountSnapshot;
  onChangePhoto: () => void;
  busy?: boolean;
}) {
  const { colors } = useTheme();
  const member = memberSinceLabel(snapshot.memberSince);
  /*
    Presentation casing only — the same helper the rail uses, so a person is
    called the same thing in both places. The stored name is never rewritten:
    people type their own name in lower case all the time, and saving a
    corrected version would quietly overwrite how they chose to write it. An
    email standing in for a missing name is left exactly as it is; capitalising
    an address would be wrong, not polite.
  */
  const shown = snapshot.name?.trim() ? titleCase(snapshot.name) : displayName(snapshot);
  return (
    <View
      style={[styles.identity, { backgroundColor: colors.surface, borderColor: colors.border }]}
      testID="account-identity"
    >
      <Pressable
        onPress={onChangePhoto}
        style={({ pressed }) => [styles.avatarWrap, pressed && styles.pressed]}
        accessibilityRole="button"
        accessibilityLabel="Cambia foto profilo"
        testID="account-avatar"
      >
        <Avatar name={shown} picture={snapshot.picture} size={76} />
        <View style={[styles.avatarBadge, { backgroundColor: colors.surfaceElevated, borderColor: colors.border }]}>
          <Ionicons name="camera-outline" size={13} color={colors.textSecondary} />
        </View>
      </Pressable>

      <View style={styles.identityText}>
        <Text
          style={[styles.identityName, { color: colors.textPrimary }]}
          numberOfLines={2}
          accessibilityRole="header"
          aria-level={2}
        >
          {shown}
        </Text>
        {snapshot.email ? (
          <Text style={[styles.identityMeta, { color: colors.textSecondary }]} numberOfLines={1}>
            {snapshot.email}
          </Text>
        ) : null}
        {member ? (
          <Text style={[styles.identityMeta, { color: colors.textTertiary }]}>{member}</Text>
        ) : null}
      </View>

      <Pressable
        onPress={onChangePhoto}
        disabled={busy}
        style={({ pressed }) => [
          styles.identityCta,
          { borderColor: colors.border, backgroundColor: colors.surfaceElevated },
          (pressed || busy) && styles.pressed,
        ]}
        accessibilityRole="button"
        testID="account-change-photo"
      >
        {busy ? (
          <ActivityIndicator size="small" color={colors.textSecondary} />
        ) : (
          <Text style={[styles.identityCtaLabel, { color: colors.textPrimary }]}>Cambia foto</Text>
        )}
      </Pressable>
    </View>
  );
}

const SECTION_ICONS: Record<string, React.ComponentProps<typeof Ionicons>['name']> = {
  preferences: 'sparkles-outline',
  connections: 'link-outline',
  permissions: 'shield-checkmark-outline',
  privacy: 'lock-closed-outline',
};

export function SectionRow({
  section,
  first,
  onPress,
}: {
  section: Section;
  first?: boolean;
  onPress: () => void;
}) {
  const { colors } = useTheme();
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [
        styles.sectionRow,
        !first && { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.divider },
        pressed && styles.pressed,
      ]}
      accessibilityRole="button"
      accessibilityLabel={section.title}
      testID={`account-section-${section.id}`}
    >
      <View style={[styles.sectionIcon, { backgroundColor: colors.accentMuted }]}>
        <Ionicons name={SECTION_ICONS[section.id] || 'ellipse-outline'} size={18} color={colors.accent} />
      </View>
      <View style={styles.sectionBody}>
        <Text style={[styles.sectionTitle, { color: colors.textPrimary }]}>{section.title}</Text>
        <Text style={[styles.sectionDetail, { color: colors.textSecondary }]} numberOfLines={2}>
          {section.detail}
        </Text>
      </View>
      <Ionicons name="chevron-forward" size={17} color={colors.textTertiary} />
    </Pressable>
  );
}

/* -------------------------------------------------------------------------- */
/* Rail                                                                       */
/* -------------------------------------------------------------------------- */

export function Panel({
  title,
  children,
  testID,
}: {
  title: string;
  children: React.ReactNode;
  testID?: string;
}) {
  const { colors } = useTheme();
  const present = React.Children.toArray(children).filter(Boolean);
  if (!present.length) return null;
  return (
    <View
      style={[styles.panel, { backgroundColor: colors.surface, borderColor: colors.border }]}
      testID={testID}
    >
      <Text style={[styles.panelTitle, { color: colors.textPrimary }]}>{title}</Text>
      {children}
    </View>
  );
}

const SUMMARY_ICONS: Record<string, React.ComponentProps<typeof Ionicons>['name']> = {
  services: 'link-outline',
  access: 'key-outline',
  location: 'location-outline',
};

export function SummaryPanel({ rows }: { rows: SummaryRow[] }) {
  const { colors } = useTheme();
  if (!rows.length) return null;
  return (
    <Panel title="IN SINTESI" testID="account-summary">
      {rows.map((r) => (
        <View key={r.key} style={styles.summaryRow}>
          <Ionicons name={SUMMARY_ICONS[r.key] || 'ellipse-outline'} size={16} color={colors.accent} />
          <Text style={[styles.summaryLabel, { color: colors.textSecondary }]} numberOfLines={1}>
            {r.label}
          </Text>
          <Text style={[styles.summaryValue, { color: colors.textPrimary }]} numberOfLines={1}>
            {r.value}
          </Text>
        </View>
      ))}
    </Panel>
  );
}

/**
 * How you get in.
 *
 * The reference calls its equivalent panel "sicurezza" and fills it with two
 * factor authentication, a last login and a device count. ORA has none of the
 * three. What it does have is the set of ways this account can be opened, and
 * that is the whole of its security surface today.
 */
export function AccessPanel({
  methods,
  onOpen,
}: {
  methods: Array<{ id: string; label: string; linked: boolean }>;
  onOpen: () => void;
}) {
  const { colors } = useTheme();
  if (!methods.length) return null;
  return (
    <Panel title="ACCESSO" testID="account-access-panel">
      {methods.map((m) => (
        <View key={m.id} style={styles.summaryRow}>
          <Ionicons
            name={m.linked ? 'checkmark-circle-outline' : 'ellipse-outline'}
            size={16}
            color={m.linked ? colors.success : colors.textTertiary}
          />
          <Text style={[styles.summaryLabel, { color: colors.textSecondary }]} numberOfLines={1}>
            {m.label}
          </Text>
          <Text
            style={[styles.accessState, { color: m.linked ? colors.textPrimary : colors.textTertiary }]}
          >
            {m.linked ? 'Collegato' : 'Non collegato'}
          </Text>
        </View>
      ))}
      <Pressable
        onPress={onOpen}
        style={({ pressed }) => [styles.panelLink, pressed && styles.pressed]}
        accessibilityRole="button"
        testID="account-access-open"
      >
        <Text style={[styles.panelLinkLabel, { color: colors.accent }]}>Gestisci</Text>
        <Ionicons name="chevron-forward" size={14} color={colors.accent} />
      </Pressable>
    </Panel>
  );
}

/* -------------------------------------------------------------------------- */
/* Logout                                                                     */
/* -------------------------------------------------------------------------- */

/**
 * Leaving.
 *
 * It has to be here and it must not be the loudest thing on the page: signing
 * out is rare, and a red row at eye level in the middle of the account screen
 * makes an ordinary visit feel like a decision.
 */
export function LogoutRow({ onPress, busy }: { onPress: () => void; busy?: boolean }) {
  const { colors } = useTheme();
  return (
    <View style={[styles.logoutWrap, { borderTopColor: colors.divider }]}>
      <Pressable
        onPress={onPress}
        disabled={busy}
        style={({ pressed }) => [styles.logoutBtn, pressed && styles.pressed]}
        accessibilityRole="button"
        testID="profile-logout-button"
      >
        <Ionicons name="log-out-outline" size={17} color={colors.textSecondary} />
        <Text style={[styles.logoutLabel, { color: colors.textSecondary }]}>
          {busy ? 'Esco…' : 'Esci da ORA'}
        </Text>
      </Pressable>
    </View>
  );
}

/* -------------------------------------------------------------------------- */
/* Subpage shell                                                              */
/* -------------------------------------------------------------------------- */

/**
 * Every subpage looks the same: where you are, how to get back, then content.
 *
 * Back goes to the profile when there is no history — a subpage opened from a
 * link should never strand someone on a page with a dead chevron.
 */
export function SubpageShell({
  title,
  subtitle,
  children,
  testID,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  testID?: string;
}) {
  const { colors } = useTheme();
  const router = useRouter();
  return (
    <SafeAreaView
      edges={['top']}
      style={[styles.subpageRoot, { backgroundColor: colors.backgroundPrimary }]}
      testID={testID}
    >
      <ScrollView
        contentContainerStyle={styles.subpageScroll}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.subpageColumn}>
          <Pressable
            onPress={() => {
              haptic('tap');
              if (router.canGoBack()) router.back();
              else router.replace('/(tabs)/profilo' as any);
            }}
            style={({ pressed }) => [styles.backBtn, pressed && styles.pressed]}
            accessibilityRole="button"
            accessibilityLabel="Torna al profilo"
            testID="subpage-back"
          >
            <Ionicons name="chevron-back" size={20} color={colors.textSecondary} />
            <Text style={[styles.backLabel, { color: colors.textSecondary }]}>Profilo</Text>
          </Pressable>

          <Text
            style={[styles.subpageTitle, { color: colors.textPrimary }]}
            accessibilityRole="header"
            aria-level={1}
          >
            {title}
          </Text>
          {subtitle ? (
            <Text style={[styles.subpageSub, { color: colors.textSecondary }]}>{subtitle}</Text>
          ) : null}

          <View style={styles.subpageBody}>{children}</View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

export function SettingCard({
  title,
  detail,
  children,
  testID,
}: {
  title?: string;
  detail?: string;
  children?: React.ReactNode;
  testID?: string;
}) {
  const { colors } = useTheme();
  return (
    <View
      style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}
      testID={testID}
    >
      {title ? (
        <Text style={[styles.cardTitle, { color: colors.textPrimary }]} accessibilityRole="header" aria-level={2}>
          {title}
        </Text>
      ) : null}
      {detail ? <Text style={[styles.cardDetail, { color: colors.textSecondary }]}>{detail}</Text> : null}
      {children}
    </View>
  );
}

export function SectionLabel({ children }: { children: string }) {
  const { colors } = useTheme();
  return <Text style={[styles.groupLabel, { color: colors.textTertiary }]}>{children}</Text>;
}

/** A statement of fact — no control, because there is no control to give. */
export function BoundaryNote({ children, icon = 'shield-checkmark-outline' }: {
  children: string;
  icon?: React.ComponentProps<typeof Ionicons>['name'];
}) {
  const { colors } = useTheme();
  return (
    <View style={styles.boundary}>
      <Ionicons name={icon} size={16} color={colors.accent} />
      <Text style={[styles.boundaryText, { color: colors.textSecondary }]}>{children}</Text>
    </View>
  );
}

/** A closing line of context. Quiet, and never a promise about later. */
export function Footnote({ children }: { children: React.ReactNode }) {
  const { colors } = useTheme();
  return <Text style={[styles.footnote, { color: colors.textTertiary }]}>{children}</Text>;
}

export function ToggleRow({
  label,
  detail,
  value,
  onChange,
  busy,
  testID,
}: {
  label: string;
  detail?: string;
  value: boolean;
  onChange: (v: boolean) => void;
  busy?: boolean;
  testID?: string;
}) {
  const { colors } = useTheme();
  /*
    The row is the control, not the little switch inside it.
    A platform Switch renders about 40×20 on web, which is under the tap floor
    and asks for a precise press on a page that is otherwise all large targets.
    Making the whole row pressable gives a 44px-tall target the width of the
    card, and the switch keeps doing what it is good at — saying which way the
    setting is set. It stops receiving pointer events so a tap on the switch
    itself is handled once, by the row, instead of twice.
  */
  return (
    <Pressable
      onPress={() => !busy && onChange(!value)}
      disabled={busy}
      style={({ pressed }) => [styles.toggleRow, pressed && styles.pressed]}
      accessibilityRole="switch"
      accessibilityState={{ checked: value, disabled: !!busy }}
      accessibilityLabel={label}
      testID={testID}
    >
      <View style={styles.toggleText}>
        <Text style={[styles.toggleLabel, { color: colors.textPrimary }]}>{label}</Text>
        {detail ? (
          <Text style={[styles.toggleDetail, { color: colors.textSecondary }]}>{detail}</Text>
        ) : null}
      </View>
      {busy ? (
        <ActivityIndicator size="small" color={colors.textSecondary} />
      ) : (
        <View pointerEvents="none">
          <Switch
            value={value}
            onValueChange={onChange}
            trackColor={{ false: colors.border, true: colors.accent }}
            thumbColor={colors.surfaceElevated}
            accessibilityElementsHidden
            importantForAccessibility="no-hide-descendants"
            // `thumbColor` only paints the off state on web; without these the
            // switch turns the platform's default teal when it is on, which is
            // the one green in the product that belongs to nothing.
            {...({
              activeThumbColor: colors.surfaceElevated,
              activeTrackColor: colors.accent,
            } as any)}
          />
        </View>
      )}
    </Pressable>
  );
}

export function ChoiceRow({
  label,
  detail,
  selected,
  onPress,
  busy,
  testID,
}: {
  label: string;
  detail?: string;
  selected: boolean;
  onPress: () => void;
  busy?: boolean;
  testID?: string;
}) {
  const { colors } = useTheme();
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [styles.choiceRow, pressed && styles.pressed]}
      accessibilityRole="radio"
      accessibilityState={{ selected }}
      testID={testID}
    >
      <View
        style={[
          styles.radio,
          { borderColor: selected ? colors.accent : colors.border },
          selected && { backgroundColor: colors.accent },
        ]}
      />
      <View style={styles.toggleText}>
        <Text style={[styles.toggleLabel, { color: colors.textPrimary }]}>{label}</Text>
        {detail ? (
          <Text style={[styles.toggleDetail, { color: colors.textSecondary }]}>{detail}</Text>
        ) : null}
      </View>
      {busy ? <ActivityIndicator size="small" color={colors.textSecondary} /> : null}
    </Pressable>
  );
}

/** A row that opens something real. Never rendered without a destination. */
export function LinkRow({
  label,
  detail,
  icon,
  onPress,
  first,
  testID,
}: {
  label: string;
  detail?: string;
  icon?: React.ComponentProps<typeof Ionicons>['name'];
  onPress: () => void;
  first?: boolean;
  testID?: string;
}) {
  const { colors } = useTheme();
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [
        styles.linkRow,
        !first && { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.divider },
        pressed && styles.pressed,
      ]}
      accessibilityRole="button"
      accessibilityLabel={label}
      testID={testID}
    >
      {icon ? <Ionicons name={icon} size={18} color={colors.textSecondary} /> : null}
      <View style={styles.toggleText}>
        <Text style={[styles.toggleLabel, { color: colors.textPrimary }]}>{label}</Text>
        {detail ? (
          <Text style={[styles.toggleDetail, { color: colors.textSecondary }]}>{detail}</Text>
        ) : null}
      </View>
      <Ionicons name="chevron-forward" size={16} color={colors.textTertiary} />
    </Pressable>
  );
}

const STATE_TONE: Record<ConnectionState, 'ok' | 'warn' | 'off'> = {
  connected: 'ok',
  disconnected: 'warn',
  absent: 'off',
};

export function StatusPill({ state }: { state: ConnectionState }) {
  const { colors } = useTheme();
  const tone = STATE_TONE[state];
  const color = tone === 'ok' ? colors.success : tone === 'warn' ? colors.warning : colors.textTertiary;
  return (
    <View style={styles.pill}>
      <View style={[styles.pillDot, { backgroundColor: color }]} />
      <Text style={[styles.pillLabel, { color }]}>{connectionLabel(state)}</Text>
    </View>
  );
}

/* -------------------------------------------------------------------------- */
/* States                                                                     */
/* -------------------------------------------------------------------------- */

export function AccountSkeleton({ wide }: { wide: boolean }) {
  const { colors } = useTheme();
  const box = (h: number) => (
    <View
      style={[
        styles.skBox,
        { backgroundColor: colors.surface, borderColor: colors.border, minHeight: h },
      ]}
    />
  );
  const bar = (w: any, h = 12) => (
    <View style={{ width: w, height: h, borderRadius: 6, backgroundColor: colors.skeleton }} />
  );
  return (
    <View style={styles.skeleton} testID="account-skeleton">
      <View style={styles.skHead}>
        {bar(140, 28)}
        {bar('40%')}
      </View>
      <View style={wide ? styles.skRow : undefined}>
        <View style={[styles.skMain, wide && styles.skFlex]}>
          {box(132)}
          {box(300)}
        </View>
        {wide ? <View style={styles.skRail}>{box(160)}</View> : null}
      </View>
    </View>
  );
}

export function PartialNote({ children }: { children: string }) {
  const { colors } = useTheme();
  return (
    <Text style={[styles.partial, { color: colors.textTertiary }]} testID="account-partial">
      {children}
    </Text>
  );
}

export function InlineError({ children }: { children: string }) {
  const { colors } = useTheme();
  return (
    <Text style={[styles.partial, { color: colors.error }]} testID="account-error">
      {children}
    </Text>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'flex-start', gap: tokens.spacing.lg },
  headerText: { flex: 1, gap: 4 },
  title: { fontSize: 30, fontWeight: '700', letterSpacing: -0.8, lineHeight: 37 },
  sub: { fontSize: 15, lineHeight: 21, maxWidth: 520 },
  whyBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 7,
    borderWidth: StyleSheet.hairlineWidth, borderRadius: tokens.radius.md,
    paddingHorizontal: tokens.spacing.lg, minHeight: tokens.touch.min,
  },
  whyLabel: { fontSize: 13, fontWeight: '500' },

  scrim: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: tokens.spacing.xl },
  dialog: {
    width: 460, maxWidth: '100%',
    borderRadius: tokens.radius.xl, borderWidth: StyleSheet.hairlineWidth,
    padding: tokens.spacing.xl, gap: tokens.spacing.md,
  },
  dialogHead: { flexDirection: 'row', alignItems: 'flex-start', gap: tokens.spacing.md },
  dialogTitle: { fontSize: 19, fontWeight: '700', flex: 1, letterSpacing: -0.3 },
  close: {
    width: tokens.touch.min, height: tokens.touch.min,
    alignItems: 'center', justifyContent: 'center', marginTop: -10, marginRight: -12,
  },
  dialogLine: { fontSize: 14, lineHeight: 21 },

  identity: {
    flexDirection: 'row', alignItems: 'center', gap: tokens.spacing.lg,
    borderRadius: tokens.radius.lg, borderWidth: StyleSheet.hairlineWidth,
    padding: tokens.spacing.xl, flexWrap: 'wrap',
  },
  avatarWrap: { position: 'relative' },
  avatarBadge: {
    position: 'absolute', right: -2, bottom: -2,
    width: 26, height: 26, borderRadius: 13, borderWidth: StyleSheet.hairlineWidth,
    alignItems: 'center', justifyContent: 'center',
  },
  identityText: { flex: 1, minWidth: 160, gap: 3 },
  identityName: { fontSize: 22, fontWeight: '700', letterSpacing: -0.4, lineHeight: 28 },
  identityMeta: { fontSize: 13, lineHeight: 19 },
  identityCta: {
    minHeight: tokens.touch.min, justifyContent: 'center', alignItems: 'center',
    paddingHorizontal: tokens.spacing.lg, borderRadius: tokens.radius.md,
    borderWidth: StyleSheet.hairlineWidth, minWidth: 120,
  },
  identityCtaLabel: { fontSize: 14, fontWeight: '600' },

  sectionRow: {
    flexDirection: 'row', alignItems: 'center', gap: tokens.spacing.md,
    paddingHorizontal: tokens.spacing.lg, paddingVertical: tokens.spacing.md,
    minHeight: 72,
  },
  sectionIcon: {
    width: 38, height: 38, borderRadius: tokens.radius.sm,
    alignItems: 'center', justifyContent: 'center',
  },
  sectionBody: { flex: 1, minWidth: 0, gap: 2 },
  sectionTitle: { fontSize: 15, fontWeight: '600' },
  sectionDetail: { fontSize: 12, lineHeight: 17 },

  panel: {
    borderRadius: tokens.radius.lg, borderWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: tokens.spacing.lg, paddingVertical: tokens.spacing.md, gap: 2,
  },
  panelTitle: {
    fontSize: 11, fontWeight: '700', letterSpacing: 1.1,
    paddingVertical: tokens.spacing.sm,
  },
  summaryRow: { flexDirection: 'row', alignItems: 'center', gap: 10, minHeight: 38 },
  summaryLabel: { fontSize: 13, flex: 1 },
  summaryValue: { fontSize: 15, fontWeight: '700', maxWidth: 140 },
  accessState: { fontSize: 12, fontWeight: '600' },
  panelLink: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    minHeight: tokens.touch.min, marginTop: 2,
  },
  panelLinkLabel: { fontSize: 13, fontWeight: '600' },

  logoutWrap: { borderTopWidth: StyleSheet.hairlineWidth, paddingTop: tokens.spacing.md },
  logoutBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 8, alignSelf: 'flex-start',
    minHeight: tokens.touch.min, paddingHorizontal: tokens.spacing.sm,
  },
  logoutLabel: { fontSize: 14, fontWeight: '500' },

  subpageRoot: { flex: 1 },
  subpageScroll: {
    paddingHorizontal: tokens.spacing.xl,
    paddingTop: tokens.spacing.sm,
    paddingBottom: tokens.spacing.xxxl,
  },
  subpageColumn: { width: '100%', maxWidth: SUBPAGE_MAX_WIDTH, alignSelf: 'center' },
  backBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 2, alignSelf: 'flex-start',
    minHeight: tokens.touch.min, paddingRight: tokens.spacing.md, marginLeft: -6,
  },
  backLabel: { fontSize: 14, fontWeight: '500' },
  subpageTitle: { fontSize: 26, fontWeight: '700', letterSpacing: -0.6, lineHeight: 33, marginTop: 2 },
  subpageSub: { fontSize: 15, lineHeight: 21, marginTop: 4 },
  subpageBody: { gap: tokens.spacing.lg, marginTop: tokens.spacing.xl },

  card: {
    borderRadius: tokens.radius.lg, borderWidth: StyleSheet.hairlineWidth,
    padding: tokens.spacing.lg, gap: 6,
  },
  cardTitle: { fontSize: 16, fontWeight: '650' as any, letterSpacing: -0.2 },
  cardDetail: { fontSize: 13, lineHeight: 19 },
  groupLabel: { fontSize: 11, fontWeight: '700', letterSpacing: 1.1, marginTop: tokens.spacing.sm },

  boundary: { flexDirection: 'row', alignItems: 'flex-start', gap: 9, marginTop: 2 },
  boundaryText: { flex: 1, fontSize: 13, lineHeight: 19 },

  toggleRow: {
    flexDirection: 'row', alignItems: 'center', gap: tokens.spacing.md,
    minHeight: tokens.touch.min, marginTop: 4,
  },
  toggleText: { flex: 1, minWidth: 0, gap: 2 },
  toggleLabel: { fontSize: 14, fontWeight: '600' },
  toggleDetail: { fontSize: 12, lineHeight: 17 },
  choiceRow: {
    flexDirection: 'row', alignItems: 'center', gap: tokens.spacing.md,
    minHeight: tokens.touch.min, paddingVertical: 2,
  },
  radio: { width: 18, height: 18, borderRadius: 9, borderWidth: 2 },
  linkRow: {
    flexDirection: 'row', alignItems: 'center', gap: tokens.spacing.md,
    paddingHorizontal: tokens.spacing.lg, minHeight: 64,
  },

  pill: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  pillDot: { width: 6, height: 6, borderRadius: 3 },
  pillLabel: { fontSize: 12, fontWeight: '600' },

  skeleton: { gap: tokens.spacing.xl },
  skHead: { gap: tokens.spacing.sm },
  skRow: { flexDirection: 'row', gap: tokens.spacing.xl, alignItems: 'flex-start' },
  skMain: { gap: tokens.spacing.lg },
  skFlex: { flex: 1 },
  skRail: { width: ACCOUNT_RAIL_WIDTH, gap: tokens.spacing.lg },
  skBox: { flex: 1, borderRadius: tokens.radius.lg, borderWidth: StyleSheet.hairlineWidth },

  footnote: { fontSize: 13, lineHeight: 19, marginTop: tokens.spacing.sm },
  partial: {
    fontSize: tokens.typography.caption.fontSize,
    lineHeight: tokens.typography.caption.lineHeight,
  },
  pressed: { opacity: 0.75 },
});
