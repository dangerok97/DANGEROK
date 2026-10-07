import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { AccessibilityInfo, AppState, Platform, Pressable, ScrollView, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { presencePalette as palette, presenceColors } from '@/src/theme/presence';
import { PresenceCanvas } from './PresenceCanvas';
import { AREA_LABELS, AREA_DETAILS, AREA_IDS, COMPLETED_FOCUS_MS, completionFocusKey, presenceFocus, type PresenceActivity, type PresenceMode, type PresenceNode } from './state';
import { useAuth } from '@/src/contexts/AuthContext';
import { openingSession } from './openingSession';
import { geometryFor, type KnowledgeMap } from './knowledge';
import { useKnowledgeMap } from './useKnowledgeMap';
import { useRouter } from 'expo-router';
import { OraCockpitContext } from '../OraCockpitContext';

export function OraPresence({ mode = 'idle', activity = null, compact = false, active = true,
  expanded = false, openingKey = null, footer, conversation, prominentConversation = false, onAreaPrompt, onBack, knowledge, knowledgeRefreshKey, spotlightId = null, cockpitChrome = false, onSelectNode, initialSelectedStarId = null, onKnowledgeChanged, knowledgeError = false }: {
  knowledge?: KnowledgeMap | null; knowledgeRefreshKey?: unknown;
  spotlightId?: string | null;
  cockpitChrome?: boolean;
  initialSelectedStarId?: string | null;
  onKnowledgeChanged?: () => void;
  knowledgeError?: boolean;
  onSelectNode?: (node: PresenceNode | null) => void;
  mode?: PresenceMode; activity?: PresenceActivity | null; compact?: boolean; active?: boolean;
  expanded?: boolean; openingKey?: string | null; footer?: React.ReactNode; conversation?: React.ReactNode; prominentConversation?: boolean; onAreaPrompt?: (prompt: string) => void; onBack?: () => void;
}) {
  const { width, height: windowHeight } = useWindowDimensions();
  const { user } = useAuth();
  const router = useRouter();
  const refreshKey = knowledgeRefreshKey ?? (activity?.phase === 'done' ? activity.request_id : null);
  const learned = useKnowledgeMap(user?.user_id, active && knowledge === undefined, refreshKey);
  const map = knowledge === undefined ? learned.data : knowledge;
  const stars = useMemo(() => geometryFor(map), [map]);
  const autoSpotlightId = useMemo(() => {
    if (spotlightId) return spotlightId;
    const addedTemporary = [...(learned.addedStars || [])]
      .filter((star) => star.temporary)
      .sort((a, b) => {
        const av = a.updated_at ? new Date(a.updated_at).getTime() : 0;
        const bv = b.updated_at ? new Date(b.updated_at).getTime() : 0;
        return bv - av;
      });
    if (addedTemporary[0]?.id) return addedTemporary[0].id;

    // A remount immediately after creation has no previous map to diff against.
    // In that narrow window, the newest temporary Situation is still the thing
    // the person just created and deserves the same visual focus.
    const recent = [...(map?.stars || [])]
      .filter((star) => star.temporary && star.updated_at)
      .sort((a, b) => new Date(b.updated_at || 0).getTime() - new Date(a.updated_at || 0).getTime())[0];
    if (!recent?.id || !recent.updated_at) return null;
    const age = Date.now() - new Date(recent.updated_at).getTime();
    return age >= 0 && age <= 120_000 ? recent.id : null;
  }, [spotlightId, learned.addedStars, map]);
  const [paused, setPaused] = useState(false);
  const [reduced, setReduced] = useState(true);
  const [motionReady, setMotionReady] = useState(false);
  const [opening, setOpening] = useState<string | null>(null);
  const [resolvedOpening, setResolvedOpening] = useState<string | null>(null);
  const [foreground, setForeground] = useState(AppState.currentState !== 'background');
  const [unavailable, setUnavailable] = useState(false);
  const [info, setInfo] = useState(false);
  const [areas, setAreas] = useState(false);
  const [selected, setSelected] = useState<PresenceNode | null>(null);
  const [resetKey, setResetKey] = useState(0);
  const [zoomOverride, setZoomOverride] = useState(1);
  const [panelHeight, setPanelHeight] = useState(windowHeight * .7);
  const [stageHeight, setStageHeight] = useState(windowHeight * .6);
  const [showConversation, setShowConversation] = useState(true);
  const [reading, setReading] = useState(false);
  const [expiredFocus, setExpiredFocus] = useState<string | null>(null);
  const completedFocus = completionFocusKey(activity);
  useEffect(() => {
    if (!completedFocus) return;
    const timer = setTimeout(() => setExpiredFocus(completedFocus), COMPLETED_FOCUS_MS);
    return () => clearTimeout(timer);
  }, [completedFocus]);
  const fail = useCallback(() => setUnavailable(true), []);
  const select = useCallback((node: PresenceNode | null) => {
    setSelected(node);
    setInfo(false);
    setAreas(false);
    onSelectNode?.(node);
  }, [onSelectNode]);
  const appliedInitialSelection = useRef<string | null>(null);
  useEffect(() => {
    if (!initialSelectedStarId) { appliedInitialSelection.current = null; return; }
    if (appliedInitialSelection.current === initialSelectedStarId) return;
    const index = stars.findIndex(star => star.id === initialSelectedStarId);
    if (index < 0) return;
    appliedInitialSelection.current = initialSelectedStarId;
    select({ index: index + 8, id: initialSelectedStarId, area: stars[index].area, kind: stars[index].kind });
  }, [initialSelectedStarId, stars, select]);
  const refreshKnowledge = useCallback(() => {
    if (knowledge === undefined) learned.reload();
    onKnowledgeChanged?.();
  }, [knowledge === undefined, learned.reload, onKnowledgeChanged]);
  useEffect(() => {
    if (selected?.id && map && !stars.some(star => star.id === selected.id)) select(null);
  }, [map, stars, selected?.id, select]);
  // A new working turn exposes its result even if the previous transcript was folded.
  useEffect(() => { if (mode === 'think') setShowConversation(true); }, [mode]);
  useEffect(() => {
    let alive = true;
    const app = AppState.addEventListener('change', state => setForeground(state === 'active'));
    const motion = AccessibilityInfo.addEventListener('reduceMotionChanged', setReduced);
    let media: MediaQueryList | undefined;
    const changed = () => { if (media) setReduced(media.matches); };
    if (Platform.OS === 'web' && typeof window !== 'undefined' && window.matchMedia) {
      media = window.matchMedia('(prefers-reduced-motion: reduce)'); changed(); media.addEventListener('change', changed);
      setMotionReady(true);
    } else {
      void AccessibilityInfo.isReduceMotionEnabled().then(value => { if (alive) setReduced(value); }).catch(() => {}).finally(() => { if (alive) setMotionReady(true); });
    }
    return () => { alive = false; app.remove(); motion.remove(); media?.removeEventListener('change', changed); };
  }, []);
  useLayoutEffect(() => {
    if (!openingKey || resolvedOpening === openingKey || !motionReady || !active || !foreground || !user) return;
    if (openingSession.claim(user.user_id, openingKey) && !reduced) setOpening(openingKey);
    setResolvedOpening(openingKey);
  }, [openingKey, resolvedOpening, motionReady, active, foreground, user, reduced]);
  // A Home handoff already has its first message. Resolve its entrance before
  // mounting the canvas, so the first visible frame is a point, not a full map.
  const canvasReady = motionReady && (!openingKey || resolvedOpening === openingKey);
  const area = presenceFocus(activity, mode, expiredFocus);
  const hasConversation = Boolean(conversation);
  const selectedGeometry = selected?.id ? stars.findIndex(s => s.id === selected.id) : -1;
  const selectedIndex = selected?.kind === 'area' ? selected.index : selectedGeometry >= 0 ? selectedGeometry + 8 : null;
  const options = useMemo(() => ({ stars, mode, area, paused, reduced, reveal: !!opening, revealKey: opening, active: active && foreground, selectedIndex: selectedIndex !== null && selectedIndex >= 0 ? selectedIndex : null, resetKey, centerY: expanded && hasConversation && showConversation ? .40 : .50, spotlightId: autoSpotlightId, zoomOverride }), [stars, mode, area, paused, reduced, opening, active, foreground, selectedIndex, resetKey, expanded, hasConversation, showConversation, autoSpotlightId, zoomOverride]);
  const caption = mode === 'listen' ? 'Ti ascolto' : mode === 'speak' ? 'Ti rispondo' : mode === 'think' ? 'Sto lavorando' : 'Sono qui';
  const label = caption + (area ? ` · ${AREA_LABELS[area]}` : '');
  const height = compact ? (windowHeight < 650 ? 128 : width < 650 ? 200 : 260) : Math.min(350, Math.max(240, windowHeight * .36));
  const tight = expanded && panelHeight < 390;
  const fact = map?.stars.find(s => s.id === selected?.id);
  useEffect(() => {
    if (!active || !foreground || !fact?.temporary) return;
    refreshKnowledge();
    const timer = setInterval(refreshKnowledge, 15000);
    return () => clearInterval(timer);
  }, [active, foreground, fact?.id, fact?.temporary, refreshKnowledge]);
  const branch = map?.branches.find(b => `branch_${b.area_id}` === selected?.id);
  const detail = selected ? AREA_DETAILS[selected.area] : null;
  const transcriptHeight = Math.max(60, reading ? stageHeight - 70 : prominentConversation ? Math.min(330, stageHeight - 70) : Math.min(164, panelHeight * .24));
  return <View style={[styles.root, expanded && styles.expanded]} testID="ora-presence" onLayout={event => setPanelHeight(event.nativeEvent.layout.height)}>
    {!cockpitChrome ? <>    <View style={[styles.top, width < 650 && styles.topMobile]}>
      <View style={styles.identity}>
        {onBack ? <Pressable accessibilityRole="button" accessibilityLabel="Indietro" onPress={onBack} style={styles.button}><Ionicons name="chevron-back" size={20} color={palette.muted} /></Pressable> : null}
        <View style={{ flexShrink: 1, minWidth: 0 }}>
          <Text accessibilityRole="header" style={styles.wordmark}>ORA</Text>
          <View style={styles.statusLine}><View style={styles.statusDot} /><Text accessibilityLiveRegion="polite" numberOfLines={1} style={[styles.caption, { maxWidth: width < 650 ? 108 : 260 }]} testID="ora-presence-state">{label}</Text></View>
        </View>
      </View>
      <View style={styles.actions}>
        <Pressable accessibilityRole="button" accessibilityLabel="Esplora le aree della mappa" accessibilityState={{ expanded: areas }} onPress={() => { setAreas(value => !value); setSelected(null); setInfo(false); }} style={styles.button}><Ionicons name="git-network-outline" size={18} color={palette.muted} />{width >= 650 ? <Text style={styles.control}>Aree</Text> : null}</Pressable>
        <Pressable accessibilityRole="button" accessibilityLabel="Centra la mappa" onPress={() => { setSelected(null); setResetKey(value => value + 1); }} style={styles.button}><Ionicons name="scan-outline" size={18} color={palette.muted} /></Pressable>
        {!reduced && !unavailable ? <Pressable accessibilityRole="button" accessibilityLabel={paused ? 'Riprendi animazione' : 'Metti in pausa animazione'} accessibilityState={{ selected: paused }} onPress={() => setPaused(value => !value)} style={styles.button}><Ionicons name={paused ? 'play-outline' : 'pause-outline'} size={18} color={palette.muted} /></Pressable> : null}
        <Pressable accessibilityRole="button" accessibilityLabel="Come funziona la rete di ORA" accessibilityState={{ expanded: info }} onPress={() => { setInfo(value => !value); setSelected(null); setAreas(false); }} style={styles.button}><Ionicons name="information-circle-outline" size={19} color={palette.muted} /></Pressable>
      </View>
    </View>

        <View style={styles.knowledgeStrip} testID="knowledge-map-progress">
      <Text style={styles.note} accessibilityLiveRegion="polite">{map ? `${map.count} stelle${map.temporary_count ? ` · ${map.temporary_count} temporanee` : ''} · VITA ${map.percent}%` : learned.error ? 'Mappa da aggiornare' : 'Carico le tue stelle…'}</Text>
      {knowledge === undefined && learned.error ? <Pressable accessibilityRole="button" accessibilityLabel="Riprova caricamento della mappa" onPress={learned.reload}><Text style={styles.control}>Riprova</Text></Pressable> : map && map.count === 0 ? <Text style={styles.note}>La prima stella nasce da ciò che mi racconti.</Text> : null}
    </View></> : null}
    <View style={expanded ? [styles.stage, tight && { minHeight: 0 }] : { height }} testID="ora-presence-map" onLayout={event => setStageHeight(event.nativeEvent.layout.height)}>
      {unavailable ? <View style={styles.fallback}><Text style={styles.fallbackText}>ORA</Text></View> : canvasReady ? <PresenceCanvas options={options} onUnavailable={fail} onSelect={select} /> : null}
      {areas || selected || info ? <View style={[styles.overlay, width < 650 && styles.overlayMobile]} testID="ora-map-detail">
          <View style={[styles.detailHead, { paddingHorizontal: 16 }]}>
            <Text accessibilityRole="header" style={styles.detailTitle}>{fact?.temporary ? 'Memoria temporanea' : fact ? 'Un punto della tua vita' : branch ? branch.title : selected ? AREA_LABELS[selected.area] : areas ? 'Esplora la mappa' : 'La tua mappa cresce con te'}</Text>
            <Pressable accessibilityRole="button" accessibilityLabel="Chiudi dettagli della mappa" onPress={() => { setSelected(null); setAreas(false); setInfo(false); }} style={styles.button}><Text style={styles.control}>Chiudi</Text></Pressable>
          </View>
        <ScrollView keyboardShouldPersistTaps="handled" style={{ minHeight: 0, flexShrink: 1 }} contentContainerStyle={styles.detailContent} testID="ora-map-detail-scroll">
          {areas ? <>
            <Text style={styles.note}>Ogni stella è un’informazione salvata. Scegli un’area per leggerle anche senza usare la mappa.</Text>
            <View style={styles.areaList}>{AREA_IDS.map((id, index) => <Pressable key={id} accessibilityRole="button" onPress={() => select({ index, area: id, kind: 'area' })} style={styles.areaButton}><Text style={styles.control}>{AREA_LABELS[id]} · {map?.stars.filter(s => s.area === id).length ?? 0}</Text></Pressable>)}</View>
          </> : fact?.temporary ? <OraCockpitContext
            key={fact.id} star={fact} standalone readError={knowledge === undefined ? learned.error : knowledgeError}
            onTemporaryChanged={() => { refreshKnowledge(); select(null); }}
          /> : fact ? <>
            <Text style={styles.detailText}>{fact.statement}</Text>
            <Text style={[styles.note, fact.temporary && styles.temporaryNote]}>
              {fact.temporary
                ? 'Memoria temporanea · resta finché la situazione è attiva'
                : `${fact.provenance} · ${fact.status === 'likely' ? 'Da verificare' : 'Informazione salvata'}`}
            </Text>
            {fact.updated_at ? <Text style={styles.note}>Aggiornato il {new Date(fact.updated_at).toLocaleDateString('it-IT')}</Text> : null}
            {fact.branch_id && !fact.temporary ? <Pressable accessibilityRole="button" style={styles.promptButton} onPress={() => router.push({ pathname: '/life-setup', params: { area: fact.branch_id } } as any)}><Text style={styles.promptText}>Apri in VITA ↗</Text></Pressable> : null}
          </> : branch ? <>
            <Text style={styles.detailText}>{branch.purpose}</Text>
            <Text style={styles.activity}>{branch.star_count} stelle · {branch.percent}% · {branch.complete ? 'Ramo completato' : branch.state_label}</Text>
            <Pressable accessibilityRole="button" style={styles.promptButton} onPress={() => router.push({ pathname: '/life-setup', params: { area: branch.area_id } } as any)}><Text style={styles.promptText}>Continua in VITA ↗</Text></Pressable>
          </> : selected && detail ? <>
            <Text style={styles.detailText}>{detail.description}</Text>
            {activity?.touched.includes(selected.area) ? <Text style={styles.activity}>Area coinvolta nell’ultimo turno.</Text> : null}
            {map?.branches.filter(b => b.area === selected.area && b.star_count > 0).map(b => <Pressable key={b.area_id} accessibilityRole="button" style={styles.areaButton} onPress={() => select({ index: 8 + stars.findIndex(s => s.id === `branch_${b.area_id}`), id: `branch_${b.area_id}`, area: b.area, kind: 'branch' })}><Text style={styles.control}>{b.complete ? '✦ ' : ''}{b.title} · {b.percent}%</Text></Pressable>)}
            {map?.stars.filter(s => s.area === selected.area).map(s => <Pressable key={s.id} accessibilityRole="button" style={styles.starRow} onPress={() => select({ index: 8 + stars.findIndex(n => n.id === s.id), id: s.id, area: s.area, kind: 'node' })}><Text numberOfLines={2} style={styles.detailText}>✦ {s.statement}</Text><Text style={styles.note}>{s.status === 'likely' ? 'Da verificare' : s.provenance}</Text></Pressable>)}
            {!map?.stars.some(s => s.area === selected.area) ? <Text style={styles.note}>Non ci sono ancora informazioni salvate in quest’area.</Text> : null}
            {onAreaPrompt ? <Pressable accessibilityRole="button" onPress={() => { onAreaPrompt(detail.prompt); setSelected(null); }} style={styles.promptButton}><Text style={styles.promptText}>Parliamone ↗</Text></Pressable> : null}
          </> : <Text style={styles.detailText}>Ogni stella rappresenta qualcosa che ORA sta tenendo presente. Le stelle normali sono informazioni salvate nel profilo o in memoria; le stelle rosse sono memorie temporanee legate a situazioni ancora attive e spariscono quando la situazione viene risolta o annullata. Le informazioni da verificare hanno una luce ambrata. Un alone segnala i rami completati in VITA. Il conteggio delle stelle e la percentuale di VITA misurano cose diverse: informazioni presenti nella mappa e completezza delle aree. I collegamenti mostrano come le informazioni si raggruppano; il movimento segue il tema della conversazione, non il ragionamento interno del modello. Trascina per ruotare, anche in pausa.</Text>}

        </ScrollView>
      </View> : null}
      {cockpitChrome ? <>
        <View style={styles.cockpitBrandPill} pointerEvents="none">
          <View style={styles.cockpitBrandOrb}><View style={styles.cockpitBrandCore} /></View>
          <View>
            <Text style={styles.cockpitBrandName}>ORA</Text>
            <Text style={styles.cockpitBrandSub}>SEMPRE CON TE</Text>
          </View>
        </View>
        <View style={styles.cockpitMapControls}>
          <Pressable accessibilityRole="button" accessibilityLabel="Centra la mappa" onPress={() => { setSelected(null); onSelectNode?.(null); setResetKey(value => value + 1); }} style={styles.cockpitControlButton}>
            <Ionicons name="locate-outline" size={18} color={palette.label} />
          </Pressable>
          <Pressable accessibilityRole="button" accessibilityLabel="Riduci zoom" onPress={() => setZoomOverride(value => Math.max(.72, Math.round((value - .12) * 100) / 100))} style={styles.cockpitControlButton}>
            <Ionicons name="remove" size={18} color={palette.label} />
          </Pressable>
          <Pressable accessibilityRole="button" accessibilityLabel="Aumenta zoom" onPress={() => setZoomOverride(value => Math.min(1.55, Math.round((value + .12) * 100) / 100))} style={styles.cockpitControlButton}>
            <Ionicons name="add" size={18} color={palette.label} />
          </Pressable>
          <Pressable accessibilityRole="button" accessibilityLabel="Ripristina vista 3D" onPress={() => { setZoomOverride(1); setResetKey(value => value + 1); }} style={styles.cockpit3dButton}>
            <Text style={styles.cockpit3dText}>3D</Text>
          </Pressable>
        </View>
      </> : null}
      {conversation && !tight ? <View style={styles.transcriptPosition} pointerEvents="box-none">
        {showConversation ? <View style={[styles.transcriptCard, { maxHeight: Math.max(0, stageHeight - 12) }]}>
          <View style={styles.transcriptHead}>
            <Text style={styles.transcriptLabel}>CONVERSAZIONE</Text>
            <View style={styles.actions}>
              <Pressable accessibilityRole="button" accessibilityLabel={reading ? 'Riduci conversazione' : 'Amplia conversazione'} accessibilityState={{ expanded: reading }} onPress={() => setReading(value => !value)} style={styles.button}><Ionicons name={reading ? 'contract-outline' : 'expand-outline'} size={16} color={palette.muted} /></Pressable>
              <Pressable accessibilityRole="button" accessibilityLabel="Nascondi conversazione" onPress={() => setShowConversation(false)} style={styles.button}><Ionicons name="chevron-down" size={18} color={palette.muted} /></Pressable>
            </View>
          </View>
          <View style={{ height: transcriptHeight, flexShrink: 1 }} testID="ora-presence-conversation">{conversation}</View>
        </View> : <Pressable accessibilityRole="button" accessibilityLabel="Mostra conversazione" onPress={() => setShowConversation(true)} style={styles.showMessages}><Ionicons name="chatbubble-outline" size={15} color={palette.muted} /><Text style={styles.control}>Mostra conversazione</Text></Pressable>}
      </View> : null}
    </View>
    {footer ? <View style={[styles.footer, width < 650 && styles.footerMobile]} testID="ora-presence-footer">{footer}</View> : null}
  </View>;
}
const styles = StyleSheet.create({
  knowledgeStrip: { flexDirection: 'row', flexWrap: 'wrap', gap: 12, justifyContent: 'space-between', paddingHorizontal: 20, paddingBottom: 8 },
  starRow: { paddingVertical: 12, gap: 4, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: palette.border },
  root: { width: '100%', borderRadius: 20, overflow: 'hidden', backgroundColor: palette.background },
  expanded: { flex: 1, minHeight: 0, borderRadius: 0 }, stage: { flex: 1, minHeight: 64, position: 'relative' },
  top: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 32, paddingTop: 18, paddingBottom: 10, minHeight: 78 },
  topMobile: { paddingHorizontal: 12, paddingTop: 6, paddingBottom: 4, minHeight: 64 },
  identity: { flexDirection: 'row', alignItems: 'center', gap: 4, flexShrink: 1 },
  wordmark: { fontSize: 19, letterSpacing: 4, color: palette.text, fontWeight: '500' },
  statusLine: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 6 }, statusDot: { width: 4, height: 4, borderRadius: 2, backgroundColor: palette.label },
  actions: { flexDirection: 'row', alignItems: 'center', gap: 2 }, button: { minWidth: 44, minHeight: 44, flexDirection: 'row', gap: 8, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 8 },
  control: { fontSize: 12, color: palette.muted }, caption: { fontSize: 11, color: palette.muted },
  footer: { paddingHorizontal: 32, paddingBottom: 24, paddingTop: 6, zIndex: 10 }, footerMobile: { paddingHorizontal: 12, paddingBottom: 12 },
  transcriptPosition: { position: 'absolute', bottom: 6, left: 12, right: 12, alignItems: 'center' },
  transcriptCard: { width: '100%', maxWidth: 836, borderRadius: 20, borderWidth: StyleSheet.hairlineWidth, borderColor: palette.border, backgroundColor: presenceColors.surfaceGlass, overflow: 'hidden' },
  transcriptHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingLeft: 20, paddingRight: 6, minHeight: 44 },
  transcriptLabel: { color: palette.muted, fontSize: 9, letterSpacing: 1.8 },
  showMessages: { minHeight: 44, flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 16, borderRadius: 22, backgroundColor: presenceColors.surfaceGlass, borderColor: palette.border, borderWidth: StyleSheet.hairlineWidth },
  overlay: { position: 'absolute', top: 8, right: 24, width: 330, maxHeight: '90%', backgroundColor: palette.atmosphere, borderWidth: 1, borderColor: palette.border, borderRadius: 18, zIndex: 20, overflow: 'hidden' },
  overlayMobile: { left: 12, right: 12, width: 'auto' }, detailContent: { padding: 16, paddingTop: 4, gap: 8 },
  detailHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  detailTitle: { flex: 1, fontSize: 16, fontWeight: '500', color: palette.text }, detailText: { fontSize: 14, lineHeight: 21, color: palette.text },
  note: { fontSize: 12, lineHeight: 18, color: palette.muted }, activity: { fontSize: 12, color: palette.warmLabel },
  temporaryNote: { color: '#ff6b6b' },
  areaList: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 }, areaButton: { minHeight: 44, paddingHorizontal: 12, justifyContent: 'center', borderWidth: 1, borderColor: palette.border, borderRadius: 12 },
  promptButton: { minHeight: 44, alignSelf: 'flex-start', justifyContent: 'center', paddingHorizontal: 14, backgroundColor: palette.border, borderRadius: 12 }, promptText: { color: palette.text, fontSize: 13 },
  cockpitBrandPill: {
    position: 'absolute', left: '50%', bottom: 22, transform: [{ translateX: -120 }],
    minWidth: 240, height: 58, borderRadius: 30, borderWidth: StyleSheet.hairlineWidth,
    borderColor: 'rgba(122,209,235,.28)', backgroundColor: 'rgba(5,18,28,.88)',
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10, zIndex: 12,
  },
  cockpitBrandOrb: {
    width: 34, height: 34, borderRadius: 17, borderWidth: 1,
    borderColor: 'rgba(137,225,255,.65)', backgroundColor: 'rgba(92,193,228,.08)',
    alignItems: 'center', justifyContent: 'center', shadowColor: '#77dcff', shadowOpacity: .7, shadowRadius: 10,
  },
  cockpitBrandCore: { width: 13, height: 13, borderRadius: 7, borderWidth: 2, borderColor: '#c7f5ff' },
  cockpitBrandName: { color: '#bff0fb', fontSize: 16, letterSpacing: 3 },
  cockpitBrandSub: { color: '#4f8195', fontSize: 8, letterSpacing: 1.1 },
  cockpitMapControls: {
    position: 'absolute', right: 18, bottom: 24, flexDirection: 'row', alignItems: 'center',
    borderRadius: 22, borderWidth: StyleSheet.hairlineWidth, borderColor: 'rgba(122,196,220,.25)',
    backgroundColor: 'rgba(5,16,25,.88)', overflow: 'hidden', zIndex: 12,
  },
  cockpitControlButton: {
    width: 42, height: 42, alignItems: 'center', justifyContent: 'center',
    borderRightWidth: StyleSheet.hairlineWidth, borderRightColor: 'rgba(122,196,220,.18)',
  },
  cockpit3dButton: { minWidth: 48, height: 42, alignItems: 'center', justifyContent: 'center' },
  cockpit3dText: { color: palette.label, fontSize: 12, fontWeight: '700' },
  fallback: { flex: 1, alignItems: 'center', justifyContent: 'center' }, fallbackText: { fontSize: 24, letterSpacing: 4, color: palette.text },
});
