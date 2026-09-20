/**
 * I mattoni condivisi del rebuild V3.21.3.
 *
 * Card, bottoni, badge, bolla d'icona, titolo di sezione. Le cinque superfici
 * ricostruite (Home, Chat, Preparazione, Conosciamoci, Documenti) li usano
 * tutti: una sola forma per ogni cosa, invece di cinque CSS simili.
 */
import type { ComponentProps, ReactNode } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View, type ViewStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { ora, oraShadow, oraType } from '@/src/theme/oraSurface';

type IconName = ComponentProps<typeof Ionicons>['name'];

export function OraCard({
  children,
  style,
  padded = true,
  warm = false,
  testID,
}: {
  children: ReactNode;
  style?: ViewStyle | ViewStyle[];
  padded?: boolean;
  warm?: boolean;
  testID?: string;
}) {
  return (
    <View
      testID={testID}
      style={[
        styles.card,
        oraShadow,
        { backgroundColor: warm ? ora.surfaceWarm : ora.surface },
        padded && styles.cardPad,
        style as any,
      ]}
    >
      {children}
    </View>
  );
}

export type OraButtonKind = 'primary' | 'secondary' | 'quiet' | 'link';

export function OraButton({
  label,
  onPress,
  kind = 'primary',
  icon,
  iconRight,
  disabled,
  busy,
  compact,
  style,
  testID,
  accessibilityLabel,
}: {
  label: string;
  onPress?: () => void;
  kind?: OraButtonKind;
  icon?: IconName;
  iconRight?: IconName;
  disabled?: boolean;
  busy?: boolean;
  compact?: boolean;
  style?: ViewStyle;
  testID?: string;
  accessibilityLabel?: string;
}) {
  const colore =
    kind === 'primary' ? '#FFFFFF' : kind === 'secondary' ? ora.cta : kind === 'link' ? ora.cta : ora.ink;
  return (
    <Pressable
      onPress={disabled || busy ? undefined : onPress}
      accessibilityRole="button"
      accessibilityState={{ disabled: !!disabled, busy: !!busy }}
      accessibilityLabel={accessibilityLabel || label}
      testID={testID}
      style={({ pressed, hovered }: any) => [
        styles.btn,
        compact && styles.btnCompact,
        kind === 'primary' && { backgroundColor: pressed ? ora.ctaPressed : ora.cta },
        kind === 'secondary' && {
          backgroundColor: hovered ? ora.activeBg : ora.surface,
          borderWidth: 1,
          borderColor: ora.ctaSoftBorder,
        },
        kind === 'quiet' && {
          backgroundColor: hovered ? ora.hover : ora.neutralBg,
        },
        kind === 'link' && styles.btnLink,
        (disabled || busy) && { opacity: 0.5 },
        pressed && kind !== 'primary' && { opacity: 0.8 },
        style,
      ]}
    >
      {busy ? <ActivityIndicator size="small" color={colore} /> : null}
      {icon && !busy ? <Ionicons name={icon} size={compact ? 16 : 18} color={colore} /> : null}
      <Text style={[styles.btnText, compact && styles.btnTextCompact, { color: colore }]}>{label}</Text>
      {iconRight ? <Ionicons name={iconRight} size={compact ? 16 : 18} color={colore} /> : null}
    </Pressable>
  );
}

export type OraTone = 'info' | 'success' | 'attention' | 'neutral';

export function OraBadge({ label, tone = 'info', icon }: { label: string; tone?: OraTone; icon?: IconName }) {
  const t = TONES[tone];
  return (
    <View style={[styles.badge, { backgroundColor: t.bg }]}>
      {icon ? <Ionicons name={icon} size={14} color={t.fg} /> : null}
      <Text style={[styles.badgeText, { color: t.fg }]}>{label}</Text>
    </View>
  );
}

const TONES: Record<OraTone, { bg: string; fg: string }> = {
  info: { bg: ora.activeBg, fg: ora.cta },
  success: { bg: ora.successBg, fg: ora.success },
  attention: { bg: ora.attentionBg, fg: ora.attention },
  neutral: { bg: ora.neutralBg, fg: ora.ink2 },
};

export function IconBubble({
  name,
  size = 44,
  tone = 'info',
}: {
  name: IconName;
  size?: number;
  tone?: OraTone;
}) {
  const t = TONES[tone];
  return (
    <View
      style={{
        width: size,
        height: size,
        borderRadius: size / 2,
        backgroundColor: tone === 'info' ? '#EEF3FB' : t.bg,
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <Ionicons name={name} size={Math.round(size * 0.48)} color={tone === 'info' ? ora.deep : t.fg} />
    </View>
  );
}

export function SectionTitle({
  icon,
  title,
  subtitle,
  right,
}: {
  icon?: IconName;
  title: string;
  subtitle?: string;
  right?: ReactNode;
}) {
  return (
    <View style={styles.sectionRow}>
      {icon ? <Ionicons name={icon} size={24} color={ora.deep} style={{ marginTop: 1 }} /> : null}
      <View style={{ flex: 1 }}>
        <Text style={[oraType.section, { color: ora.ink }]} accessibilityRole="header">
          {title}
        </Text>
        {subtitle ? <Text style={[oraType.small, { color: ora.ink3, marginTop: 2 }]}>{subtitle}</Text> : null}
      </View>
      {right}
    </View>
  );
}

/** Un collegamento testuale blu con freccia: «3 da rispondere ›», «Vedi agenda». */
export function OraLink({ label, onPress, chevron = true }: { label: string; onPress?: () => void; chevron?: boolean }) {
  return (
    <Pressable onPress={onPress} accessibilityRole="link" style={styles.link} hitSlop={8}>
      <Text style={[oraType.small, { color: ora.cta, fontWeight: '500' }]}>{label}</Text>
      {chevron ? <Ionicons name="chevron-forward" size={16} color={ora.ink3} /> : null}
    </Pressable>
  );
}

export function Divider() {
  return <View style={{ height: StyleSheet.hairlineWidth, backgroundColor: ora.divider }} />;
}

const styles = StyleSheet.create({
  card: {
    borderRadius: ora.radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: ora.hairline,
  },
  cardPad: { padding: ora.space.card },
  btn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    minHeight: 46,
    paddingHorizontal: 22,
    borderRadius: ora.radius.control,
  },
  btnCompact: { minHeight: 38, paddingHorizontal: 16, gap: 6 },
  btnLink: { paddingHorizontal: 6, minHeight: 36 },
  btnText: { fontSize: 16, fontWeight: '600' },
  btnTextCompact: { fontSize: 14 },
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 12,
    paddingVertical: 5,
    borderRadius: ora.radius.pill,
    alignSelf: 'flex-start',
  },
  badgeText: { fontSize: 13, fontWeight: '500' },
  sectionRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 12 },
  link: { flexDirection: 'row', alignItems: 'center', gap: 4 },
});
