import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, AppState, Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';

import { api, type HomeV2Response } from '@/src/api/client';
import { presencePalette as palette, presenceColors } from '@/src/theme/presence';
import { tokens } from '@/src/theme/tokens';
import { useTemporaryMemory } from './presence/useTemporaryMemory';
import type { KnowledgeStar } from './presence/knowledge';
import { firstSituationState, situationIcon, situationTitle } from './situationVisual';

function timeLabel(iso?: string | null): string {
  if (!iso) return 'Poco fa';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return 'Poco fa';
  return d.toLocaleString('it-IT', {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function DetailRow({
  icon,
  title,
  body,
  danger = false,
}: {
  icon: any;
  title: string;
  body: string;
  danger?: boolean;
}) {
  return (
    <View style={styles.detailRow}>
      <View style={[styles.detailIcon, danger && styles.detailIconDanger]}>
        <Ionicons name={icon} size={19} color={danger ? '#ff7373' : palette.label} />
      </View>
      <View style={styles.detailBody}>
        <Text style={styles.detailLabel}>{title}</Text>
        <Text style={[styles.detailText, danger && styles.detailTextDanger]}>{body}</Text>
      </View>
    </View>
  );
}

export function OraCockpitContext({
  refreshKey,
  selectedStarId,
  onTemporaryChanged,
  star,
  standalone = false,
  readError = false,
}: {
  refreshKey?: unknown;
  selectedStarId?: string | null;
  onTemporaryChanged?: () => void;
  /** A selected map snapshot; never fall back to some other/latest star. */
  star?: KnowledgeStar | null;
  standalone?: boolean;
  readError?: boolean;
}) {
  const router = useRouter();
  const [home, setHome] = useState<HomeV2Response | null>(null);
  const [removing, setRemoving] = useState(false);
  const [removeError, setRemoveError] = useState('');
  const temporary = useTemporaryMemory(star === undefined, refreshKey);

  const refresh = useCallback(async () => {
    const next = await api.getHome().catch(() => null);
    if (next) setHome(next);
    await temporary.refresh();
  }, [temporary.refresh]);

  useEffect(() => {
    if (standalone) return;
    void refresh();
    const timer = setInterval(() => {
      if (AppState.currentState === 'active') void refresh();
    }, 30000);
    const app = AppState.addEventListener('change', state => {
      if (state === 'active') void refresh();
    });
    return () => { clearInterval(timer); app.remove(); };
  }, [refresh, refreshKey, standalone]);

  const current = star !== undefined
    ? star
    : temporary.stars.find(item => item.id === selectedStarId) || temporary.latest;
  const focus = home?.primary_focus || null;
  const currentState = firstSituationState(current);
  const followup = current?.follow_up;
  const followupStatus: Record<string, string> = {
    scheduled: 'Controllo programmato', due: 'Controllo in scadenza', running: 'Controllo in corso',
    not_scheduled: 'Nessun controllo programmato', recovery_pending: 'Programmazione da recuperare',
    waiting_for_user: 'In attesa di informazioni o autorizzazione', runtime_disabled: 'Controlli automatici disattivati',
    stopped: 'Controllo terminato', unavailable: 'Stato del controllo non verificabile',
  };

  const removeCurrent = useCallback(async () => {
    if (!current?.situation_id || removing) return;
    setRemoving(true);
    setRemoveError('');
    try {
      const result = await api.dismissTemporarySituation(current.situation_id);
      if (!result.ok) throw new Error('dismiss_not_confirmed');
      await temporary.refresh();
      onTemporaryChanged?.();
    } catch {
      setRemoveError('Non sono riuscita a rimuovere questa situazione. Aggiorna e riprova.');
    } finally {
      setRemoving(false);
    }
  }, [current?.situation_id, removing, temporary.refresh, onTemporaryChanged]);

  return (
    <View style={styles.rail} testID="ora-cockpit-context">
      {current ? (
        <View style={styles.primaryCard} testID="ora-cockpit-temporary">
          <View style={styles.primaryHead}>
            <View style={styles.tempOrb}>
              <Ionicons name={situationIcon(current.icon_key)} size={24} color="#ff7373" />
            </View>
            <View style={styles.primaryTitleCol}>
              <Text style={styles.primaryTitle}>{situationTitle(current).toUpperCase()}</Text>
              <Text style={styles.primarySubtitle}>Memoria temporanea</Text>
            </View>
            {temporary.count > 1 ? (
              <View style={styles.countPill}>
                <Text style={styles.countText}>+{temporary.count - 1}</Text>
              </View>
            ) : null}
          </View>

          <Text style={styles.situationStatement}>{current.statement}</Text>
          {readError ? <Text accessibilityRole="alert" style={styles.removeError}>
            Aggiornamento non riuscito: i dati mostrati sono quelli dell'ultima lettura.
          </Text> : null}

          <View style={styles.divider} />
          <DetailRow
            icon="time-outline"
            title="Inserita"
            body={timeLabel(current.created_at || current.updated_at)}
          />

          {current.location_label ? (
            <>
              <View style={styles.divider} />
              <DetailRow icon="location-outline" title="Luogo" body={current.location_label} />
            </>
          ) : null}

          {currentState ? (
            <>
              <View style={styles.divider} />
              <DetailRow
                icon="pulse-outline"
                title="Stato attuale"
                body={currentState}
                danger={/rischio|allert|urgente|pericolo|piogg|ritir|interven/i.test(currentState)}
              />
            </>
          ) : null}

          {current.expected_outcome_summary ? (
            <>
              <View style={styles.divider} />
              <DetailRow
                icon="time-outline"
                title="Stima / esito atteso"
                body={current.expected_outcome_summary}
              />
            </>
          ) : null}

          <View style={styles.divider} />
          <DetailRow icon="eye-outline" title="Stato del controllo"
            body={followupStatus[followup?.status || 'unavailable'] || followupStatus.unavailable} />
          {followup?.next_check_at ? <>
            <View style={styles.divider} />
            <DetailRow icon="time-outline" title="Prossimo controllo" body={timeLabel(followup.next_check_at)} />
          </> : null}
          {followup?.last_checked_at ? <>
            <View style={styles.divider} />
            <DetailRow icon="checkmark-circle-outline" title="Ultimo controllo eseguito" body={timeLabel(followup.last_checked_at)} />
          </> : null}
          {followup?.completion_when ? <>
            <View style={styles.divider} />
            <DetailRow icon="checkmark-done-outline" title="Ti avviso quando" body={followup.completion_when} />
          </> : null}
          {followup?.notify_when ? <>
            <View style={styles.divider} />
            <DetailRow icon="warning-outline" title="Ti avviso prima se" body={followup.notify_when} />
          </> : null}

          {!standalone ? <Pressable
            onPress={() => router.push('/situazione' as any)}
            accessibilityRole="button"
            style={({ pressed }) => [styles.primaryAction, pressed && styles.pressed]}
          >
            <Text style={styles.primaryActionText}>Apri situazione</Text>
            <Ionicons name="arrow-forward" size={16} color={palette.label} />
          </Pressable> : null}

          <Pressable
            onPress={() => void removeCurrent()}
            accessibilityRole="button"
            accessibilityLabel="Rimuovi dalla memoria temporanea"
            disabled={removing || !current.situation_id}
            style={({ pressed }) => [styles.removeAction, pressed && styles.pressed, removing && styles.disabled]}
            testID="ora-remove-temporary"
          >
            {removing ? <ActivityIndicator size="small" color="#ff8f8f" /> : <Ionicons name="trash-outline" size={17} color="#ff8f8f" />}
            <Text style={styles.removeText}>Rimuovi dalla memoria temporanea</Text>
          </Pressable>
          {removeError ? <Text style={styles.removeError}>{removeError}</Text> : null}
        </View>
      ) : (
        <View style={styles.emptyCard}>
          <View style={styles.primaryHead}>
            <View style={styles.calmOrb}>
              <Ionicons name="sparkles-outline" size={19} color={palette.label} />
            </View>
            <View style={styles.primaryTitleCol}>
              <Text style={styles.cardLabel}>NESSUNA SITUAZIONE TEMPORANEA</Text>
              <Text style={styles.primarySubtitle}>La mappa non ha stati momentanei aperti.</Text>
            </View>
          </View>
        </View>
      )}

      {!standalone && focus ? (
        <View style={styles.secondaryCard}>
          <View style={styles.secondaryHead}>
            <Ionicons name="locate-outline" size={17} color={palette.label} />
            <Text style={styles.cardLabel}>COSA CONTA ORA</Text>
          </View>
          <Text style={styles.secondaryTitle}>{focus.title}</Text>
          {focus.subtitle || focus.description ? (
            <Text style={styles.secondaryText} numberOfLines={3}>
              {focus.subtitle || focus.description}
            </Text>
          ) : null}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  rail: { width: '100%', gap: 12 },
  primaryCard: {
    borderWidth: 1, borderColor: 'rgba(255,92,92,.48)', borderRadius: 20,
    backgroundColor: 'rgba(28,7,13,.68)', overflow: 'hidden', padding: 18, gap: 13,
  },
  emptyCard: {
    borderWidth: StyleSheet.hairlineWidth, borderColor: palette.border, borderRadius: 18,
    backgroundColor: 'rgba(12,21,30,.64)', padding: 16,
  },
  primaryHead: { flexDirection: 'row', alignItems: 'center', gap: 11 },
  tempOrb: {
    width: 48, height: 48, borderRadius: 24, borderWidth: 1,
    borderColor: 'rgba(255,92,92,.68)', backgroundColor: 'rgba(255,92,92,.08)',
    alignItems: 'center', justifyContent: 'center',
    shadowColor: '#ff5252', shadowOpacity: .55, shadowRadius: 14,
  },
  calmOrb: {
    width: 38, height: 38, borderRadius: 19, borderWidth: 1,
    borderColor: 'rgba(143,213,233,.34)', backgroundColor: 'rgba(143,213,233,.05)',
    alignItems: 'center', justifyContent: 'center',
  },
  primaryTitleCol: { flex: 1, gap: 2 },
  primaryTitle: { color: '#ff7373', fontSize: 14, letterSpacing: 1, fontWeight: '850' as any },
  primarySubtitle: { color: palette.muted, fontSize: 12, lineHeight: 17 },
  countPill: {
    minWidth: 30, height: 30, borderRadius: 15, alignItems: 'center', justifyContent: 'center',
    backgroundColor: 'rgba(255,92,92,.12)', borderWidth: StyleSheet.hairlineWidth,
    borderColor: 'rgba(255,92,92,.38)',
  },
  countText: { color: '#ff9191', fontSize: 11, fontWeight: '700' },
  situationStatement: {
    color: presenceColors.textPrimary, fontSize: 15, lineHeight: 21, fontWeight: '650' as any,
  },
  divider: { height: StyleSheet.hairlineWidth, backgroundColor: 'rgba(144,190,207,.15)' },
  detailRow: { flexDirection: 'row', gap: 10, alignItems: 'flex-start' },
  detailIcon: {
    width: 32, height: 32, borderRadius: 16, alignItems: 'center', justifyContent: 'center',
    backgroundColor: 'rgba(116,200,226,.06)',
  },
  detailIconDanger: { backgroundColor: 'rgba(255,92,92,.08)' },
  detailBody: { flex: 1, gap: 2 },
  detailLabel: { color: '#95bcca', fontSize: 11, fontWeight: '650' as any },
  detailText: { color: presenceColors.textSecondary, fontSize: 12, lineHeight: 17 },
  detailTextDanger: { color: '#ff9b9b' },
  primaryAction: {
    minHeight: 44, paddingHorizontal: 14, borderRadius: 12,
    borderWidth: StyleSheet.hairlineWidth, borderColor: 'rgba(143,213,233,.22)',
    backgroundColor: 'rgba(143,213,233,.07)', flexDirection: 'row',
    alignItems: 'center', justifyContent: 'space-between',
  },
  primaryActionText: { color: palette.label, fontSize: 12, fontWeight: '700' },
  removeAction: {
    minHeight: 46, paddingHorizontal: 14, borderRadius: 12, borderWidth: 1,
    borderColor: 'rgba(255,92,92,.42)', backgroundColor: 'rgba(255,50,65,.07)',
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
  },
  removeText: { color: '#ff8f8f', fontSize: 12, fontWeight: '700' },
  removeError: { color: '#ff9b9b', fontSize: 11, lineHeight: 16 },
  disabled: { opacity: .55 },
  secondaryCard: {
    gap: 9, padding: 15, borderWidth: StyleSheet.hairlineWidth, borderColor: palette.border,
    borderRadius: 18, backgroundColor: 'rgba(12,21,30,.64)',
  },
  secondaryHead: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  cardLabel: { color: '#afd7e2', fontSize: 10, letterSpacing: 1.2, fontWeight: '800' },
  secondaryTitle: { color: presenceColors.textPrimary, fontSize: 14, lineHeight: 19, fontWeight: '650' as any },
  secondaryText: { color: presenceColors.textSecondary, fontSize: 12, lineHeight: 18 },
  pressed: { opacity: .7 },
});
