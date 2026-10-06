import { useCallback, useEffect, useState } from 'react';
import { AppState, Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';

import { api, type HomeV2Response } from '@/src/api/client';
import { presencePalette as palette, presenceColors } from '@/src/theme/presence';
import { tokens } from '@/src/theme/tokens';
import { useTemporaryMemory } from './presence/useTemporaryMemory';

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
        <Ionicons name={icon} size={18} color={danger ? '#ff7373' : palette.label} />
      </View>
      <View style={styles.detailBody}>
        <Text style={styles.detailLabel}>{title}</Text>
        <Text style={[styles.detailText, danger && styles.detailTextDanger]}>{body}</Text>
      </View>
    </View>
  );
}

export function OraCockpitContext() {
  const router = useRouter();
  const [home, setHome] = useState<HomeV2Response | null>(null);
  const temporary = useTemporaryMemory(true);

  const refresh = useCallback(async () => {
    const next = await api.getHome().catch(() => null);
    if (next) setHome(next);
    await temporary.refresh();
  }, [temporary.refresh]);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => {
      if (AppState.currentState === 'active') void refresh();
    }, 30000);
    const app = AppState.addEventListener('change', state => {
      if (state === 'active') void refresh();
    });
    return () => { clearInterval(timer); app.remove(); };
  }, [refresh]);

  const current = temporary.latest;
  const focus = home?.primary_focus || null;
  const situation = home?.current_situation || null;
  const weather = home?.weather?.available ? home.weather : null;

  return (
    <View style={styles.rail} testID="ora-cockpit-context">
      <View style={styles.railHead}>
        <View style={styles.liveDot} />
        <Text style={styles.eyebrow}>ORA · CONTESTO</Text>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Aggiorna contesto"
          onPress={() => void refresh()}
          style={({ pressed }) => [styles.refresh, pressed && styles.pressed]}
        >
          <Ionicons name="refresh-outline" size={16} color={palette.label} />
        </Pressable>
      </View>

      {current ? (
        <View style={styles.primaryCard} testID="ora-cockpit-temporary">
          <View style={styles.primaryHead}>
            <View style={styles.tempOrb}>
              <Ionicons name="flash-outline" size={20} color="#ff7373" />
            </View>
            <View style={styles.primaryTitleCol}>
              <Text style={styles.primaryTitle}>SITUAZIONE ATTIVA</Text>
              <Text style={styles.primarySubtitle}>Memoria temporanea</Text>
            </View>
            {temporary.count > 1 ? (
              <View style={styles.countPill}>
                <Text style={styles.countText}>+{temporary.count - 1}</Text>
              </View>
            ) : null}
          </View>

          <Text style={styles.situationStatement}>{current.statement}</Text>

          <View style={styles.divider} />
          <DetailRow
            icon="time-outline"
            title="Inserita"
            body={timeLabel(current.updated_at)}
          />
          {weather ? (
            <>
              <View style={styles.divider} />
              <DetailRow
                icon="rainy-outline"
                title="Stato live"
                body={[
                  weather.label,
                  typeof weather.temperature_c === 'number' ? `${weather.temperature_c}°C` : null,
                  weather.place,
                ].filter(Boolean).join(' · ')}
                danger={/piogg|tempor|allert/i.test(String(weather.label || ''))}
              />
            </>
          ) : null}
          <View style={styles.divider} />
          <DetailRow
            icon="notifications-outline"
            title="Monitoraggio"
            body="Attivo. ORA continua a rivalutare la situazione finché resta aperta."
          />

          <Pressable
            onPress={() => router.push('/situazione' as any)}
            accessibilityRole="button"
            style={({ pressed }) => [styles.primaryAction, pressed && styles.pressed]}
          >
            <Text style={styles.primaryActionText}>Apri situazione</Text>
            <Ionicons name="arrow-forward" size={16} color={palette.label} />
          </Pressable>
        </View>
      ) : (
        <View style={styles.primaryCard}>
          <View style={styles.primaryHead}>
            <View style={styles.calmOrb}>
              <Ionicons name="sparkles-outline" size={19} color={palette.label} />
            </View>
            <View style={styles.primaryTitleCol}>
              <Text style={styles.cardLabel}>NESSUNA MEMORIA TEMPORANEA</Text>
              <Text style={styles.primarySubtitle}>ORA non ha situazioni momentanee aperte.</Text>
            </View>
          </View>
        </View>
      )}

      {focus ? (
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

      {situation?.next_commitment && !current ? (
        <View style={styles.secondaryCard}>
          <View style={styles.secondaryHead}>
            <Ionicons name="time-outline" size={17} color={palette.label} />
            <Text style={styles.cardLabel}>PROSSIMO PASSO</Text>
          </View>
          <Text style={styles.secondaryText}>{String(situation.next_commitment)}</Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  rail: {
    width: '100%',
    gap: 12,
  },
  railHead: {
    minHeight: 42,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingHorizontal: 4,
  },
  liveDot: {
    width: 7,
    height: 7,
    borderRadius: 4,
    backgroundColor: palette.label,
    shadowColor: palette.label,
    shadowOpacity: 0.9,
    shadowRadius: 8,
  },
  eyebrow: {
    flex: 1,
    color: '#b6dce7',
    fontSize: 11,
    letterSpacing: 1.7,
    fontWeight: '800',
  },
  refresh: {
    width: tokens.touch.min,
    height: tokens.touch.min,
    borderRadius: tokens.touch.min / 2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  primaryCard: {
    borderWidth: 1,
    borderColor: 'rgba(255,92,92,.48)',
    borderRadius: 20,
    backgroundColor: 'rgba(28,7,13,.68)',
    overflow: 'hidden',
    padding: 18,
    gap: 13,
  },
  primaryHead: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 11,
  },
  tempOrb: {
    width: 42,
    height: 42,
    borderRadius: 21,
    borderWidth: 1,
    borderColor: 'rgba(255,92,92,.68)',
    backgroundColor: 'rgba(255,92,92,.08)',
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#ff5252',
    shadowOpacity: 0.5,
    shadowRadius: 12,
  },
  calmOrb: {
    width: 38,
    height: 38,
    borderRadius: 19,
    borderWidth: 1,
    borderColor: 'rgba(143,213,233,.34)',
    backgroundColor: 'rgba(143,213,233,.05)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  primaryTitleCol: { flex: 1, gap: 2 },
  primaryTitle: {
    color: '#ff7373',
    fontSize: 13,
    letterSpacing: 1.1,
    fontWeight: '850' as any,
  },
  primarySubtitle: {
    color: palette.muted,
    fontSize: 12,
    lineHeight: 17,
  },
  countPill: {
    minWidth: 30,
    height: 30,
    borderRadius: 15,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(255,92,92,.12)',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: 'rgba(255,92,92,.38)',
  },
  countText: {
    color: '#ff9191',
    fontSize: 11,
    fontWeight: '700',
  },
  situationStatement: {
    color: presenceColors.textPrimary,
    fontSize: 15,
    lineHeight: 21,
    fontWeight: '650' as any,
  },
  divider: {
    height: StyleSheet.hairlineWidth,
    backgroundColor: 'rgba(144,190,207,.15)',
  },
  detailRow: {
    flexDirection: 'row',
    gap: 10,
    alignItems: 'flex-start',
  },
  detailIcon: {
    width: 30,
    height: 30,
    borderRadius: 15,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(116,200,226,.06)',
  },
  detailIconDanger: {
    backgroundColor: 'rgba(255,92,92,.08)',
  },
  detailBody: { flex: 1, gap: 2 },
  detailLabel: {
    color: '#95bcca',
    fontSize: 11,
    fontWeight: '650' as any,
  },
  detailText: {
    color: presenceColors.textSecondary,
    fontSize: 12,
    lineHeight: 17,
  },
  detailTextDanger: {
    color: '#ff9b9b',
  },
  primaryAction: {
    minHeight: 44,
    marginTop: 2,
    paddingHorizontal: 14,
    borderRadius: 12,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: 'rgba(143,213,233,.22)',
    backgroundColor: 'rgba(143,213,233,.07)',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  primaryActionText: {
    color: palette.label,
    fontSize: 12,
    fontWeight: '700',
  },
  secondaryCard: {
    gap: 9,
    padding: 15,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: palette.border,
    borderRadius: 18,
    backgroundColor: 'rgba(12,21,30,.64)',
  },
  secondaryHead: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  cardLabel: {
    color: '#afd7e2',
    fontSize: 10,
    letterSpacing: 1.2,
    fontWeight: '800',
  },
  secondaryTitle: {
    color: presenceColors.textPrimary,
    fontSize: 14,
    lineHeight: 19,
    fontWeight: '650' as any,
  },
  secondaryText: {
    color: presenceColors.textSecondary,
    fontSize: 12,
    lineHeight: 18,
  },
  pressed: { opacity: 0.7 },
});
