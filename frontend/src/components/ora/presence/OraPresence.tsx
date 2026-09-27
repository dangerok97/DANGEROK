import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { AccessibilityInfo, AppState, Platform, Pressable, ScrollView, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import { presencePalette as palette } from '@/src/theme/presence';
import { PresenceCanvas } from './PresenceCanvas';
import { AREA_LABELS, AREA_DETAILS, AREA_IDS, type PresenceActivity, type PresenceMode, type PresenceNode } from './state';

export function OraPresence({ mode = 'idle', activity = null, compact = false, active = true,
  expanded = false, footer, conversation, onAreaPrompt }: {
  mode?: PresenceMode; activity?: PresenceActivity | null; compact?: boolean; active?: boolean;
  expanded?: boolean; footer?: React.ReactNode; conversation?: React.ReactNode; onAreaPrompt?: (prompt: string) => void;
}) {
  const { width, height: windowHeight } = useWindowDimensions();
  const [paused, setPaused] = useState(false);
  const [reduced, setReduced] = useState(true);
  const [foreground, setForeground] = useState(AppState.currentState !== 'background');
  const [unavailable, setUnavailable] = useState(false);
  const [info, setInfo] = useState(false);
  const [areas, setAreas] = useState(false);
  const [selected, setSelected] = useState<PresenceNode | null>(null);
  const [resetKey, setResetKey] = useState(0);
  const [panelHeight, setPanelHeight] = useState(windowHeight * .7);
  const [showConversation, setShowConversation] = useState(true);
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
    } else {
      void AccessibilityInfo.isReduceMotionEnabled().then(value => { if (alive) setReduced(value); }).catch(() => {});
    }
    return () => { alive = false; app.remove(); motion.remove(); media?.removeEventListener('change', changed); };
  }, []);
  const working = mode === 'think' || mode === 'speak';
  const area = working && activity?.phase !== 'error' ? activity?.area || null : null;
  const options = useMemo(() => ({ mode, area, paused, reduced, active: active && foreground, selectedIndex: selected?.index ?? null, resetKey }), [mode, area, paused, reduced, active, foreground, selected, resetKey]);
  const caption = mode === 'listen' ? 'Ti ascolto' : mode === 'speak' ? 'Ti rispondo' : mode === 'think' ? 'Sto lavorando' : 'Sono qui';
  const label = caption + (area ? ` · ${AREA_LABELS[area]}` : '');
  const height = compact ? (windowHeight < 650 ? 128 : width < 650 ? 200 : 260) : Math.min(350, Math.max(240, windowHeight * .36));
  const tight = expanded && panelHeight < 390;
  const detail = selected ? AREA_DETAILS[selected.area] : null;
  return <View style={[styles.root, expanded && styles.expanded]} testID="ora-presence" onLayout={event => setPanelHeight(event.nativeEvent.layout.height)}>
    <View style={styles.top}>
      <Text style={styles.wordmark}>ORA <Text style={styles.submark}>/ PRESENZA</Text></Text>
      <View style={styles.actions}>
        <Pressable accessibilityRole="button" accessibilityLabel="Esplora le aree della mappa" accessibilityState={{ expanded: areas }} onPress={() => { setAreas(value => !value); setSelected(null); setInfo(false); }} style={styles.button}><Text style={styles.control}>Aree</Text></Pressable>
        <Pressable accessibilityRole="button" accessibilityLabel="Centra la mappa" onPress={() => { setSelected(null); setResetKey(value => value + 1); }} style={styles.button}><Text style={styles.control}>Centra</Text></Pressable>
        {!reduced && !unavailable ? <Pressable accessibilityRole="button" accessibilityLabel={paused ? 'Riprendi animazione' : 'Metti in pausa animazione'} accessibilityState={{ selected: paused }} onPress={() => setPaused(value => !value)} style={styles.button}><Text style={styles.control}>{paused ? 'Riprendi' : 'Pausa'}</Text></Pressable> : null}
      </View>
    </View>
    <View style={expanded ? [styles.stage, tight && { minHeight: 0 }] : { height }} testID="ora-presence-map">
      {unavailable ? <View style={styles.fallback}><Text style={styles.fallbackText}>ORA</Text></View> : <PresenceCanvas options={options} onUnavailable={fail} onSelect={select} />}
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
    </View>
    {!tight ? <View style={styles.status}>
      <View style={styles.statusText}>
        <Text accessibilityLiveRegion="polite" style={styles.caption} testID="ora-presence-state">{label}</Text>
        {expanded && panelHeight > 430 ? <Text style={styles.hint}>{paused ? 'In pausa · ' : ''}Trascina per ruotare · Tocca i nodi</Text> : null}
      </View>
      <Pressable accessibilityRole="button" accessibilityLabel="Come funziona la rete di ORA" accessibilityState={{ expanded: info }} onPress={() => { setInfo(value => !value); setSelected(null); setAreas(false); }} style={styles.button}><Text style={styles.control}>Info</Text></Pressable>
    </View> : null}
    {conversation && !tight ? <>
      <Pressable accessibilityRole="button" accessibilityState={{ expanded: showConversation }} accessibilityLabel={showConversation ? 'Nascondi conversazione' : 'Mostra conversazione'} onPress={() => setShowConversation(value => !value)} style={styles.transcriptToggle}><Text style={styles.control}>{showConversation ? 'Conversazione  −' : 'Mostra conversazione  +'}</Text></Pressable>
      {showConversation ? <View style={{ height: Math.max(80, Math.min(240, panelHeight * .3)), flexShrink: 1 }} testID="ora-presence-conversation">{conversation}</View> : null}
    </> : null}
    {footer ? <View style={styles.footer} testID="ora-presence-footer">{footer}</View> : null}
  </View>;
}
const styles = StyleSheet.create({
  root: { width: '100%', borderRadius: 20, overflow: 'hidden', backgroundColor: palette.background },
  expanded: { flex: 1, minHeight: 0 }, stage: { flex: 1, minHeight: 64, position: 'relative' },
  top: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingLeft: 16, paddingRight: 6, minHeight: 44 },
  wordmark: { fontSize: 13, letterSpacing: 2, color: palette.text, fontWeight: '500' },
  submark: { fontSize: 9, letterSpacing: 1, color: palette.muted },
  actions: { flexDirection: 'row' }, button: { minWidth: 44, minHeight: 44, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 8 },
  control: { fontSize: 12, color: palette.muted }, caption: { fontSize: 13, color: palette.text },
  status: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16 }, statusText: { flex: 1, gap: 3 },
  hint: { fontSize: 11, color: palette.muted }, footer: { paddingHorizontal: 12, paddingBottom: 8, zIndex: 10 },
  transcriptToggle: { minHeight: 44, justifyContent: 'center', paddingHorizontal: 18, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: palette.border },
  overlay: { position: 'absolute', top: 8, right: 12, width: 330, maxHeight: '95%', backgroundColor: palette.atmosphere, borderWidth: 1, borderColor: palette.border, borderRadius: 16 },
  overlayMobile: { left: 12, width: 'auto' }, detailContent: { padding: 14, paddingTop: 4, gap: 8 },
  detailHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  detailTitle: { flex: 1, fontSize: 16, fontWeight: '500', color: palette.text }, detailText: { fontSize: 14, lineHeight: 21, color: palette.text },
  note: { fontSize: 12, lineHeight: 18, color: palette.muted }, activity: { fontSize: 12, color: palette.warmLabel },
  areaList: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 }, areaButton: { minHeight: 44, paddingHorizontal: 12, justifyContent: 'center', borderWidth: 1, borderColor: palette.border, borderRadius: 12 },
  promptButton: { minHeight: 44, alignSelf: 'flex-start', justifyContent: 'center', paddingHorizontal: 14, backgroundColor: palette.border, borderRadius: 12 }, promptText: { color: palette.text, fontSize: 13 },
  fallback: { flex: 1, alignItems: 'center', justifyContent: 'center' }, fallbackText: { fontSize: 24, letterSpacing: 4, color: palette.text },
});
