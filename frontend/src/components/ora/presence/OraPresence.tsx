import React, { useCallback, useEffect, useLayoutEffect, useMemo, useState } from 'react';
import { AccessibilityInfo, AppState, Platform, Pressable, ScrollView, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { presencePalette as palette, presenceColors } from '@/src/theme/presence';
import { PresenceCanvas } from './PresenceCanvas';
import { AREA_LABELS, AREA_DETAILS, AREA_IDS, type PresenceActivity, type PresenceMode, type PresenceNode } from './state';
import { useAuth } from '@/src/contexts/AuthContext';
import { openingSession } from './openingSession';

export function OraPresence({ mode = 'idle', activity = null, compact = false, active = true,
  expanded = false, openingKey = null, footer, conversation, onAreaPrompt, onBack }: {
  mode?: PresenceMode; activity?: PresenceActivity | null; compact?: boolean; active?: boolean;
  expanded?: boolean; openingKey?: string | null; footer?: React.ReactNode; conversation?: React.ReactNode; onAreaPrompt?: (prompt: string) => void; onBack?: () => void;
}) {
  const { width, height: windowHeight } = useWindowDimensions();
  const { user } = useAuth();
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
  const [panelHeight, setPanelHeight] = useState(windowHeight * .7);
  const [stageHeight, setStageHeight] = useState(windowHeight * .6);
  const [showConversation, setShowConversation] = useState(true);
  const [reading, setReading] = useState(false);
  const fail = useCallback(() => setUnavailable(true), []);
  const select = useCallback((node: PresenceNode | null) => { setSelected(node); setInfo(false); setAreas(false); }, []);
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
  const working = mode === 'think' || mode === 'speak';
  const area = working && activity?.phase !== 'error' ? activity?.area || null : null;
  const hasConversation = Boolean(conversation);
  const options = useMemo(() => ({ mode, area, paused, reduced, reveal: !!opening, revealKey: opening, active: active && foreground, selectedIndex: selected?.index ?? null, resetKey, centerY: expanded && hasConversation && showConversation ? .40 : .50 }), [mode, area, paused, reduced, opening, active, foreground, selected, resetKey, expanded, hasConversation, showConversation]);
  const caption = mode === 'listen' ? 'Ti ascolto' : mode === 'speak' ? 'Ti rispondo' : mode === 'think' ? 'Sto lavorando' : 'Sono qui';
  const label = caption + (area ? ` · ${AREA_LABELS[area]}` : '');
  const height = compact ? (windowHeight < 650 ? 128 : width < 650 ? 200 : 260) : Math.min(350, Math.max(240, windowHeight * .36));
  const tight = expanded && panelHeight < 390;
  const detail = selected ? AREA_DETAILS[selected.area] : null;
  const transcriptHeight = Math.max(60, reading ? stageHeight - 70 : Math.min(164, panelHeight * .24));
  return <View style={[styles.root, expanded && styles.expanded]} testID="ora-presence" onLayout={event => setPanelHeight(event.nativeEvent.layout.height)}>
    <View style={[styles.top, width < 650 && styles.topMobile]}>
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
    <View style={expanded ? [styles.stage, tight && { minHeight: 0 }] : { height }} testID="ora-presence-map" onLayout={event => setStageHeight(event.nativeEvent.layout.height)}>
      {unavailable ? <View style={styles.fallback}><Text style={styles.fallbackText}>ORA</Text></View> : canvasReady ? <PresenceCanvas options={options} onUnavailable={fail} onSelect={select} /> : null}
      {areas || selected || info ? <View style={[styles.overlay, width < 650 && styles.overlayMobile]}>
        <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={styles.detailContent}>
          <View style={styles.detailHead}>
            <Text accessibilityRole="header" style={styles.detailTitle}>{selected ? AREA_LABELS[selected.area] : areas ? 'Esplora la mappa' : 'Una mappa del tuo contesto'}</Text>
            <Pressable accessibilityRole="button" accessibilityLabel="Chiudi dettagli della mappa" onPress={() => { setSelected(null); setAreas(false); setInfo(false); }} style={styles.button}><Text style={styles.control}>Chiudi</Text></Pressable>
          </View>
          {areas ? <View style={styles.areaList}>{AREA_IDS.map((id, index) => <Pressable key={id} accessibilityRole="button" onPress={() => select({ index, area: id, kind: 'area' })} style={styles.areaButton}><Text style={styles.control}>{AREA_LABELS[id]}</Text></Pressable>)}</View> : selected && detail ? <>
            <Text style={styles.detailText}>{detail.description}</Text>
            <Text style={styles.note}>{selected.kind === 'connection' ? 'Collegamento visivo vicino a quest’area.' : 'Nodo illustrativo di quest’area.'} Non è un singolo dato personale.</Text>
            {activity?.touched.includes(selected.area) ? <Text style={styles.activity}>Area coinvolta nell’ultimo turno.</Text> : null}
            {onAreaPrompt ? <Pressable accessibilityRole="button" onPress={() => { onAreaPrompt(detail.prompt); setSelected(null); }} style={styles.promptButton}><Text style={styles.promptText}>Parliamone ↗</Text></Pressable> : null}
          </> : <Text style={styles.detailText}>Le aree seguono le informazioni consultate e gli strumenti usati in questa conversazione. Punti e filamenti rappresentano visivamente i collegamenti; non sono i neuroni del modello. Trascina per ruotare, anche in pausa. Tocca un nodo per esplorarlo.</Text>}
        </ScrollView>
      </View> : null}
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
  overlay: { position: 'absolute', top: 8, right: 24, width: 330, maxHeight: '90%', backgroundColor: palette.atmosphere, borderWidth: 1, borderColor: palette.border, borderRadius: 18, zIndex: 20 },
  overlayMobile: { left: 12, right: 12, width: 'auto' }, detailContent: { padding: 16, paddingTop: 4, gap: 8 },
  detailHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  detailTitle: { flex: 1, fontSize: 16, fontWeight: '500', color: palette.text }, detailText: { fontSize: 14, lineHeight: 21, color: palette.text },
  note: { fontSize: 12, lineHeight: 18, color: palette.muted }, activity: { fontSize: 12, color: palette.warmLabel },
  areaList: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 }, areaButton: { minHeight: 44, paddingHorizontal: 12, justifyContent: 'center', borderWidth: 1, borderColor: palette.border, borderRadius: 12 },
  promptButton: { minHeight: 44, alignSelf: 'flex-start', justifyContent: 'center', paddingHorizontal: 14, backgroundColor: palette.border, borderRadius: 12 }, promptText: { color: palette.text, fontSize: 13 },
  fallback: { flex: 1, alignItems: 'center', justifyContent: 'center' }, fallbackText: { fontSize: 24, letterSpacing: 4, color: palette.text },
});
