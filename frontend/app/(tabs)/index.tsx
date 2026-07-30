import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, ActivityIndicator,
  RefreshControl, Modal, TextInput, Platform, Dimensions,
} from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import Animated, {
  FadeInDown, FadeIn, FadeOut, SlideInDown, LinearTransition,
} from 'react-native-reanimated';
import { Ionicons } from '@expo/vector-icons';

import { tokens } from '@/src/theme/tokens';
import { api, ApiDecision, DecisionExplanation, DailySummary } from '@/src/api/client';
import {
  ruleLabel, CONFIDENCE_LABELS, RISK_LABELS, IMPACT_LABELS, STATUS_LABELS,
  USER_ACTION_LABELS, DAILY_SIGNAL_LABELS, DAILY_WARNING_LABELS,
  DAILY_OPPORTUNITY_LABELS, ENERGY_LABELS, formatMinutes, formatDateTime, formatTime,
  formatRelativeAgo,
} from '@/src/utils/labels';
import { haptic } from '@/src/utils/haptic';
import { useOnlineStatus, isNetworkError } from '@/src/hooks/use-online-status';
import { FocusSkeleton, DailySkeleton, LaterSkeleton } from '@/src/components/Skeleton';

type Flags = { explain: boolean; action: boolean; daily: boolean };

function riskColor(v?: string) {
  if (v === 'high') return tokens.color.error;
  if (v === 'medium') return tokens.color.warning;
  return tokens.color.success;
}
function riskBg(v?: string) {
  if (v === 'high') return tokens.color.errorBg;
  if (v === 'medium') return tokens.color.warningBg;
  return tokens.color.successBg;
}

async function safe<T>(fn: () => Promise<T>): Promise<{ data?: T; error?: any; status?: number }> {
  try {
    const data = await fn();
    return { data };
  } catch (e: any) {
    return { error: e, status: e?.status };
  }
}

export default function HomeScreen() {
  const insets = useSafeAreaInsets();
  const [decisions, setDecisions] = useState<ApiDecision[]>([]);
  const [explanation, setExplanation] = useState<DecisionExplanation | null>(null);
  const [daily, setDaily] = useState<DailySummary | null>(null);
  const [calendarConnected, setCalendarConnected] = useState<boolean | null>(null);
  const [calendarSynced, setCalendarSynced] = useState<boolean>(false);
  const [flags, setFlags] = useState<Flags>({ explain: true, action: true, daily: true });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastSuccessAt, setLastSuccessAt] = useState<Date | null>(null);
  const [, setTick] = useState(0); // triggers relative-time refresh
  const [whyOpen, setWhyOpen] = useState(false);
  const [dailyDetailOpen, setDailyDetailOpen] = useState(false);
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const [errorBanner, setErrorBanner] = useState<string | null>(null);
  const [postponeOpen, setPostponeOpen] = useState(false);
  const [partialOpen, setPartialOpen] = useState(false);
  const [blockOpen, setBlockOpen] = useState(false);
  const [dismissOpen, setDismissOpen] = useState(false);
  const [confirmCompleteOpen, setConfirmCompleteOpen] = useState(false);
  const [moreMenuOpen, setMoreMenuOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [history, setHistory] = useState<any[] | null>(null);
  const [otherWhy, setOtherWhy] = useState<DecisionExplanation | null>(null);
  const [otherWhyLoading, setOtherWhyLoading] = useState<string | null>(null);
  const { online, markOffline, markOnline } = useOnlineStatus();
  const inflight = useRef<Set<string>>(new Set());

  const activeDecisions = useMemo(
    () => decisions.filter((d) => !['completed', 'dismissed'].includes(d.status)),
    [decisions],
  );
  const focus = activeDecisions[0] || null;
  const later = activeDecisions.slice(1);

  const load = useCallback(async (opts?: { silent?: boolean }) => {
    if (!opts?.silent) setLoading(true);
    const [decRes, dailyRes, calRes] = await Promise.all([
      safe(() => api.topDecisions(10)),
      safe(() => api.dailyToday()),
      safe(() => api.googleCalendarInstances()),
    ]);

    // Detect network failure across the whole batch (all errors + all look network-y)
    const allErrors = [decRes.error, dailyRes.error, calRes.error].filter(Boolean);
    const allNetwork = allErrors.length === 3 && allErrors.every(isNetworkError);
    if (allNetwork) {
      markOffline();
    } else {
      markOnline();
      setLastSuccessAt(new Date());
    }

    const items = decRes.data?.items || [];
    setDecisions(items);
    setDaily(dailyRes.data || null);
    const insts = calRes.data?.items || [];
    setCalendarConnected(insts.length > 0);
    setCalendarSynced(insts.some((i: any) => i.last_sync_at));

    // Explanation only for focus
    if (items.length && flags.explain) {
      const exp = await safe(() => api.getExplanation(items[0].id));
      if (exp.status === 404 && exp.error?.detail?.includes?.('abilitata')) {
        setFlags((f) => ({ ...f, explain: false }));
        setExplanation(null);
      } else {
        setExplanation(exp.data || null);
      }
    } else {
      setExplanation(null);
    }
    setLoading(false);
  }, [flags.explain, markOffline, markOnline]);

  useEffect(() => { load(); }, [load]);

  // Refresh "N min fa" every 30s
  useEffect(() => {
    const id = setInterval(() => setTick((n) => n + 1), 30_000);
    return () => clearInterval(id);
  }, []);

  const runAction = useCallback(async (
    key: string,
    fn: () => Promise<any>,
    opts?: { onDone?: () => void; hapticIntent?: 'tap' | 'medium' | 'heavy' },
  ) => {
    if (inflight.current.has(key)) return;
    inflight.current.add(key);
    setActionBusy(key);
    setErrorBanner(null);
    haptic(opts?.hapticIntent || 'tap');
    try {
      await fn();
      haptic('success');
      await load({ silent: true });
      opts?.onDone?.();
    } catch (e: any) {
      if (isNetworkError(e)) markOffline();
      const status = e?.status;
      let msg = 'Errore, riprova.';
      if (isNetworkError(e)) msg = 'Sei offline. Controlla la connessione e riprova.';
      else if (status === 403) msg = 'Permesso non concesso per questa azione.';
      else if (status === 404) msg = 'Elemento non più disponibile.';
      else if (status === 409) msg = 'Questa transizione non è consentita nello stato attuale.';
      else if (status >= 500) msg = 'Servizio non disponibile. Riprova tra poco.';
      setErrorBanner(msg);
      haptic('error');
    } finally {
      inflight.current.delete(key);
      setActionBusy(null);
    }
  }, [load, markOffline]);

  const openWhy = useCallback(async () => {
    if (!focus || !flags.explain) return;
    haptic('tap');
    setWhyOpen(true);
    if (!explanation) {
      const exp = await safe(() => api.getExplanation(focus.id));
      if (exp.status === 404) setFlags((f) => ({ ...f, explain: false }));
      else setExplanation(exp.data || null);
    }
  }, [focus, explanation, flags.explain]);

  const openHistory = useCallback(async () => {
    if (!focus) return;
    haptic('tap');
    setHistoryOpen(true);
    setHistory(null);
    const r = await safe(() => api.historyDecision(focus.id));
    if (r.status === 404 && r.error?.detail?.includes?.('abilitato')) {
      setFlags((f) => ({ ...f, action: false }));
      setHistory([]);
    } else {
      setHistory(r.data?.items || []);
    }
  }, [focus]);

  const openOtherWhy = useCallback(async (id: string) => {
    haptic('tap');
    setOtherWhyLoading(id);
    const exp = await safe(() => api.getExplanation(id));
    setOtherWhyLoading(null);
    if (exp.data) setOtherWhy(exp.data);
  }, []);

  const onStart = () => focus && runAction(`start:${focus.id}`, () => api.startDecision(focus.id), { hapticIntent: 'tap' });
  const onComplete = () => focus && runAction(`complete:${focus.id}`, () => api.completeDecision(focus.id), {
    onDone: () => setConfirmCompleteOpen(false), hapticIntent: 'medium',
  });
  const onPartial = (pct: number, note?: string) =>
    focus && runAction(`partial:${focus.id}:${pct}`, () => api.partialDecision(focus.id, pct, undefined, note), {
      onDone: () => setPartialOpen(false), hapticIntent: 'medium',
    });
  const onPostpone = (until: string, reason?: string) =>
    focus && runAction(`postpone:${focus.id}`, () => api.postponeDecision(focus.id, until, reason), {
      onDone: () => setPostponeOpen(false), hapticIntent: 'medium',
    });
  const onBlock = (reason: string) =>
    focus && runAction(`block:${focus.id}`, () => api.blockDecision(focus.id, reason), {
      onDone: () => setBlockOpen(false), hapticIntent: 'medium',
    });
  const onDismiss = (reason?: string) =>
    focus && runAction(`dismiss:${focus.id}`, () => api.dismissDecision(focus.id, reason), {
      onDone: () => setDismissOpen(false), hapticIntent: 'tap',
    });

  const onRefresh = useCallback(async () => {
    haptic('select');
    setRefreshing(true);
    await load({ silent: true });
    setRefreshing(false);
  }, [load]);

  const showEmptyStates = calendarConnected === false || (calendarConnected === true && !calendarSynced);

  return (
    <SafeAreaView style={s.safe} edges={['top']} testID="home-safe">
      <ScrollView
        contentContainerStyle={[s.content, { paddingBottom: insets.bottom + 96 }]}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={tokens.color.onSurface}
            colors={[tokens.color.onSurface]}
            progressBackgroundColor={tokens.color.surfaceSecondary}
          />
        }
        showsVerticalScrollIndicator={false}
        testID="home-scroll"
      >
        <View style={s.header}>
          <Text style={s.h1} accessibilityRole="header">Adesso</Text>
          <SyncMeta online={online} lastSuccessAt={lastSuccessAt} />
        </View>

        {!online ? (
          <Animated.View
            entering={FadeIn.duration(200)}
            style={[s.banner, s.offlineBanner]}
            accessibilityRole="alert"
            accessibilityLiveRegion="polite"
            testID="offline-banner"
          >
            <Ionicons name="cloud-offline-outline" size={16} color={tokens.color.warning} />
            <Text style={s.bannerText}>Sei offline. I dati mostrati potrebbero non essere aggiornati.</Text>
          </Animated.View>
        ) : null}

        {errorBanner ? (
          <Animated.View
            entering={FadeIn.duration(200)}
            exiting={FadeOut.duration(200)}
            style={[s.banner, s.errorBanner]}
            accessibilityRole="alert"
            accessibilityLiveRegion="polite"
            testID="error-banner"
          >
            <Ionicons name="alert-circle" size={16} color={tokens.color.error} />
            <Text style={s.bannerText}>{errorBanner}</Text>
            <Pressable hitSlop={12} onPress={() => setErrorBanner(null)} accessibilityLabel="Chiudi errore" accessibilityRole="button">
              <Ionicons name="close" size={16} color={tokens.color.onSurfaceMuted} />
            </Pressable>
          </Animated.View>
        ) : null}

        {loading ? (
          <FocusSkeleton />
        ) : focus ? (
          <Animated.View
            key={focus.id}
            entering={FadeInDown.duration(tokens.motion.slow)}
            exiting={FadeOut.duration(tokens.motion.fast)}
            layout={LinearTransition.duration(tokens.motion.base)}
          >
            <FocusNowCard
              decision={focus}
              explanation={explanation}
              explainEnabled={flags.explain}
              actionEnabled={flags.action}
              actionBusy={actionBusy}
              onWhy={openWhy}
              onStart={onStart}
              onComplete={() => { haptic('tap'); setConfirmCompleteOpen(true); }}
              onPartial={() => { haptic('tap'); setPartialOpen(true); }}
              onPostpone={() => { haptic('tap'); setPostponeOpen(true); }}
              onMore={() => { haptic('tap'); setMoreMenuOpen(true); }}
              onHistory={openHistory}
            />
          </Animated.View>
        ) : (
          <Animated.View entering={FadeInDown.duration(tokens.motion.slow)}>
            <EmptyFocus />
          </Animated.View>
        )}

        {loading ? (
          <DailySkeleton />
        ) : flags.daily && daily ? (
          <DailyCard daily={daily} onOpen={() => { haptic('tap'); setDailyDetailOpen(true); }} />
        ) : null}

        {!loading && showEmptyStates ? (
          calendarConnected === false ? (
            <EmptyState
              icon="calendar-outline"
              title="Collega Google Calendar"
              body="Collega Google Calendar per aiutare ORA a comprendere la tua giornata."
              testID="empty-calendar"
            />
          ) : (
            <EmptyState
              icon="sync-outline"
              title="Avvia la prima sincronizzazione"
              body="Il calendario è collegato. Sincronizza ora per iniziare."
              testID="empty-sync"
            />
          )
        ) : null}

        {later.length > 0 && (
          <Animated.View layout={LinearTransition.duration(tokens.motion.base)} style={s.section}>
            <Text style={s.h2} accessibilityRole="header">Dopo</Text>
            {later.map((d, idx) => (
              <Animated.View
                key={d.id}
                entering={FadeInDown.duration(tokens.motion.base).delay(idx * 40)}
                exiting={FadeOut.duration(tokens.motion.fast)}
                layout={LinearTransition.duration(tokens.motion.base)}
              >
                <LaterCard
                  index={idx + 2}
                  decision={d}
                  explainEnabled={flags.explain}
                  onWhy={() => openOtherWhy(d.id)}
                  loadingWhy={otherWhyLoading === d.id}
                />
              </Animated.View>
            ))}
          </Animated.View>
        )}

        {loading && (
          <View style={s.section}>
            <LaterSkeleton />
            <LaterSkeleton />
          </View>
        )}
      </ScrollView>

      {/* Modals */}
      <WhyNowSheet open={whyOpen} onClose={() => setWhyOpen(false)} explanation={explanation} />
      <DailyDetailSheet open={dailyDetailOpen} onClose={() => setDailyDetailOpen(false)} daily={daily} />
      <ConfirmSheet
        open={confirmCompleteOpen} onClose={() => setConfirmCompleteOpen(false)}
        title="Segnare come completata?" body="Verrà rimossa dal Focus Now."
        confirmLabel="Completa" onConfirm={onComplete} loading={actionBusy?.startsWith('complete:')}
      />
      <PartialSheet open={partialOpen} onClose={() => setPartialOpen(false)} onSubmit={onPartial} loading={actionBusy?.startsWith('partial:')} />
      <PostponeSheet open={postponeOpen} onClose={() => setPostponeOpen(false)} onSubmit={onPostpone} loading={actionBusy?.startsWith('postpone:')} />
      <ReasonSheet open={blockOpen} onClose={() => setBlockOpen(false)} title="Blocca la Decision" placeholder="Motivo del blocco (obbligatorio)" required
        onSubmit={onBlock} loading={actionBusy?.startsWith('block:')} />
      <ReasonSheet open={dismissOpen} onClose={() => setDismissOpen(false)} title="Ignora la Decision" placeholder="Motivo (opzionale)"
        onSubmit={onDismiss} loading={actionBusy?.startsWith('dismiss:')} />
      <MoreMenu open={moreMenuOpen} onClose={() => setMoreMenuOpen(false)}
        onBlock={() => { setMoreMenuOpen(false); setBlockOpen(true); }}
        onDismiss={() => { setMoreMenuOpen(false); setDismissOpen(true); }}
        onHistory={() => { setMoreMenuOpen(false); openHistory(); }} />
      <HistorySheet open={historyOpen} onClose={() => setHistoryOpen(false)} items={history} />
      <WhyNowSheet open={!!otherWhy} onClose={() => setOtherWhy(null)} explanation={otherWhy} />
    </SafeAreaView>
  );
}

// -------------------- Small header meta ---------------------------
function SyncMeta({ online, lastSuccessAt }: { online: boolean; lastSuccessAt: Date | null }) {
  if (!online) {
    return (
      <View style={s.syncMetaRow}>
        <View style={[s.dot, { backgroundColor: tokens.color.warning }]} />
        <Text style={s.syncMetaText}>Offline</Text>
      </View>
    );
  }
  if (!lastSuccessAt) return null;
  return (
    <View style={s.syncMetaRow} accessibilityLabel={`Ultimo aggiornamento ${formatRelativeAgo(lastSuccessAt)}`}>
      <View style={[s.dot, { backgroundColor: tokens.color.success }]} />
      <Text style={s.syncMetaText}>Aggiornato {formatRelativeAgo(lastSuccessAt)}</Text>
    </View>
  );
}

// -------------------- Components ---------------------------------
function FocusNowCard({ decision, explanation, explainEnabled, actionEnabled, actionBusy, onWhy, onStart, onComplete, onPartial, onPostpone, onMore, onHistory }: any) {
  const risk = explanation?.estimated_postpone_risk;
  const impact = explanation?.estimated_impact;
  const conf = explanation?.confidence;
  const st = decision.action_state?.status || decision.status;
  const pct = decision.action_state?.completion_percentage as number | null | undefined;
  const inProgress = st === 'in_progress';
  const partial = st === 'partially_completed';
  const statusColor = inProgress ? tokens.color.info : partial ? tokens.color.warning : tokens.color.onSurfaceMuted;

  return (
    <View
      style={s.focusCard}
      testID="focus-card"
      accessible={false}
    >
      <View style={s.focusHeader}>
        <View style={s.pill} accessibilityLabel="Focus adesso">
          <View style={s.pillDot} />
          <Text style={s.pillText}>ORA</Text>
        </View>
        <View
          style={[s.statusPill, { borderColor: statusColor }]}
          accessibilityLabel={`Stato ${STATUS_LABELS[st] || 'Da fare'}`}
        >
          <View style={[s.dot, { backgroundColor: statusColor }]} />
          <Text style={s.statusText}>{STATUS_LABELS[st] || 'Da fare'}</Text>
        </View>
      </View>

      <Text style={s.focusTitle} accessibilityRole="header">{decision.title}</Text>
      {decision.description ? <Text style={s.focusDesc}>{decision.description}</Text> : null}

      {inProgress ? (
        <View style={s.progressWrap} accessibilityLabel="In corso">
          <View style={s.progressTrack}>
            <Animated.View
              entering={FadeIn.duration(tokens.motion.base)}
              style={[s.progressBar, { width: `${Math.max(10, pct || 20)}%`, backgroundColor: tokens.color.info }]}
            />
          </View>
          <Text style={s.progressLabel}>
            {pct != null ? `Avanzamento ${pct}%` : 'In corso'}
          </Text>
        </View>
      ) : partial && pct != null ? (
        <View style={s.progressWrap} accessibilityLabel={`Completata ${pct}%`}>
          <View style={s.progressTrack}>
            <View style={[s.progressBar, { width: `${pct}%`, backgroundColor: tokens.color.warning }]} />
          </View>
          <Text style={s.progressLabel}>Parziale · {pct}%</Text>
        </View>
      ) : null}

      {explanation?.human_summary ? (
        <View style={s.summaryBox}>
          <Ionicons name="sparkles-outline" size={13} color={tokens.color.onSurfaceMuted} />
          <Text style={s.summary}>{explanation.human_summary}</Text>
        </View>
      ) : null}

      <View style={s.metaGrid}>
        <MetaItem icon="time-outline" label="Durata" value={formatMinutes(decision.time_required_min)} />
        <MetaItem
          icon="flag-outline" label="Impatto"
          value={impact ? IMPACT_LABELS[impact] : '—'}
          tone={impact === 'high' ? 'warning' : 'default'}
        />
        <MetaItem
          icon="alert-outline" label="Rimando"
          value={risk ? RISK_LABELS[risk] : '—'}
          tone={risk === 'high' ? 'error' : risk === 'medium' ? 'warning' : 'default'}
        />
        {decision.deadline ? <MetaItem icon="calendar-outline" label="Scadenza" value={formatDateTime(decision.deadline)} /> : null}
        {conf ? <MetaItem icon="stats-chart-outline" label="Confidenza" value={CONFIDENCE_LABELS[conf]} /> : null}
      </View>

      {explainEnabled ? (
        <Pressable
          style={({ pressed }) => [s.whyBtn, pressed && s.pressed]}
          onPress={onWhy}
          accessibilityRole="button"
          accessibilityLabel="Mostra il ragionamento della priorità"
          testID="why-now-btn"
          hitSlop={8}
        >
          <Ionicons name="bulb-outline" size={16} color={tokens.color.onSurface} />
          <Text style={s.whyBtnText}>Perché adesso?</Text>
          <Ionicons name="chevron-forward" size={14} color={tokens.color.onSurfaceMuted} />
        </Pressable>
      ) : null}

      {actionEnabled ? (
        <View style={s.actions}>
          {!inProgress && !partial && (
            <ActionBtn primary label="Inizia" icon="play" onPress={onStart} loading={actionBusy?.startsWith('start:')} testID="btn-start" />
          )}
          <ActionBtn label="Risolvi" icon="checkmark" onPress={onComplete} loading={actionBusy?.startsWith('complete:')} testID="btn-complete" />
          <ActionBtn label="Parziale" icon="pie-chart-outline" onPress={onPartial} testID="btn-partial" />
          <ActionBtn label="Rimanda" icon="hourglass-outline" onPress={onPostpone} testID="btn-postpone" />
          <ActionBtn label="Altro" icon="ellipsis-horizontal" onPress={onMore} testID="btn-more" />
        </View>
      ) : null}
    </View>
  );
}

function MetaItem({ icon, label, value, tone }: any) {
  const bg =
    tone === 'error' ? tokens.color.errorBg :
    tone === 'warning' ? tokens.color.warningBg :
    tone === 'success' ? tokens.color.successBg :
    tokens.color.surfaceTertiary;
  const color =
    tone === 'error' ? tokens.color.error :
    tone === 'warning' ? tokens.color.warning :
    tone === 'success' ? tokens.color.success :
    tokens.color.onSurface;
  return (
    <View style={[s.meta, { backgroundColor: bg }]} accessible accessibilityLabel={`${label}: ${value}`}>
      <Ionicons name={icon} size={13} color={tokens.color.onSurfaceMuted} />
      <Text style={s.metaLabel}>{label}</Text>
      <Text style={[s.metaValue, { color }]}>{value}</Text>
    </View>
  );
}

function ActionBtn({ label, icon, onPress, primary, loading, testID }: any) {
  return (
    <Pressable
      onPress={onPress}
      disabled={loading}
      style={({ pressed }) => [
        s.actionBtn,
        primary && s.actionBtnPrimary,
        loading && s.actionBtnDim,
        pressed && s.pressed,
      ]}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ busy: !!loading, disabled: !!loading }}
      testID={testID}
      hitSlop={8}
    >
      {loading ? (
        <ActivityIndicator size="small" color={primary ? tokens.color.onBrand : tokens.color.onSurface} />
      ) : (
        <>
          <Ionicons name={icon} size={16} color={primary ? tokens.color.onBrand : tokens.color.onSurface} />
          <Text style={[s.actionBtnText, primary && s.actionBtnTextPrimary]}>{label}</Text>
        </>
      )}
    </Pressable>
  );
}

function DailyCard({ daily, onOpen }: { daily: DailySummary; onOpen: () => void }) {
  const warnings = daily.warnings.slice(0, 2);
  const opps = daily.opportunities.slice(0, 2);
  const firstFree = daily.free_slots.find((f) => f.duration_min >= 30);
  const scoreColor =
    daily.score >= 66 ? tokens.color.success :
    daily.score >= 33 ? tokens.color.warning :
    tokens.color.error;
  const scoreBg =
    daily.score >= 66 ? tokens.color.successBg :
    daily.score >= 33 ? tokens.color.warningBg :
    tokens.color.errorBg;
  return (
    <Animated.View entering={FadeInDown.duration(tokens.motion.slow)} style={s.card} testID="daily-card">
      <View style={s.cardHeader}>
        <Text style={s.h3} accessibilityRole="header">La tua giornata</Text>
        <View style={[s.scorePill, { backgroundColor: scoreBg }]} accessibilityLabel={`Punteggio ${daily.score} su 100`}>
          <Text style={[s.scoreText, { color: scoreColor }]}>{daily.score}/100</Text>
        </View>
      </View>
      <View style={s.dailyRow}>
        <DailyMeta icon="calendar-outline" label={`${daily.total_events} eventi`} />
        <DailyMeta icon="time-outline" label={`${Math.round(daily.busy_minutes / 60 * 10) / 10}h occupate`} />
        <DailyMeta icon="battery-half-outline" label={ENERGY_LABELS[daily.energy_estimation.level]} />
      </View>
      {firstFree ? (
        <View style={s.freeRow}>
          <Ionicons name="sunny-outline" size={13} color={tokens.color.onSurfaceMuted} />
          <Text style={s.dailyFree}>Prima finestra libera: {formatTime(firstFree.start)}–{formatTime(firstFree.end)}</Text>
        </View>
      ) : null}
      {warnings.length > 0 && (
        <View style={s.chipsRow}>
          {warnings.map((w) => (
            <View key={w} style={[s.chip, { backgroundColor: tokens.color.warningBg, borderColor: tokens.color.warning }]}>
              <Ionicons name="alert-circle-outline" size={12} color={tokens.color.warning} />
              <Text style={[s.chipText, { color: tokens.color.warning }]}>{DAILY_WARNING_LABELS[w] || w}</Text>
            </View>
          ))}
        </View>
      )}
      {opps.length > 0 && (
        <View style={s.chipsRow}>
          {opps.map((o) => (
            <View key={o} style={[s.chip, { backgroundColor: tokens.color.successBg, borderColor: tokens.color.success }]}>
              <Ionicons name="leaf-outline" size={12} color={tokens.color.success} />
              <Text style={[s.chipText, { color: tokens.color.success }]}>{DAILY_OPPORTUNITY_LABELS[o] || o}</Text>
            </View>
          ))}
        </View>
      )}
      <Pressable
        style={({ pressed }) => [s.linkBtn, pressed && s.pressed]}
        onPress={onOpen}
        accessibilityRole="button"
        accessibilityLabel="Vedi il dettaglio della giornata"
        testID="btn-daily-detail"
        hitSlop={8}
      >
        <Text style={s.linkBtnText}>Vedi giornata</Text>
        <Ionicons name="chevron-forward" size={14} color={tokens.color.onSurface} />
      </Pressable>
    </Animated.View>
  );
}

function DailyMeta({ icon, label }: any) {
  return (
    <View style={s.dailyMeta} accessible accessibilityLabel={label}>
      <Ionicons name={icon} size={14} color={tokens.color.onSurfaceMuted} />
      <Text style={s.dailyMetaText}>{label}</Text>
    </View>
  );
}

function LaterCard({ index, decision, explainEnabled, onWhy, loadingWhy }: any) {
  const st = decision.action_state?.status || decision.status;
  return (
    <View style={s.laterCard} accessible accessibilityLabel={`Prossima ${index}: ${decision.title}`}>
      <View style={s.laterHead}>
        <Text style={s.laterIndex}>{index}</Text>
        <Text style={s.laterTitle} numberOfLines={2}>{decision.title}</Text>
      </View>
      <View style={s.laterMeta}>
        <Text style={s.laterMetaText}>{formatMinutes(decision.time_required_min)}</Text>
        {decision.deadline && <Text style={s.laterMetaText}>· Scad. {formatDateTime(decision.deadline)}</Text>}
        <Text style={s.laterMetaText}>· {STATUS_LABELS[st] || 'Da fare'}</Text>
      </View>
      {explainEnabled && (
        <Pressable
          style={({ pressed }) => [s.whyMini, pressed && s.pressed]}
          onPress={onWhy}
          disabled={loadingWhy}
          accessibilityRole="button"
          accessibilityLabel="Perché è prioritaria"
          accessibilityState={{ busy: !!loadingWhy }}
          hitSlop={8}
        >
          {loadingWhy ? (
            <ActivityIndicator size="small" color={tokens.color.onSurfaceMuted} />
          ) : (
            <>
              <Ionicons name="bulb-outline" size={13} color={tokens.color.onSurface} />
              <Text style={s.whyMiniText}>Perché?</Text>
            </>
          )}
        </Pressable>
      )}
    </View>
  );
}

function EmptyFocus() {
  return (
    <View style={s.emptyFocus} accessible accessibilityLabel="Nessuna decisione attiva" testID="empty-focus">
      <View style={s.emptyIconWrap}>
        <Ionicons name="checkmark-done-outline" size={32} color={tokens.color.success} />
      </View>
      <Text style={s.emptyTitle}>Per ora è tutto sotto controllo.</Text>
      <Text style={s.emptyBody}>Nessuna Decision attiva. Torna quando ne aggiungi una o quando ORA rileverà nuovi impegni.</Text>
    </View>
  );
}

function EmptyState({ icon, title, body, testID }: any) {
  return (
    <View style={s.card} testID={testID} accessible accessibilityLabel={title}>
      <View style={s.emptyStateHead}>
        <Ionicons name={icon} size={18} color={tokens.color.onSurfaceMuted} />
        <Text style={s.h3}>{title}</Text>
      </View>
      <Text style={s.emptyBody}>{body}</Text>
    </View>
  );
}

// -------------------- Sheets --------------------
function Sheet({ open, onClose, children, title, testID }: any) {
  return (
    <Modal visible={!!open} transparent animationType="none" onRequestClose={onClose} statusBarTranslucent>
      {open ? (
        <>
          <Animated.View entering={FadeIn.duration(tokens.motion.fast)} exiting={FadeOut.duration(tokens.motion.fast)} style={s.backdrop}>
            <Pressable style={{ flex: 1 }} onPress={onClose} accessibilityLabel="Chiudi" accessibilityRole="button" />
          </Animated.View>
          <Animated.View
            entering={SlideInDown.duration(tokens.motion.slow).springify().damping(18)}
            exiting={FadeOut.duration(tokens.motion.fast)}
            style={s.sheet}
            testID={testID}
          >
            <View style={s.sheetGrab} />
            {title && <Text style={s.sheetTitle} accessibilityRole="header">{title}</Text>}
            <ScrollView showsVerticalScrollIndicator={false}>{children}</ScrollView>
          </Animated.View>
        </>
      ) : null}
    </Modal>
  );
}

function WhyNowSheet({ open, onClose, explanation }: any) {
  if (!open) return null;
  if (!explanation) {
    return (
      <Sheet open={open} onClose={onClose} title="Perché adesso" testID="sheet-why">
        <View style={{ padding: 24 }}>
          <ActivityIndicator color={tokens.color.onSurfaceMuted} />
        </View>
      </Sheet>
    );
  }
  return (
    <Sheet open={open} onClose={onClose} title="Perché adesso" testID="sheet-why">
      <Text style={s.whyTitle}>{explanation.human_summary}</Text>

      <SheetSection title="Cosa la rende prioritaria">
        {explanation.applied_rules.map((r: any) => (
          <View key={r.id} style={s.ruleRow}>
            <View style={[s.ruleDot, { backgroundColor: r.weight === 'high' ? tokens.color.error : r.weight === 'medium' ? tokens.color.warning : tokens.color.info }]} />
            <View style={{ flex: 1 }}>
              <Text style={s.ruleLabel}>{ruleLabel(r.id)}</Text>
              {r.evidence?.map((e: string, i: number) => (<Text key={i} style={s.ruleEvidence}>{e}</Text>))}
            </View>
          </View>
        ))}
        {explanation.applied_rules.length === 0 && <Text style={s.muted}>Nessuna regola applicata in modo particolare.</Text>}
      </SheetSection>

      <SheetSection title="Passi del ragionamento">
        {explanation.reasoning_steps.map((r: string, i: number) => (
          <Text key={i} style={s.step}>• {r}</Text>
        ))}
      </SheetSection>

      <SheetSection title="Stime">
        <View style={s.statRow}>
          <Stat label="Durata" value={formatMinutes(explanation.estimated_duration_minutes)} />
          <Stat label="Impatto" value={IMPACT_LABELS[explanation.estimated_impact]} />
        </View>
        <View style={s.statRow}>
          <Stat label="Rischio rinvio" value={RISK_LABELS[explanation.estimated_postpone_risk]} color={riskColor(explanation.estimated_postpone_risk)} bg={riskBg(explanation.estimated_postpone_risk)} />
          <Stat label="Confidenza" value={CONFIDENCE_LABELS[explanation.confidence]} />
        </View>
      </SheetSection>

      <SheetSection title="Dati utilizzati">
        {explanation.data_sources.map((d: any, i: number) => (
          <View key={i} style={s.sourceRow}>
            <Ionicons name="cube-outline" size={14} color={tokens.color.onSurfaceMuted} />
            <View style={{ flex: 1 }}>
              <Text style={s.sourceName}>{d.source}</Text>
              {d.notes && <Text style={s.sourceNotes}>{d.notes}</Text>}
              <Text style={s.sourceMeta}>Confidenza: {CONFIDENCE_LABELS[d.confidence] || d.confidence}{d.last_updated_at ? ` · aggiornato ${formatDateTime(d.last_updated_at)}` : ''}</Text>
            </View>
          </View>
        ))}
      </SheetSection>

      {explanation.context_used?.length > 0 && (
        <SheetSection title="Contesto considerato">
          {explanation.context_used.map((c: string, i: number) => (<Text key={i} style={s.step}>• {c}</Text>))}
        </SheetSection>
      )}
    </Sheet>
  );
}

function SheetSection({ title, children }: any) {
  return (
    <View style={s.sheetSection}>
      <Text style={s.sheetSectionTitle}>{title}</Text>
      {children}
    </View>
  );
}

function Stat({ label, value, color, bg }: any) {
  return (
    <View style={[s.statBox, bg ? { backgroundColor: bg } : null]}>
      <Text style={s.statLabel}>{label}</Text>
      <Text style={[s.statValue, color ? { color } : null]}>{value}</Text>
    </View>
  );
}

function DailyDetailSheet({ open, onClose, daily }: any) {
  if (!open || !daily) return null;
  return (
    <Sheet open={open} onClose={onClose} title="La tua giornata" testID="sheet-daily">
      <View style={s.statRow}>
        <Stat label="Score" value={`${daily.score}/100`} />
        <Stat label="Energia" value={ENERGY_LABELS[daily.energy_estimation.level]} />
      </View>
      <View style={s.statRow}>
        <Stat label="Eventi" value={String(daily.total_events)} />
        <Stat label="Confidenza" value={CONFIDENCE_LABELS[daily.confidence]} />
      </View>
      <SheetSection title="Impegni">
        {daily.busy_slots.length === 0 && <Text style={s.muted}>Nessun impegno pianificato.</Text>}
        {daily.busy_slots.map((b: any, i: number) => (
          <Text key={i} style={s.step}>• {formatTime(b.start)}–{formatTime(b.end)} · {formatMinutes(b.duration_min)}{b.category ? ` · ${b.category}` : ''}</Text>
        ))}
      </SheetSection>
      <SheetSection title="Finestre libere">
        {daily.free_slots.slice(0, 5).map((f: any, i: number) => (
          <Text key={i} style={s.step}>• {formatTime(f.start)}–{formatTime(f.end)} · {formatMinutes(f.duration_min)}</Text>
        ))}
      </SheetSection>
      {daily.signals.length > 0 && (
        <SheetSection title="Segnali">
          {daily.signals.map((sg: string) => (<Text key={sg} style={s.step}>• {DAILY_SIGNAL_LABELS[sg] || sg}</Text>))}
        </SheetSection>
      )}
    </Sheet>
  );
}

function ConfirmSheet({ open, onClose, title, body, confirmLabel, onConfirm, loading }: any) {
  if (!open) return null;
  return (
    <Sheet open={open} onClose={onClose} title={title} testID="sheet-confirm">
      <Text style={s.step}>{body}</Text>
      <View style={s.sheetActions}>
        <ActionBtn label="Annulla" icon="close" onPress={onClose} />
        <ActionBtn primary label={confirmLabel} icon="checkmark" onPress={onConfirm} loading={loading} testID="btn-confirm" />
      </View>
    </Sheet>
  );
}

function PartialSheet({ open, onClose, onSubmit, loading }: any) {
  const [pct, setPct] = useState(50);
  const [note, setNote] = useState('');
  useEffect(() => { if (open) { setPct(50); setNote(''); } }, [open]);
  if (!open) return null;
  return (
    <Sheet open={open} onClose={onClose} title="Progresso parziale" testID="sheet-partial">
      <View style={{ flexDirection: 'row', gap: 8, marginTop: 8 }}>
        {[25, 50, 75].map((p) => (
          <Pressable
            key={p}
            onPress={() => { haptic('select'); setPct(p); }}
            style={({ pressed }) => [s.pctBtn, pct === p && s.pctBtnActive, pressed && s.pressed]}
            accessibilityRole="button"
            accessibilityLabel={`${p} percento`}
            accessibilityState={{ selected: pct === p }}
          >
            <Text style={[s.pctBtnText, pct === p && s.pctBtnTextActive]}>{p}%</Text>
          </Pressable>
        ))}
      </View>
      <TextInput
        placeholder="Nota (opzionale)" placeholderTextColor={tokens.color.onSurfaceMuted}
        value={note} onChangeText={setNote} style={s.input}
        accessibilityLabel="Nota facoltativa"
      />
      <View style={s.sheetActions}>
        <ActionBtn label="Annulla" icon="close" onPress={onClose} />
        <ActionBtn primary label="Salva" icon="save-outline" onPress={() => onSubmit(pct, note || undefined)} loading={loading} />
      </View>
    </Sheet>
  );
}

function PostponeSheet({ open, onClose, onSubmit, loading }: any) {
  const [reason, setReason] = useState('');
  const now = new Date();
  const options = [
    { label: 'Più tardi oggi', dt: new Date(now.getTime() + 3 * 3600 * 1000) },
    { label: 'Domani', dt: new Date(now.getTime() + 24 * 3600 * 1000) },
    { label: 'Weekend', dt: (() => { const d = new Date(now); const day = d.getDay(); const offset = (6 - day + 7) % 7 || 7; d.setDate(d.getDate() + offset); return d; })() },
  ];
  useEffect(() => { if (open) setReason(''); }, [open]);
  if (!open) return null;
  return (
    <Sheet open={open} onClose={onClose} title="Rimanda" testID="sheet-postpone">
      {options.map((o) => (
        <Pressable
          key={o.label}
          onPress={() => onSubmit(o.dt.toISOString(), reason || undefined)}
          style={({ pressed }) => [s.optionBtn, pressed && s.pressed]}
          disabled={loading}
          accessibilityRole="button"
          accessibilityLabel={`Rimanda a ${o.label}`}
        >
          <Ionicons name="hourglass-outline" size={14} color={tokens.color.onSurface} />
          <Text style={s.optionText}>{o.label}</Text>
          <Text style={s.optionMeta}>{formatDateTime(o.dt.toISOString())}</Text>
        </Pressable>
      ))}
      <TextInput
        placeholder="Motivo (opzionale)" placeholderTextColor={tokens.color.onSurfaceMuted}
        value={reason} onChangeText={setReason} style={s.input}
        accessibilityLabel="Motivo facoltativo"
      />
      <View style={s.sheetActions}>
        <ActionBtn label="Annulla" icon="close" onPress={onClose} />
      </View>
    </Sheet>
  );
}

function ReasonSheet({ open, onClose, title, placeholder, required, onSubmit, loading }: any) {
  const [text, setText] = useState('');
  useEffect(() => { if (open) setText(''); }, [open]);
  const canSubmit = !required || text.trim().length > 0;
  if (!open) return null;
  return (
    <Sheet open={open} onClose={onClose} title={title} testID="sheet-reason">
      <TextInput
        placeholder={placeholder} placeholderTextColor={tokens.color.onSurfaceMuted}
        value={text} onChangeText={setText} style={[s.input, { minHeight: 88 }]} multiline
        accessibilityLabel={placeholder}
      />
      <View style={s.sheetActions}>
        <ActionBtn label="Annulla" icon="close" onPress={onClose} />
        <ActionBtn primary label="Conferma" icon="checkmark" onPress={() => canSubmit && onSubmit(text.trim() || undefined)} loading={loading} />
      </View>
    </Sheet>
  );
}

function MoreMenu({ open, onClose, onBlock, onDismiss, onHistory }: any) {
  if (!open) return null;
  return (
    <Sheet open={open} onClose={onClose} title="Altre azioni" testID="sheet-more">
      <Pressable style={({ pressed }) => [s.optionBtn, pressed && s.pressed]} onPress={onHistory} accessibilityRole="button" accessibilityLabel="Vedi cronologia">
        <Ionicons name="time-outline" size={16} color={tokens.color.onSurface} />
        <Text style={s.optionText}>Cronologia</Text>
        <Ionicons name="chevron-forward" size={14} color={tokens.color.onSurfaceMuted} />
      </Pressable>
      <Pressable style={({ pressed }) => [s.optionBtn, pressed && s.pressed]} onPress={onBlock} accessibilityRole="button" accessibilityLabel="Blocca la decision">
        <Ionicons name="lock-closed-outline" size={16} color={tokens.color.warning} />
        <Text style={[s.optionText, { color: tokens.color.warning }]}>Blocca</Text>
        <Ionicons name="chevron-forward" size={14} color={tokens.color.onSurfaceMuted} />
      </Pressable>
      <Pressable style={({ pressed }) => [s.optionBtn, pressed && s.pressed]} onPress={onDismiss} accessibilityRole="button" accessibilityLabel="Ignora la decision">
        <Ionicons name="close-circle-outline" size={16} color={tokens.color.error} />
        <Text style={[s.optionText, { color: tokens.color.error }]}>Ignora</Text>
        <Ionicons name="chevron-forward" size={14} color={tokens.color.onSurfaceMuted} />
      </Pressable>
    </Sheet>
  );
}

function HistorySheet({ open, onClose, items }: any) {
  if (!open) return null;
  return (
    <Sheet open={open} onClose={onClose} title="Cronologia" testID="sheet-history">
      {items === null ? (
        <View style={{ padding: 24 }}>
          <ActivityIndicator color={tokens.color.onSurfaceMuted} />
        </View>
      ) : items.length === 0 ? (
        <Text style={s.muted}>Nessun evento registrato.</Text>
      ) : (
        items.map((h: any) => (
          <View key={h.id} style={s.timelineRow}>
            <View style={s.timelineDot} />
            <View style={{ flex: 1 }}>
              <Text style={s.timelineTitle}>{USER_ACTION_LABELS[h.user_action] || h.user_action}</Text>
              <Text style={s.timelineMeta}>{formatDateTime(h.timestamp)}</Text>
              {h.reason && <Text style={s.timelineNote}>Motivo: {h.reason}</Text>}
              {h.note && <Text style={s.timelineNote}>Nota: {h.note}</Text>}
              {h.completion_percentage != null && <Text style={s.timelineNote}>Progresso: {h.completion_percentage}%</Text>}
            </View>
          </View>
        ))
      )}
    </Sheet>
  );
}

// -------------------- Styles --------------------
const { width: SCREEN_W } = Dimensions.get('window');
const isWide = SCREEN_W >= 700;

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: tokens.color.surface },
  content: {
    padding: tokens.spacing.lg,
    gap: tokens.spacing.lg,
    maxWidth: 720,
    width: '100%',
    alignSelf: 'center',
  },
  header: { marginBottom: tokens.spacing.sm, flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'space-between' },
  h1: { fontSize: 34, fontWeight: '700', color: tokens.color.onSurface, letterSpacing: -0.5 },
  h2: { fontSize: 20, fontWeight: '600', color: tokens.color.onSurface, marginBottom: tokens.spacing.sm },
  h3: { fontSize: 16, fontWeight: '600', color: tokens.color.onSurface },
  section: { gap: tokens.spacing.sm },

  syncMetaRow: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingBottom: 6 },
  syncMetaText: { fontSize: 11, color: tokens.color.onSurfaceDim, fontWeight: '500' },

  banner: { flexDirection: 'row', alignItems: 'center', gap: 8, borderRadius: tokens.radius.md, padding: 12, borderWidth: 1 },
  offlineBanner: { backgroundColor: tokens.color.warningBg, borderColor: tokens.color.warning },
  errorBanner: { backgroundColor: tokens.color.errorBg, borderColor: tokens.color.error },
  bannerText: { flex: 1, color: tokens.color.onSurface, fontSize: 13 },

  focusCard: {
    backgroundColor: tokens.color.surfaceSecondary,
    borderRadius: tokens.radius.lg,
    padding: tokens.spacing.lg,
    gap: tokens.spacing.md,
    borderWidth: 1,
    borderColor: tokens.color.borderStrong,
    // subtle depth
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.25,
    shadowRadius: 12,
    elevation: 4,
  },
  focusHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  pill: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 10, paddingVertical: 5, borderRadius: tokens.radius.pill, backgroundColor: tokens.color.brand },
  pillDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: tokens.color.onBrand },
  pillText: { fontSize: 10, fontWeight: '700', color: tokens.color.onBrand, letterSpacing: 1 },
  statusPill: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 10, paddingVertical: 4, borderRadius: tokens.radius.pill, borderWidth: 1 },
  dot: { width: 6, height: 6, borderRadius: 3 },
  statusText: { fontSize: 11, color: tokens.color.onSurface, fontWeight: '500' },

  focusTitle: { fontSize: isWide ? 26 : 24, fontWeight: '700', color: tokens.color.onSurface, lineHeight: isWide ? 32 : 30, letterSpacing: -0.3 },
  focusDesc: { fontSize: 14, color: tokens.color.onSurfaceMuted, lineHeight: 20 },

  summaryBox: { flexDirection: 'row', gap: 8, alignItems: 'flex-start', backgroundColor: tokens.color.surfaceTertiary, padding: 10, borderRadius: tokens.radius.md, borderLeftWidth: 2, borderLeftColor: tokens.color.brand },
  summary: { flex: 1, fontSize: 13, color: tokens.color.onSurface, lineHeight: 19 },

  progressWrap: { gap: 6 },
  progressTrack: { width: '100%', height: 6, borderRadius: 3, backgroundColor: tokens.color.surfaceTertiary, overflow: 'hidden' },
  progressBar: { height: 6, borderRadius: 3 },
  progressLabel: { fontSize: 11, color: tokens.color.onSurfaceMuted, fontWeight: '500' },

  metaGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: tokens.spacing.sm },
  meta: { flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 10, paddingVertical: 7, borderRadius: tokens.radius.md },
  metaLabel: { fontSize: 11, color: tokens.color.onSurfaceMuted },
  metaValue: { fontSize: 12, color: tokens.color.onSurface, fontWeight: '600' },

  whyBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, alignSelf: 'flex-start', paddingHorizontal: 14, paddingVertical: 10, borderRadius: tokens.radius.pill, borderWidth: 1, borderColor: tokens.color.borderStrong, minHeight: tokens.touch.min, backgroundColor: tokens.color.surfaceTertiary },
  whyBtnText: { fontSize: 13, color: tokens.color.onSurface, fontWeight: '600' },

  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 4 },
  actionBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, minHeight: tokens.touch.min, minWidth: tokens.touch.min, paddingHorizontal: 14, paddingVertical: 10, borderRadius: tokens.radius.md, backgroundColor: tokens.color.surfaceTertiary, borderWidth: 1, borderColor: tokens.color.border },
  actionBtnPrimary: { backgroundColor: tokens.color.brand, borderColor: tokens.color.brand },
  actionBtnDim: { opacity: 0.6 },
  actionBtnText: { fontSize: 13, color: tokens.color.onSurface, fontWeight: '600' },
  actionBtnTextPrimary: { color: tokens.color.onBrand },
  pressed: { opacity: 0.7, transform: [{ scale: 0.98 }] },

  card: { backgroundColor: tokens.color.surfaceSecondary, borderRadius: tokens.radius.lg, padding: tokens.spacing.lg, gap: 8, borderWidth: 1, borderColor: tokens.color.border },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  scorePill: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: tokens.radius.pill },
  scoreText: { fontSize: 12, fontWeight: '700' },

  dailyRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 4 },
  dailyMeta: { flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 10, paddingVertical: 5, borderRadius: tokens.radius.pill, backgroundColor: tokens.color.surfaceTertiary },
  dailyMetaText: { fontSize: 12, color: tokens.color.onSurface, fontWeight: '500' },
  freeRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 4 },
  dailyFree: { fontSize: 13, color: tokens.color.onSurfaceMuted },
  chipsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 4 },
  chip: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 8, paddingVertical: 4, borderRadius: tokens.radius.pill, borderWidth: 1 },
  chipText: { fontSize: 11, fontWeight: '600' },
  linkBtn: { flexDirection: 'row', alignItems: 'center', gap: 4, alignSelf: 'flex-start', paddingVertical: 8, minHeight: tokens.touch.min },
  linkBtnText: { fontSize: 13, color: tokens.color.onSurface, fontWeight: '600' },

  laterCard: { backgroundColor: tokens.color.surfaceSecondary, borderRadius: tokens.radius.md, padding: tokens.spacing.md, gap: 6, borderWidth: 1, borderColor: tokens.color.border, marginBottom: 8 },
  laterHead: { flexDirection: 'row', alignItems: 'flex-start', gap: 8 },
  laterIndex: { fontSize: 13, color: tokens.color.onSurfaceMuted, fontWeight: '700', minWidth: 18 },
  laterTitle: { fontSize: 15, color: tokens.color.onSurface, fontWeight: '600', flex: 1, lineHeight: 20 },
  laterMeta: { flexDirection: 'row', flexWrap: 'wrap', gap: 4, marginLeft: 26 },
  laterMetaText: { fontSize: 11, color: tokens.color.onSurfaceMuted },
  whyMini: { flexDirection: 'row', alignItems: 'center', gap: 4, alignSelf: 'flex-start', paddingHorizontal: 12, paddingVertical: 8, borderRadius: tokens.radius.pill, borderWidth: 1, borderColor: tokens.color.borderStrong, marginLeft: 26, minHeight: 32, backgroundColor: tokens.color.surfaceTertiary },
  whyMiniText: { fontSize: 11, color: tokens.color.onSurface, fontWeight: '600' },

  emptyFocus: { backgroundColor: tokens.color.surfaceSecondary, borderRadius: tokens.radius.lg, padding: tokens.spacing.xl, alignItems: 'center', gap: 10, borderWidth: 1, borderColor: tokens.color.border },
  emptyIconWrap: { width: 56, height: 56, borderRadius: 28, backgroundColor: tokens.color.successBg, alignItems: 'center', justifyContent: 'center' },
  emptyTitle: { fontSize: 17, fontWeight: '600', color: tokens.color.onSurface, textAlign: 'center' },
  emptyBody: { fontSize: 13, color: tokens.color.onSurfaceMuted, textAlign: 'center', lineHeight: 19 },
  emptyStateHead: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 4 },

  backdrop: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: tokens.color.scrim },
  sheet: {
    position: 'absolute', bottom: 0, left: 0, right: 0,
    maxHeight: '85%',
    backgroundColor: tokens.color.surfaceSecondary,
    borderTopLeftRadius: tokens.radius.xl,
    borderTopRightRadius: tokens.radius.xl,
    padding: tokens.spacing.lg,
    paddingBottom: Platform.OS === 'ios' ? tokens.spacing.xxl : tokens.spacing.xxl,
    borderWidth: 1,
    borderColor: tokens.color.border,
    borderBottomWidth: 0,
  },
  sheetGrab: { width: 40, height: 4, backgroundColor: tokens.color.borderStrong, borderRadius: 2, alignSelf: 'center', marginBottom: 12 },
  sheetTitle: { fontSize: 18, fontWeight: '700', color: tokens.color.onSurface, marginBottom: 12 },
  sheetSection: { marginTop: 16, gap: 6 },
  sheetSectionTitle: { fontSize: 11, color: tokens.color.onSurfaceMuted, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4, fontWeight: '600' },
  sheetActions: { flexDirection: 'row', gap: 8, marginTop: 16 },

  whyTitle: { fontSize: 16, color: tokens.color.onSurface, lineHeight: 22 },
  ruleRow: { flexDirection: 'row', gap: 10, alignItems: 'flex-start', paddingVertical: 6 },
  ruleDot: { width: 8, height: 8, borderRadius: 4, marginTop: 6 },
  ruleLabel: { fontSize: 14, color: tokens.color.onSurface, fontWeight: '600' },
  ruleEvidence: { fontSize: 12, color: tokens.color.onSurfaceMuted, marginTop: 2, lineHeight: 17 },
  step: { fontSize: 13, color: tokens.color.onSurface, lineHeight: 20 },
  muted: { fontSize: 13, color: tokens.color.onSurfaceMuted },

  statRow: { flexDirection: 'row', gap: 8, marginTop: 6 },
  statBox: { flex: 1, backgroundColor: tokens.color.surfaceTertiary, padding: 12, borderRadius: tokens.radius.md },
  statLabel: { fontSize: 11, color: tokens.color.onSurfaceMuted },
  statValue: { fontSize: 16, color: tokens.color.onSurface, fontWeight: '700', marginTop: 2 },

  sourceRow: { flexDirection: 'row', gap: 10, alignItems: 'flex-start', paddingVertical: 6 },
  sourceName: { fontSize: 13, color: tokens.color.onSurface, fontWeight: '600' },
  sourceNotes: { fontSize: 12, color: tokens.color.onSurface, marginTop: 2 },
  sourceMeta: { fontSize: 11, color: tokens.color.onSurfaceMuted, marginTop: 2 },

  pctBtn: { flex: 1, paddingVertical: 12, borderRadius: tokens.radius.md, borderWidth: 1, borderColor: tokens.color.border, alignItems: 'center', minHeight: tokens.touch.min, backgroundColor: tokens.color.surfaceTertiary },
  pctBtnActive: { backgroundColor: tokens.color.brand, borderColor: tokens.color.brand },
  pctBtnText: { color: tokens.color.onSurface, fontWeight: '600' },
  pctBtnTextActive: { color: tokens.color.onBrand },

  input: { marginTop: 12, backgroundColor: tokens.color.surfaceTertiary, borderRadius: tokens.radius.md, padding: 12, color: tokens.color.onSurface, minHeight: tokens.touch.min, borderWidth: 1, borderColor: tokens.color.border, fontSize: 14 },

  optionBtn: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: tokens.color.border, minHeight: tokens.touch.min },
  optionText: { fontSize: 15, color: tokens.color.onSurface, fontWeight: '500', flex: 1 },
  optionMeta: { fontSize: 11, color: tokens.color.onSurfaceMuted },

  timelineRow: { flexDirection: 'row', gap: 12, paddingVertical: 8 },
  timelineDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: tokens.color.brand, marginTop: 4 },
  timelineTitle: { fontSize: 14, color: tokens.color.onSurface, fontWeight: '600' },
  timelineMeta: { fontSize: 11, color: tokens.color.onSurfaceMuted, marginTop: 2 },
  timelineNote: { fontSize: 12, color: tokens.color.onSurfaceMuted, marginTop: 2 },
});
