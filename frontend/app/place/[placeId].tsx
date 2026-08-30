/**
 * One place, and what ORA knows about being in it.
 *
 * No map and no coordinates. A person opening this wants to know whether ORA
 * thinks they are here, when it last saw them arrive and leave, and how to
 * make it stop remembering — and none of those questions are answered by a pin
 * on a tile they cannot read anyway.
 *
 * The zone is described, not exposed. "Gestita automaticamente" is the honest
 * summary of a radius nobody asked for; a metre value would invite tuning a
 * number whose consequences are invisible from here.
 */
import { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useFocusEffect, useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';

import { api, PlaceDetail } from '@/src/api/client';
import { PlaceEditor } from '@/src/components/vita/PlaceEditor';
import { invalidatePlace, useRevalidate } from '@/src/lib/revalidate';
import { useTheme } from '@/src/theme/ThemeProvider';
import { formatDuration } from '@/src/utils/duration';
import { tokens } from '@/src/theme/tokens';

function whenLabel(iso?: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  const today = new Date().toDateString() === d.toDateString();
  const time = d.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
  if (today) return `oggi, ${time}`;
  return `${d.toLocaleDateString('it-IT', { day: 'numeric', month: 'short' })}, ${time}`;
}

export default function PlaceDetailScreen() {
  const { placeId } = useLocalSearchParams<{ placeId: string }>();
  const router = useRouter();
  const { colors } = useTheme();
  const [detail, setDetail] = useState<PlaceDetail | null>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [renaming, setRenaming] = useState(false);
  const [relocating, setRelocating] = useState(false);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!placeId) return;
    try {
      const next = await api.placesDetail(String(placeId));
      setDetail(next);
      setDraft(next.place.label);
      setStatus('ready');
    } catch {
      setStatus('error');
    }
  }, [placeId]);

  useEffect(() => {
    void load();
  }, [load]);

  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load]),
  );
  useRevalidate(['presence:current'], () => {
    void load();
  });

  const rename = useCallback(async () => {
    const label = draft.trim();
    if (!label || busy || !placeId) return;
    setBusy(true);
    try {
      await api.placesRename(String(placeId), label);
      setRenaming(false);
      invalidatePlace(String(placeId));
      await load();
    } finally {
      setBusy(false);
    }
  }, [draft, busy, placeId, load]);

  const forgetHistory = useCallback(async () => {
    if (busy || !placeId) return;
    setBusy(true);
    try {
      await api.placesForgetHistory(String(placeId));
      invalidatePlace(String(placeId));
      await load();
    } finally {
      setBusy(false);
    }
  }, [busy, placeId, load]);

  const relocate = useCallback(
    async (result: {
      latitude?: number;
      longitude?: number;
      address?: string;
      locality?: string;
      google_place_id?: string;
      location_source: 'current_position' | 'google_place' | 'map_selection' | 'name_only';
    }) => {
      if (!placeId || result.latitude === undefined || result.longitude === undefined) return;
      await api.placesRelocate(String(placeId), {
        latitude: result.latitude,
        longitude: result.longitude,
        address: result.address,
        locality: result.locality,
        google_place_id: result.google_place_id,
        location_source: result.location_source,
      });
      setRelocating(false);
      invalidatePlace(String(placeId));
      await load();
    },
    [placeId, load],
  );

  const remove = useCallback(async () => {
    if (busy || !placeId) return;
    setBusy(true);
    try {
      await api.placesRemove(String(placeId));
      // Invalidate first, navigate second. The other way round shows Vita its
      // old list for a frame and then corrects it, which reads as a place that
      // briefly came back.
      invalidatePlace(String(placeId));
      router.back();
    } finally {
      setBusy(false);
    }
  }, [busy, placeId, router]);

  const body = () => {
    if (status === 'loading') {
      return (
        <View style={styles.centred} testID="place-detail-loading">
          <ActivityIndicator color={colors.textTertiary} />
        </View>
      );
    }
    if (status === 'error' || !detail) {
      return (
        <Text style={[styles.paragraph, { color: colors.textSecondary }]} testID="place-detail-error">
          Non riesco a caricare questo luogo.
        </Text>
      );
    }

    const { place, presence, zone, recent_sessions: sessions, this_week: week } = detail;
    const here = presence?.present;
    const current = formatDuration(presence?.current_session_seconds);

    return (
      <>
        <View style={styles.head}>
          <Text style={[styles.title, { color: colors.textPrimary }]}>{place.label}</Text>
          {place.locality ? (
            <Text style={[styles.subtitle, { color: colors.textTertiary }]}>{place.locality}</Text>
          ) : null}
        </View>

        <Row label="Stato" colors={colors}>
          <Badge
            text={place.state === 'confirmed' ? 'Confermato' : 'Da confermare'}
            tone={place.state === 'confirmed' ? 'ok' : 'warn'}
            colors={colors}
          />
        </Row>

        <Row label="Presenza" colors={colors} testID="place-detail-presence">
          <Text style={[styles.value, { color: here ? colors.success : colors.textSecondary }]}>
            {here ? (current ? `Sei qui da ${current}` : 'Sei qui') : 'Non sei qui'}
          </Text>
        </Row>

        <Row label="Ultimo ingresso" colors={colors}>
          <Text style={[styles.value, { color: colors.textSecondary }]}>
            {whenLabel(presence?.last_entered_at)}
          </Text>
        </Row>

        <Row label="Ultima uscita" colors={colors}>
          <Text style={[styles.value, { color: colors.textSecondary }]}>
            {whenLabel(presence?.last_exited_at)}
          </Text>
        </Row>

        <Row label="Zona di presenza" colors={colors}>
          <Text style={[styles.value, { color: colors.textSecondary }]}>
            {zone?.managed ? 'Gestita automaticamente' : 'Impostata da te'}
          </Text>
        </Row>

        {week && week.visits ? (
          <View style={styles.block} testID="place-detail-week">
            <Text style={[styles.blockLabel, { color: colors.textTertiary }]}>
              QUESTA SETTIMANA
            </Text>
            {/* Two numbers. A place somebody has to study a chart to
                understand is not being shown to them, it is being analysed
                at them. */}
            <Text style={[styles.value, { color: colors.textSecondary }]}>
              {week.visits === 1 ? '1 visita' : `${week.visits} visite`}
              {formatDuration(week.total_seconds) ? ` · ${formatDuration(week.total_seconds)}` : ''}
              {week.still_there ? ' · finora' : ''}
            </Text>
          </View>
        ) : null}

        {sessions.length ? (
          <View style={styles.block}>
            <Text style={[styles.blockLabel, { color: colors.textTertiary }]}>
              PRESENZE RECENTI
            </Text>
            {sessions.slice(0, 5).map((s) => (
              <View key={s.id} style={[styles.session, { borderColor: colors.divider }]}>
                <Text style={[styles.value, { color: colors.textSecondary }]}>
                  {whenLabel(s.entered_at)} → {s.open ? 'in corso' : whenLabel(s.exited_at)}
                </Text>
                {formatDuration(s.duration_seconds) ? (
                  <Text style={[styles.meta, { color: colors.textTertiary }]}>
                    {formatDuration(s.duration_seconds)}
                  </Text>
                ) : null}
              </View>
            ))}
          </View>
        ) : null}

        <View style={styles.block}>
          <Text style={[styles.blockLabel, { color: colors.textTertiary }]}>AZIONI</Text>
          {renaming ? (
            <View style={styles.renameRow}>
              <TextInput
                value={draft}
                onChangeText={setDraft}
                style={[styles.input, { color: colors.textPrimary, borderColor: colors.border }]}
                testID="place-rename-input"
                editable={!busy}
              />
              <Pressable
                onPress={() => void rename()}
                disabled={busy || !draft.trim()}
                style={[styles.primary, { backgroundColor: colors.accent, opacity: busy ? 0.5 : 1 }]}
                testID="place-rename-save"
              >
                <Text style={[styles.primaryText, { color: colors.onAccent }]}>Salva</Text>
              </Pressable>
            </View>
          ) : (
            <Action label="Rinomina" icon="create-outline" colors={colors} onPress={() => setRenaming(true)} testID="place-action-rename" />
          )}
          {relocating ? (
            // The same editor that created it. A place corrected six months
            // later goes through exactly the path that made it.
            <PlaceEditor
              mode="relocate"
              initialLabel={place.label}
              initialPoint={null}
              onCancel={() => setRelocating(false)}
              onSave={relocate}
            />
          ) : (
            <Action
              label="Modifica posizione"
              icon="location-outline"
              colors={colors}
              onPress={() => setRelocating(true)}
              testID="place-action-relocate"
            />
          )}
          <Action
            label="Dimentica la cronologia"
            icon="time-outline"
            colors={colors}
            onPress={() => void forgetHistory()}
            testID="place-action-forget"
          />
          <Action
            label="Rimuovi luogo"
            icon="trash-outline"
            colors={colors}
            destructive
            onPress={() => void remove()}
            testID="place-action-remove"
          />
        </View>
      </>
    );
  };

  return (
    <SafeAreaView
      edges={['top']}
      style={[styles.root, { backgroundColor: colors.backgroundPrimary }]}
      testID="place-detail-screen"
    >
      <View style={styles.bar}>
        <Pressable onPress={() => router.back()} hitSlop={8} testID="place-detail-back">
          <Ionicons name="chevron-back" size={22} color={colors.textPrimary} />
        </Pressable>
        <Text style={[styles.barTitle, { color: colors.textPrimary }]}>Luogo</Text>
      </View>
      <ScrollView contentContainerStyle={styles.content}>{body()}</ScrollView>
    </SafeAreaView>
  );
}

function Row({
  label,
  children,
  colors,
  testID,
}: {
  label: string;
  children: React.ReactNode;
  colors: ReturnType<typeof useTheme>['colors'];
  testID?: string;
}) {
  return (
    <View style={[styles.row, { borderColor: colors.divider }]} testID={testID}>
      <Text style={[styles.rowLabel, { color: colors.textTertiary }]}>{label}</Text>
      <View style={styles.rowValue}>{children}</View>
    </View>
  );
}

function Badge({
  text,
  tone,
  colors,
}: {
  text: string;
  tone: 'ok' | 'warn';
  colors: ReturnType<typeof useTheme>['colors'];
}) {
  return (
    <View
      style={[
        styles.badge,
        { backgroundColor: tone === 'ok' ? colors.successBg : colors.warningBg },
      ]}
    >
      <Text style={[styles.badgeText, { color: tone === 'ok' ? colors.success : colors.warning }]}>
        {text}
      </Text>
    </View>
  );
}

function Action({
  label,
  icon,
  colors,
  onPress,
  destructive,
  testID,
}: {
  label: string;
  icon: keyof typeof Ionicons.glyphMap;
  colors: ReturnType<typeof useTheme>['colors'];
  onPress: () => void;
  destructive?: boolean;
  testID?: string;
}) {
  return (
    <Pressable
      onPress={onPress}
      style={[styles.action, { borderColor: colors.divider }]}
      testID={testID}
    >
      <Ionicons
        name={icon}
        size={16}
        color={destructive ? colors.warning : colors.textSecondary}
      />
      <Text
        style={[
          styles.actionText,
          { color: destructive ? colors.warning : colors.textPrimary },
        ]}
      >
        {label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  bar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: tokens.spacing.md,
    paddingHorizontal: tokens.spacing.lg,
    paddingVertical: tokens.spacing.md,
  },
  barTitle: { fontSize: 15, fontWeight: '600' },
  content: {
    paddingHorizontal: tokens.spacing.lg,
    paddingBottom: tokens.spacing.xxl,
    gap: tokens.spacing.md,
    maxWidth: 720,
    width: '100%',
    alignSelf: 'center',
  },
  centred: { paddingVertical: tokens.spacing.xxl, alignItems: 'center' },
  head: { gap: 2, paddingBottom: tokens.spacing.md },
  title: { fontSize: 24, fontWeight: '600' },
  subtitle: { fontSize: 13 },
  paragraph: { fontSize: 14, lineHeight: 20 },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: tokens.spacing.md,
    borderTopWidth: StyleSheet.hairlineWidth,
    paddingVertical: tokens.spacing.md,
    minHeight: tokens.touch.min,
  },
  rowLabel: { fontSize: 13 },
  rowValue: { flexShrink: 1, alignItems: 'flex-end' },
  value: { fontSize: 14, fontWeight: '500' },
  meta: { fontSize: 12 },
  badge: { borderRadius: tokens.radius.sm, paddingHorizontal: 8, paddingVertical: 3 },
  badgeText: { fontSize: 11, fontWeight: '600' },
  block: { gap: tokens.spacing.sm, paddingTop: tokens.spacing.lg },
  blockLabel: { fontSize: 11, fontWeight: '600', letterSpacing: 0.6 },
  session: {
    borderTopWidth: StyleSheet.hairlineWidth,
    paddingVertical: tokens.spacing.md,
    gap: 2,
  },
  action: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: tokens.spacing.md,
    borderTopWidth: StyleSheet.hairlineWidth,
    paddingVertical: tokens.spacing.md,
    minHeight: tokens.touch.min,
  },
  actionText: { fontSize: 14 },
  renameRow: { flexDirection: 'row', gap: tokens.spacing.md, alignItems: 'center' },
  input: {
    flex: 1,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.sm,
    paddingHorizontal: tokens.spacing.md,
    paddingVertical: 10,
    fontSize: 14,
    minHeight: tokens.touch.min,
  },
  primary: {
    borderRadius: tokens.radius.md,
    paddingHorizontal: tokens.spacing.lg,
    justifyContent: 'center',
    minHeight: tokens.touch.min,
  },
  primaryText: { fontSize: 13, fontWeight: '600' },
});
