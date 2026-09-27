import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { AccessibilityInfo, AppState, Platform, Pressable, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import { presencePalette as palette } from '@/src/theme/presence';
import { PresenceCanvas } from './PresenceCanvas';
import { AREA_LABELS, type PresenceActivity, type PresenceMode } from './state';

export function OraPresence({ mode = 'idle', activity = null, compact = false, active = true }: {
  mode?: PresenceMode; activity?: PresenceActivity | null; compact?: boolean; active?: boolean;
}) {
  const { width, height: windowHeight } = useWindowDimensions();
  const [paused, setPaused] = useState(false);
  const [reduced, setReduced] = useState(true);
  const [foreground, setForeground] = useState(AppState.currentState !== 'background');
  const [unavailable, setUnavailable] = useState(false);
  const [info, setInfo] = useState(false);
  const fail = useCallback(() => setUnavailable(true), []);
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
  const options = useMemo(() => ({ mode, area, paused, reduced, active: active && foreground }), [mode, area, paused, reduced, active, foreground]);
  const caption = mode === 'listen' ? 'Ti ascolto' : mode === 'speak' ? 'Ti rispondo' : mode === 'think' ? 'Sto lavorando' : 'Sono qui';
  const label = caption + (area ? ` · ${AREA_LABELS[area]}` : '');
  const height = compact ? (windowHeight < 650 ? 128 : width < 650 ? 200 : 260) : Math.min(350, Math.max(240, windowHeight * .36));
  return <View style={styles.root} testID="ora-presence">
    <View style={styles.top}>
      <Text style={styles.wordmark}>ORA <Text style={styles.submark}>/ PRESENZA</Text></Text>
      <View style={styles.actions}>
        <Pressable accessibilityRole="button" accessibilityLabel="Come funziona la rete di ORA" accessibilityState={{ expanded: info }} onPress={() => setInfo(value => !value)} style={styles.button}><Text style={styles.control}>Info</Text></Pressable>
        {!reduced && !unavailable ? <Pressable accessibilityRole="button" accessibilityLabel={paused ? 'Riprendi animazione' : 'Metti in pausa animazione'} accessibilityState={{ selected: paused }} onPress={() => setPaused(value => !value)} style={styles.button}><Text style={styles.control}>{paused ? 'Riprendi' : 'Pausa'}</Text></Pressable> : null}
      </View>
    </View>
    <View style={{ height }}>
      {unavailable ? <View style={styles.fallback}><Text style={styles.fallbackText}>ORA</Text></View> : <PresenceCanvas options={options} onUnavailable={fail} />}
    </View>
    <Text accessibilityLiveRegion="polite" style={styles.caption} testID="ora-presence-state">{label}</Text>
    {info ? <Text style={styles.info}>Le aree seguono le informazioni consultate e gli strumenti usati in questa conversazione. Punti e filamenti rappresentano visivamente i collegamenti; non sono i neuroni del modello. Il battito accompagna il lavoro e non misura la voce.</Text> : null}
  </View>;
}
const styles = StyleSheet.create({
  root: { width: '100%', borderRadius: 20, overflow: 'hidden', backgroundColor: palette.background },
  top: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingLeft: 18, paddingRight: 8, minHeight: 44 },
  wordmark: { fontSize: 14, letterSpacing: 2.4, color: palette.text, fontWeight: '500' },
  submark: { fontSize: 9, letterSpacing: 1.5, color: palette.muted },
  actions: { flexDirection: 'row' }, button: { minWidth: 44, minHeight: 44, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 10 },
  control: { fontSize: 11, color: palette.muted }, caption: { fontSize: 13, color: palette.text, textAlign: 'center', paddingTop: 2, paddingBottom: 16 },
  info: { fontSize: 12, lineHeight: 18, color: palette.muted, paddingHorizontal: 18, paddingBottom: 18 },
  fallback: { flex: 1, alignItems: 'center', justifyContent: 'center' }, fallbackText: { fontSize: 24, letterSpacing: 4, color: palette.text },
});
