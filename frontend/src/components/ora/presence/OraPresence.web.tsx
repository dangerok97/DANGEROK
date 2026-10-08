import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { AccessibilityInfo, AppState, Keyboard, Modal, Pressable, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
// Explicit extension is intentional: do not resolve this platform wrapper recursively.
import { OraPresence as StandardPresence } from './OraPresence.tsx';
import { PresenceCanvas } from './PresenceCanvas';
import { geometryFor } from './knowledge';
import { useKnowledgeMap } from './useKnowledgeMap';
import { useAuth } from '@/src/contexts/AuthContext';
import { presencePalette as palette } from '@/src/theme/presence';
import { AREA_LABELS, presenceFocus, type PresenceNode } from './state';
import { openingSession } from './openingSession';
import { useConversationViewport } from './useConversationViewport';
import { mobileConversationLayout } from './mobileConversationLayout';

type Props = React.ComponentProps<typeof StandardPresence>;

/** Desktop and non-conversation maps retain their existing renderer/lifecycle.
 * On mobile web, the actual conversation and composer are sibling layout slots,
 * never an absolute overlay on the map. No second session or send path is created.
 */
export function OraPresence(props: Props) {
  const { width } = useWindowDimensions();
  if (props.expanded && props.footer && width < 1120) {
    return <MobilePresenceConversation {...props} />;
  }
  return <StandardPresence {...props} />;
}

function MobilePresenceConversation({
  mode = 'idle', activity = null, active = true, openingKey = null,
  conversation, footer, onBack, onAreaPrompt, knowledge, knowledgeRefreshKey,
  spotlightId: requestedSpotlight = null,
  spotlightRef: requestedSpotlightRef = null,
}: Props) {
  const { user } = useAuth();
  const insets = useSafeAreaInsets();
  const root = useRef<View>(null);
  const viewport = useConversationViewport(root, insets.bottom);
  const { height: windowHeight } = useWindowDimensions();
  const [measuredHeight, setMeasuredHeight] = useState(windowHeight);
  const [mapOpen, setMapOpen] = useState(false);
  const [foreground, setForeground] = useState(AppState.currentState !== 'background');
  const [reduced, setReduced] = useState(true);
  const [canvasFailed, setCanvasFailed] = useState(false);
  const [revealKey, setRevealKey] = useState<string | null>(null);
  const [spotlight, setSpotlight] = useState<string | null>(null);
  const [inspection, setInspection] = useState<string | null>(null);
  const refreshKey = knowledgeRefreshKey ?? `${activity?.request_id || ''}:${activity?.phase || ''}:${mode}`;
  const learned = useKnowledgeMap(user?.user_id, active && knowledge === undefined, refreshKey);
  const map = knowledge === undefined ? learned.data : knowledge;
  const stars = useMemo(() => geometryFor(map), [map]);
  const area = presenceFocus(activity, mode, null);
  const preview = mobileConversationLayout(Math.min(measuredHeight, viewport.maxHeight ?? measuredHeight), viewport.editing);

  useEffect(() => {
    const app = AppState.addEventListener('change', state => setForeground(state === 'active'));
    const media = typeof window !== 'undefined' ? window.matchMedia?.('(prefers-reduced-motion: reduce)') : null;
    const updateMotion = () => setReduced(media?.matches ?? true);
    updateMotion();
    media?.addEventListener('change', updateMotion);
    const motion = AccessibilityInfo.addEventListener('reduceMotionChanged', setReduced);
    return () => { app.remove(); media?.removeEventListener('change', updateMotion); motion.remove(); };
  }, []);

  useLayoutEffect(() => {
    if (openingKey && user && active && foreground && !reduced && openingSession.claim(user.user_id, openingKey)) {
      setRevealKey(openingKey);
    }
  }, [openingKey, user, active, foreground, reduced]);

  const candidate = useMemo(() => {
    if (requestedSpotlight && map?.stars.some(star => star.id === requestedSpotlight)) return requestedSpotlight;
    if (requestedSpotlightRef) {
      const byRef = map?.stars.find(star => (star.source_refs || []).includes(requestedSpotlightRef));
      if (byRef?.id) return byRef.id;
    }
    const changed = [...learned.changedStars]
      .sort((a, b) => Date.parse(b.updated_at || '') - Date.parse(a.updated_at || ''));
    if (changed[0]) return changed[0].id;
    const recent = [...(map?.stars || [])].filter(star => star.updated_at)
      .sort((a, b) => Date.parse(b.updated_at || '') - Date.parse(a.updated_at || ''))[0];
    const age = recent ? Date.now() - Date.parse(recent.updated_at || '') : Infinity;
    return age >= 0 && age < 120000 ? recent?.id || null : null;
  }, [requestedSpotlight, requestedSpotlightRef, learned.changedStars, map]);

  useEffect(() => {
    if (!candidate) { setSpotlight(null); return; }
    // A newly created/updated/talked-about star owns the visual focus. Drop an
    // older inspected point so the expanded map cannot keep the camera pinned.
    setInspection(null);
    setSpotlight(candidate);
    const timer = setTimeout(() => setSpotlight(null), 8000);
    return () => clearTimeout(timer);
  }, [candidate, refreshKey]);

  useEffect(() => {
    if (viewport.editing || mode === 'think' || mode === 'listen') setMapOpen(false);
  }, [viewport.editing, mode]);

  const highlighted = map?.stars.find(star => star.id === spotlight);
  const inspected = map?.stars.find(star => star.id === inspection);
  const caption = mode === 'think' ? 'Sto lavorando' : mode === 'listen' ? 'Ti ascolto' : mode === 'speak' ? 'Ti rispondo' : 'Sono qui';
  const openMap = (node?: PresenceNode | null) => {
    Keyboard.dismiss();
    setInspection(node?.id || highlighted?.id || map?.stars.find(star => star.temporary)?.id || null);
    setMapOpen(true);
  };
  const options = useMemo(() => ({
    stars, mode, area, paused: false, reduced,
    active: active && foreground && !mapOpen && preview.showPreview,
    centerY: 0.5, spotlightId: highlighted?.id || null,
    reveal: Boolean(revealKey), revealKey,
  }), [stars, mode, area, reduced, active, foreground, mapOpen, preview.showPreview, highlighted?.id, revealKey]);

  return (
    <View ref={root} testID="ora-presence" style={[styles.root, viewport.maxHeight !== null && { maxHeight: viewport.maxHeight }]}
      onLayout={event => setMeasuredHeight(event.nativeEvent.layout.height)}>
      <View style={styles.header} testID="ora-mobile-header">
        {onBack ? <Pressable accessibilityRole="button" accessibilityLabel="Indietro" onPress={onBack} style={styles.iconButton}>
          <Ionicons name="chevron-back" size={22} color={palette.label} />
        </Pressable> : null}
        <View style={styles.identity}>
          <Text accessibilityRole="header" style={styles.wordmark}>ORA</Text>
          <Text style={styles.caption} numberOfLines={1} testID="ora-presence-state">{caption}{area ? ` · ${AREA_LABELS[area]}` : ''}</Text>
        </View>
        <Pressable accessibilityRole="button" accessibilityLabel="Espandi la mappa" accessibilityState={{ expanded: mapOpen }}
          onPress={() => openMap()} style={styles.mapButton} testID="ora-mobile-open-map">
          <Ionicons name="git-network-outline" size={17} color={palette.label} />
          <Text style={styles.mapButtonText}>Mappa</Text>
          <Ionicons name="expand-outline" size={14} color={palette.muted} />
        </Pressable>
      </View>

      {!viewport.editing ? <View style={styles.knowledgeStrip} testID="knowledge-map-progress">
        <Text style={styles.note}>{map ? `${map.count} stelle · ${map.temporary_count || 0} temporanee · VITA ${map.percent}%` : learned.error ? 'Mappa non disponibile' : 'Carico la mappa…'}</Text>
        {learned.error ? <Pressable accessibilityRole="button" accessibilityLabel="Riprova caricamento della mappa" onPress={learned.reload} style={styles.retry}><Text style={styles.note}>Riprova</Text></Pressable> : null}
      </View> : null}

      <View testID="ora-mobile-map-preview" style={[styles.preview, { height: preview.previewHeight, display: preview.showPreview ? 'flex' : 'none' }]}>
        {!canvasFailed ? <PresenceCanvas options={options} onUnavailable={() => setCanvasFailed(true)} onSelect={node => openMap(node)} />
          : <Text style={styles.note}>La mappa non è disponibile. La conversazione resta attiva.</Text>}
      </View>
      {preview.showPreview && highlighted ? <Pressable
        accessibilityRole="button"
        onPress={() => openMap()}
        style={[styles.highlight, !highlighted.temporary && styles.highlightPermanent]}
        testID="ora-mobile-star-detail"
      >
        <Text style={[styles.redStar, !highlighted.temporary && styles.permanentStar]}>✦</Text>
        <View style={styles.highlightText}>
          <Text style={[styles.highlightLabel, !highlighted.temporary && styles.highlightLabelPermanent]}>
            {highlighted.temporary ? 'MEMORIA TEMPORANEA IN EVIDENZA' : 'STELLA IN EVIDENZA'}
          </Text>
          <Text style={styles.highlightStatement} numberOfLines={2}>{highlighted.statement}</Text>
        </View>
        <Ionicons name="chevron-forward" size={16} color={highlighted.temporary ? '#ffaaaa' : palette.label} />
      </Pressable> : null}

      <View style={styles.conversation} testID="ora-mobile-conversation-panel">
        <View style={styles.conversationHead}><View style={styles.dot} /><Text style={styles.sectionLabel}>CONVERSAZIONE</Text></View>
        <View style={styles.conversationBody} testID="ora-presence-conversation">
          {conversation || <View style={styles.empty}><Text style={styles.emptyTitle}>Ci sono.</Text><Text style={styles.emptyText}>Scrivimi qui sotto. La mappa resta a portata di mano.</Text></View>}
        </View>
      </View>
      <View style={styles.footer} testID="ora-presence-footer">{footer}</View>

      <Modal visible={mapOpen} animationType={reduced ? 'none' : 'fade'} onRequestClose={() => setMapOpen(false)} presentationStyle="fullScreen">
        <View accessibilityViewIsModal style={[styles.modal, { paddingTop: insets.top, paddingBottom: insets.bottom }]} testID="ora-mobile-expanded-map">
          <View style={styles.modalHead}>
            <Text style={styles.modalTitle}>La tua mappa</Text>
            <Pressable accessibilityRole="button" accessibilityLabel="Torna alla chat" onPress={() => setMapOpen(false)} style={styles.mapButton} testID="ora-mobile-close-map">
              <Ionicons name="chatbubble-outline" size={17} color={palette.label} /><Text style={styles.mapButtonText}>Torna alla chat</Text>
            </Pressable>
          </View>
          {inspected && !inspected.temporary ? <Text style={styles.modalStatement}>{inspected.statement}</Text> : null}
          <StandardPresence expanded mode={mode} activity={activity} active={active && foreground && mapOpen}
            knowledge={map} spotlightId={inspection || spotlight}
            initialSelectedStarId={inspection} onKnowledgeChanged={learned.reload} knowledgeError={learned.error}
            onAreaPrompt={onAreaPrompt ? words => { setMapOpen(false); onAreaPrompt(words); } : undefined} />
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, minHeight: 0, minWidth: 0, width: '100%', overflow: 'hidden', backgroundColor: palette.background },
  header: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 10, paddingVertical: 3, minHeight: 54, flexShrink: 0 },
  iconButton: { minHeight: 44, minWidth: 40, alignItems: 'center', justifyContent: 'center' },
  identity: { flex: 1, minWidth: 0, gap: 2 },
  wordmark: { color: palette.text, fontSize: 18, letterSpacing: 3, fontWeight: '500' },
  caption: { color: palette.muted, fontSize: 11, lineHeight: 15 },
  mapButton: { minHeight: 44, flexDirection: 'row', gap: 6, alignItems: 'center', paddingHorizontal: 10, borderRadius: 18, borderWidth: StyleSheet.hairlineWidth, borderColor: palette.border },
  mapButtonText: { color: palette.label, fontSize: 12 },
  knowledgeStrip: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 14, minHeight: 24, flexShrink: 0 },
  note: { color: palette.muted, fontSize: 11, lineHeight: 16 },
  retry: { minHeight: 44, paddingHorizontal: 8, justifyContent: 'center' },
  preview: { position: 'relative', flexShrink: 0, overflow: 'hidden', marginHorizontal: 8, borderRadius: 14 },
  highlight: { flexShrink: 0, flexDirection: 'row', alignItems: 'center', gap: 9, minHeight: 44, paddingHorizontal: 12, paddingVertical: 7, marginHorizontal: 10, marginBottom: 6, borderRadius: 12, borderWidth: StyleSheet.hairlineWidth, borderColor: 'rgba(255,110,110,.35)', backgroundColor: 'rgba(58,15,24,.55)' },
  highlightPermanent: { borderColor: palette.border, backgroundColor: 'rgba(10,27,39,.72)' },
  highlightText: { flex: 1, minWidth: 0 },
  redStar: { color: '#ff7373', fontSize: 18 },
  permanentStar: { color: palette.label },
  highlightLabel: { color: '#ffaaaa', fontSize: 9, letterSpacing: 0.7, lineHeight: 14 },
  highlightLabelPermanent: { color: palette.label },
  highlightStatement: { color: palette.text, fontSize: 12, lineHeight: 17 },
  conversation: { flex: 1, minHeight: 0, minWidth: 0, marginHorizontal: 8, borderRadius: 18, borderWidth: StyleSheet.hairlineWidth, borderColor: palette.border, backgroundColor: '#09121b', overflow: 'hidden' },
  conversationHead: { flexDirection: 'row', alignItems: 'center', gap: 7, paddingHorizontal: 14, minHeight: 30, flexShrink: 0 },
  dot: { width: 5, height: 5, borderRadius: 3, backgroundColor: palette.label },
  sectionLabel: { color: palette.muted, fontSize: 9, letterSpacing: 1.5 },
  conversationBody: { flex: 1, minHeight: 0, minWidth: 0 },
  footer: { flexShrink: 0, minWidth: 0, paddingHorizontal: 8, paddingTop: 4, paddingBottom: 6 },
  empty: { padding: 18, gap: 8 },
  emptyTitle: { color: palette.text, fontSize: 22, fontWeight: '600' },
  emptyText: { color: palette.muted, fontSize: 14, lineHeight: 21 },
  modal: { flex: 1, minHeight: 0, backgroundColor: palette.background },
  modalHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 12, paddingVertical: 6 },
  modalTitle: { color: palette.text, fontSize: 16, fontWeight: '600' },
  modalStatement: { color: '#ffaaaa', fontSize: 14, lineHeight: 20, paddingHorizontal: 18, paddingBottom: 8 },
});
