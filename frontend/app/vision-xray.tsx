/** ORA Vision X-Ray: one foreground still => a truthful, interactive exploded schematic. */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  AccessibilityInfo,
  ActivityIndicator,
  Animated,
  Image,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
  useWindowDimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';

import CameraPreview from '@/src/vision-xray/CameraPreview';
import { imageUriAsData, scanObject, type XrayPart, type XrayResult } from '@/src/vision-xray/api';
import { pickOraAttachment } from '@/src/components/ora/OraComposer';

const COLORS = {
  bg: '#070D19',
  panel: '#121B2A',
  border: '#2A384D',
  blue: '#79B5FF',
  main: '#F7FAFF',
  secondary: '#BDCBDB',
  muted: '#8091A7',
  green: '#B8E9DB',
};

function iconFor(kind: XrayPart['visual_kind']): React.ComponentProps<typeof Ionicons>['name'] {
  switch (kind) {
    case 'battery': return 'battery-charging-outline';
    case 'board': return 'hardware-chip-outline';
    case 'button': return 'keypad-outline';
    case 'sensor': return 'radio-outline';
    case 'connector': return 'git-merge-outline';
    case 'body': return 'cube-outline';
    default: return 'layers-outline';
  }
}

/** Deliberately abstract. No hidden geometry is fabricated from a flat photo. */
function PartLayer({
  part, position, selected, onPress, progress,
}: {
  part: XrayPart; position: number; selected: boolean;
  onPress: () => void; progress: Animated.Value;
}) {
  const slide = progress.interpolate({ inputRange: [0, 1], outputRange: [-35 * (position + 1), 0] });
  const emerge = progress.interpolate({ inputRange: [0, 0.2, 1], outputRange: [0, 0.12, 1] });
  return (
    <Animated.View style={{ opacity: emerge, transform: [{ translateX: slide }] }}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={'Componente ' + part.name + ', ' + (part.certainty === 'visible' ? 'visibile' : 'ipotizzato')}
        onPress={onPress}
        testID={'xray-part-' + part.id}
        style={[styles.layerTap, selected && styles.layerSelected]}
      >
        <View style={[styles.layerPlate, selected && styles.layerPlateSelected]}>
          <View style={styles.plateDetail}>
            <Ionicons name={iconFor(part.visual_kind)} size={38} color={selected ? '#D9ECFF' : '#80AEE5'} />
          </View>
          <View style={styles.plateEdge} />
        </View>
        <Text style={styles.layerNumber}>0{position + 1}</Text>
        <Text style={styles.layerName} numberOfLines={2}>{part.name}</Text>
        <Text style={styles.layerCertainty}>{part.certainty === 'visible' ? 'Visibile' : 'Componente tipico'}</Text>
      </Pressable>
    </Animated.View>
  );
}

export default function VisionXrayScreen() {
  const router = useRouter();
  const { width } = useWindowDimensions();
  const [cameraOpen, setCameraOpen] = useState(false);
  const [photo, setPhoto] = useState<string | null>(null);
  const [result, setResult] = useState<XrayResult | null>(null);
  const [active, setActive] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const progress = useRef(new Animated.Value(0)).current;
  const taskId = useRef(0);

  useEffect(() => {
    if (!result?.parts.length) return;
    let mounted = true;
    void AccessibilityInfo.isReduceMotionEnabled().then((reduced) => {
      if (!mounted) return;
      progress.setValue(reduced ? 1 : 0);
      if (!reduced) Animated.spring(progress, { toValue: 1, tension: 45, friction: 12, useNativeDriver: true }).start();
    });
    return () => { mounted = false; };
  }, [result, progress]);

  // Every new scan invalidates old responses; a slow first analysis can never
  // overwrite the second photograph.
  const analyze = useCallback(async (dataUri: string) => {
    taskId.current += 1;
    const currentTask = taskId.current;
    setPhoto(dataUri);
    setCameraOpen(false);
    setResult(null);
    setActive(0);
    setError(null);
    setBusy(true);
    try {
      const found = await scanObject(dataUri);
      if (currentTask === taskId.current) setResult(found);
    } catch (e: any) {
      if (currentTask === taskId.current) setError(e?.message || 'Non riesco a riconoscere questo oggetto.');
    } finally {
      if (currentTask === taskId.current) setBusy(false);
    }
  }, []);

  const choosePhoto = useCallback(async () => {
    setError(null);
    try {
      const picked = await pickOraAttachment('photo');
      if (!picked) return;
      try {
        const data = await imageUriAsData(picked.uri, picked.type);
        void analyze(data);
      } finally {
        if (Platform.OS === 'web' && picked.uri.startsWith('blob:')) {
          URL.revokeObjectURL(picked.uri);
        }
      }
    } catch (e: any) {
      setError(e?.message || 'Non riesco ad aprire la foto.');
    }
  }, [analyze]);

  const openCamera = () => {
    taskId.current += 1;
    setBusy(false);
    setResult(null);
    setPhoto(null);
    setError(null);
    setCameraOpen(true);
  };

  const reportCameraError = (message: string) => {
    setError(message);
    setCameraOpen(false);
  };
  const parts = result?.parts || [];
  const chosen = parts[active] || null;

  return (
    <SafeAreaView style={styles.root} edges={['top', 'bottom']}>
      <ScrollView style={styles.scroll} contentContainerStyle={[styles.content, { maxWidth: Math.min(860, width) }]}>
        <View style={styles.header}>
          <Pressable accessibilityLabel="Torna indietro" onPress={() => router.back()} style={styles.back} testID="xray-back">
            <Ionicons name="arrow-back" color={COLORS.main} size={22} />
          </Pressable>
          <View style={{ flex: 1 }}>
            <Text style={styles.brand}>ORA / VISION X-RAY</Text>
            <Text style={styles.title}>Guarda oltre la superficie.</Text>
          </View>
        </View>
        <Text style={styles.intro}>
          Inquadra un oggetto o scegli una foto. ORA proverà a riconoscerlo e
          mostrerà uno schema esploso con componenti da esplorare.
        </Text>

        {!cameraOpen && !photo && (
          <View style={styles.emptyStage}>
            <Ionicons name="scan-outline" size={58} color={COLORS.blue} />
            <Text style={styles.emptyTitle}>Che cosa vuoi esplorare?</Text>
            <Text style={styles.emptySub}>Niente viene analizzato finché non apri la fotocamera o scegli una foto.</Text>
          </View>
        )}

        {cameraOpen && (
          <CameraPreview onCapture={(data) => { void analyze(data); }} onError={reportCameraError} />
        )}

        {!!photo && !cameraOpen && (
          <View style={styles.photoFrame}>
            <Image source={{ uri: photo }} style={styles.photo} resizeMode="contain" accessibilityLabel="Fotografia acquisita" />
            {busy ? (
              <View style={styles.photoBadge}>
                <ActivityIndicator size="small" color={COLORS.blue} />
                <Text style={styles.photoBadgeText}>ORA sta osservando…</Text>
              </View>
            ) : !!result ? (
              <View style={styles.photoBadge}>
                <Ionicons name="scan-circle-outline" size={18} color={COLORS.green} />
                <Text style={styles.photoBadgeText}>{result.object_name}</Text>
              </View>
            ) : null}
          </View>
        )}

        <View style={styles.actions}>
          {Platform.OS === 'web' && (
            <Pressable
              style={styles.primary}
              onPress={openCamera}
              disabled={busy}
              accessibilityRole="button"
              testID="xray-open-camera"
            >
              <Ionicons name="camera-outline" size={20} color="#071020" />
              <Text style={styles.primaryText}>{photo ? 'Inquadra altro' : 'Apri fotocamera'}</Text>
            </Pressable>
          )}
          <Pressable
            style={styles.secondary}
            onPress={() => { void choosePhoto(); }}
            disabled={busy}
            accessibilityRole="button"
            testID="xray-pick-photo"
          >
            <Ionicons name="image-outline" size={20} color={COLORS.main} />
            <Text style={styles.secondaryText}>Scegli foto</Text>
          </Pressable>
        </View>

        {!!error && (
          <View style={styles.message} accessibilityRole="alert" testID="xray-error">
            <Ionicons name="alert-circle-outline" size={20} color="#FFB6A9" />
            <Text style={styles.errorText}>{error}</Text>
          </View>
        )}

        {!!result && (
          <View style={styles.results} testID="xray-result">
            <View style={styles.resultHead}>
              <Text style={styles.kicker}>OGGETTO RICONOSCIUTO</Text>
              <Text style={styles.resultName}>{result.object_name}</Text>
              <Text style={styles.description}>{result.what_i_see}</Text>
              <Text style={styles.truth}>
                {result.confidence === 'low'
                  ? 'Riconoscimento incerto: prova un’altra angolazione.'
                  : 'Vista esplosa illustrativa · non è una scansione dell’interno reale.'}
              </Text>
            </View>

            {parts.length > 0 ? (
              <>
                <View style={styles.sectionHead}>
                  <View>
                    <Text style={styles.kicker}>ESPLORA LE PARTI</Text>
                    <Text style={styles.sectionTitle}>Un oggetto, più livelli.</Text>
                  </View>
                  <Ionicons name="move-outline" size={22} color={COLORS.blue} />
                </View>
                <ScrollView
                  horizontal
                  showsHorizontalScrollIndicator={false}
                  contentContainerStyle={styles.exploded}
                  testID="xray-exploded-parts"
                >
                  {parts.map((part, i) => (
                    <React.Fragment key={part.id}>
                      {i > 0 ? <View style={styles.connector} /> : null}
                      <PartLayer
                        part={part}
                        position={i}
                        selected={i === active}
                        onPress={() => setActive(i)}
                        progress={progress}
                      />
                    </React.Fragment>
                  ))}
                </ScrollView>
                {!!chosen && (
                  <View style={styles.detail} testID="xray-part-detail">
                    <View style={styles.detailHeading}>
                      <Ionicons name={iconFor(chosen.visual_kind)} size={26} color={COLORS.blue} />
                      <View style={{ flex: 1 }}>
                        <Text style={styles.detailName}>{chosen.name}</Text>
                        <Text style={styles.detailKind}>
                          {chosen.certainty === 'visible'
                            ? 'Elemento individuato nella foto'
                            : 'Parte tipica ipotizzata · non verificata sulla tua unità'}
                        </Text>
                      </View>
                    </View>
                    <Text style={styles.detailLabel}>A COSA SERVE</Text>
                    <Text style={styles.detailText}>{chosen.function || 'Funzione non determinabile con certezza.'}</Text>
                    <Text style={styles.detailLabel}>COME FUNZIONA</Text>
                    <Text style={styles.detailText}>{chosen.how_it_works || 'Servono più informazioni per spiegarne il funzionamento.'}</Text>
                  </View>
                )}
              </>
            ) : (
              <Text style={styles.cannotSplit}>
                Non ho elementi sufficienti per una scomposizione attendibile.
                Prova con una foto più vicina, chiara e centrata.
              </Text>
            )}

            {result.unknowns ? <Text style={styles.disclaimer}>Limiti: {result.unknowns}</Text> : null}
            {result.safety_note ? <Text style={styles.safety}>Attenzione: {result.safety_note}</Text> : null}
          </View>
        )}

        <Text style={styles.privacy}>Le immagini vengono inviate all'AI solo dopo un'acquisizione volontaria. Vision X-Ray non salva gli scatti sul server.</Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: COLORS.bg },
  scroll: { flex: 1 },
  content: { paddingHorizontal: 18, paddingTop: 18, paddingBottom: 52, width: '100%', alignSelf: 'center', gap: 18 },
  header: { flexDirection: 'row', alignItems: 'center', gap: 16 },
  back: { width: 46, height: 46, borderColor: COLORS.border, borderWidth: 1, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
  brand: { fontSize: 11, fontWeight: '800', letterSpacing: 2.2, color: COLORS.blue, marginBottom: 7 },
  title: { fontSize: 25, fontWeight: '700', lineHeight: 29, color: COLORS.main, letterSpacing: -0.5 },
  intro: { color: COLORS.secondary, fontSize: 15, lineHeight: 23 },
  emptyStage: { height: 310, borderRadius: 22, backgroundColor: COLORS.panel, borderWidth: 1, borderColor: COLORS.border, alignItems: 'center', justifyContent: 'center', padding: 24, gap: 13 },
  emptyTitle: { color: COLORS.main, fontSize: 21, fontWeight: '700', textAlign: 'center' },
  emptySub: { color: COLORS.secondary, fontSize: 13, lineHeight: 20, textAlign: 'center' },
  photoFrame: { height: 330, borderRadius: 18, overflow: 'hidden', backgroundColor: '#0C1522', borderWidth: 1, borderColor: COLORS.border },
  photo: { width: '100%', height: '100%' },
  photoBadge: { position: 'absolute', bottom: 12, left: 12, right: 12, flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: '#121C29E6', paddingHorizontal: 14, paddingVertical: 10, borderRadius: 14 },
  photoBadgeText: { flex: 1, color: COLORS.main, fontWeight: '700', fontSize: 15 },
  actions: { flexDirection: 'row', gap: 10, flexWrap: 'wrap' },
  primary: { flexGrow: 1, flexDirection: 'row', gap: 9, alignItems: 'center', justifyContent: 'center', minHeight: 50, paddingHorizontal: 16, borderRadius: 13, backgroundColor: '#92C5FF' },
  primaryText: { color: '#071020', fontWeight: '800', fontSize: 14 },
  secondary: { flexGrow: 1, flexDirection: 'row', gap: 9, alignItems: 'center', justifyContent: 'center', minHeight: 50, paddingHorizontal: 16, borderRadius: 13, borderWidth: 1, borderColor: COLORS.border, backgroundColor: COLORS.panel },
  secondaryText: { color: COLORS.main, fontWeight: '700', fontSize: 14 },
  message: { flexDirection: 'row', gap: 9, alignItems: 'center', padding: 13, borderRadius: 12, borderColor: '#85423D', borderWidth: 1, backgroundColor: '#291B21' },
  errorText: { flex: 1, color: '#FFD1C9', fontSize: 14, lineHeight: 20 },
  results: { gap: 18, paddingTop: 5 },
  resultHead: { gap: 9 },
  kicker: { color: COLORS.blue, fontWeight: '800', letterSpacing: 2, fontSize: 10 },
  resultName: { color: COLORS.main, fontWeight: '800', fontSize: 28, lineHeight: 32 },
  description: { color: COLORS.secondary, fontSize: 15, lineHeight: 22 },
  truth: { color: COLORS.muted, fontSize: 12, lineHeight: 18 },
  sectionHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 10 },
  sectionTitle: { color: COLORS.main, fontSize: 19, fontWeight: '700', paddingTop: 5 },
  exploded: { alignItems: 'center', paddingTop: 15, paddingBottom: 16, paddingRight: 26 },
  connector: { width: 23, height: 2, backgroundColor: '#4E6D8D', marginHorizontal: 5, marginTop: -48 },
  layerTap: { width: 146, minHeight: 212, padding: 10, borderWidth: 1, borderColor: COLORS.border, borderRadius: 15, backgroundColor: '#142034', alignItems: 'center' },
  layerSelected: { backgroundColor: '#172E4D', borderColor: '#87BEF9' },
  layerPlate: { height: 104, width: 100, borderWidth: 2, borderColor: '#517DAF', borderRadius: 15, transform: [{ perspective: 800 }, { rotateY: '-18deg' }], justifyContent: 'center', alignItems: 'center', backgroundColor: '#20395B' },
  layerPlateSelected: { borderColor: '#A0D6FF', backgroundColor: '#2C517B' },
  plateDetail: { width: 66, height: 66, borderColor: '#638CB8', borderWidth: 1, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  plateEdge: { height: 4, width: 50, backgroundColor: '#79B5FF', borderRadius: 3, position: 'absolute', bottom: 6 },
  layerNumber: { fontWeight: '800', fontSize: 10, color: COLORS.blue, letterSpacing: 2, paddingTop: 11 },
  layerName: { fontWeight: '700', fontSize: 13, color: COLORS.main, textAlign: 'center', minHeight: 32, marginTop: 5 },
  layerCertainty: { fontSize: 10, color: COLORS.muted, textAlign: 'center', marginTop: 4 },
  detail: { gap: 9, backgroundColor: COLORS.panel, borderColor: COLORS.border, borderWidth: 1, borderRadius: 18, padding: 18 },
  detailHeading: { flexDirection: 'row', gap: 12, alignItems: 'center', paddingBottom: 7 },
  detailName: { fontSize: 20, fontWeight: '700', color: COLORS.main },
  detailKind: { color: COLORS.muted, fontSize: 12, paddingTop: 4, lineHeight: 17 },
  detailLabel: { color: COLORS.blue, fontSize: 10, letterSpacing: 2, fontWeight: '700', paddingTop: 7 },
  detailText: { color: COLORS.secondary, fontSize: 15, lineHeight: 23 },
  cannotSplit: { fontSize: 15, color: COLORS.secondary, lineHeight: 22 },
  disclaimer: { color: COLORS.muted, fontSize: 12, lineHeight: 19 },
  safety: { color: '#FFD49B', fontSize: 12, lineHeight: 19 },
  privacy: { fontSize: 11, color: COLORS.muted, lineHeight: 18, paddingTop: 24 },
});
