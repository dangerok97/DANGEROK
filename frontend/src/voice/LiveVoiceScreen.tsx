/**
 * La modalità vocale: una schermata sola, e quasi vuota.
 *
 *     NON È UNA TELEFONATA, NON È UN REGISTRATORE, NON È UNA PAGINA TECNICA.
 *
 * Chi ha appena aperto bocca non deve leggere niente. Al centro c'è un segno
 * piccolo che respira quando ORA ascolta e batte quando parla; sotto, fuori
 * da quel segno, una frase sola in italiano; sotto ancora, quando serve, una
 * riga che dice cosa si può fare. In fondo tre comandi separati fra loro:
 * mettere in pausa il microfono, chiudere, tornare a scrivere.
 *
 * Il disco lilla grande con il testo dentro era la versione precedente ed era
 * sbagliata per due ragioni: la prima è che un testo dentro una forma che
 * pulsa si legge male, la seconda è che quella forma prometteva di reagire
 * alla voce e non reagiva a niente — l'animazione era un ciclo fisso, e un
 * indicatore che finge di ascoltare è peggio di nessun indicatore.
 */
import React, { useEffect, useRef } from 'react';
import {
  AccessibilityInfo,
  Animated,
  Easing,
  Modal,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import type { LiveVoice } from './useLiveVoice';

/**
 * Se questa persona ha chiesto meno movimento, si sta fermi.
 *
 * Non è una preferenza estetica: per qualcuno un elemento che pulsa in mezzo
 * allo schermo è nausea o emicrania, e una schermata che si usa parlando può
 * restare aperta a lungo.
 */
function useCalmMotion(): boolean {
  const [calm, setCalm] = React.useState(false);
  useEffect(() => {
    let alive = true;
    const ask = async () => {
      try {
        const reduced = await AccessibilityInfo.isReduceMotionEnabled();
        if (alive) setCalm(Boolean(reduced));
      } catch {
        /* se non si può chiedere, ci si muove piano lo stesso */
      }
    };
    void ask();
    let media: any = null;
    if (Platform.OS === 'web' && typeof window !== 'undefined' && window.matchMedia) {
      media = window.matchMedia('(prefers-reduced-motion: reduce)');
      setCalm(Boolean(media.matches));
      const onChange = (e: any) => alive && setCalm(Boolean(e.matches));
      media.addEventListener?.('change', onChange);
      return () => {
        alive = false;
        media?.removeEventListener?.('change', onChange);
      };
    }
    return () => {
      alive = false;
    };
  }, []);
  return calm;
}

export function LiveVoiceScreen({ live }: { live: LiveVoice }) {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const calm = useCalmMotion();
  const pulse = useRef(new Animated.Value(0)).current;

  const listening = live.state.phase === 'listening' || live.state.phase === 'asking';
  const speaking = live.state.phase === 'speaking';
  const preparing = live.state.phase === 'preparing';
  const thinking = live.state.phase === 'heard' || live.state.phase === 'thinking';

  useEffect(() => {
    if (!live.on || calm) {
      pulse.setValue(0);
      return undefined;
    }
    // Respira quando ascolta, batte quando parla, sta ferma quando pensa.
    if (!listening && !speaking) {
      pulse.setValue(0);
      return undefined;
    }
    const beat = speaking ? 520 : 1600;
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, {
          toValue: 1,
          duration: beat,
          easing: Easing.inOut(Easing.ease),
          useNativeDriver: true,
        }),
        Animated.timing(pulse, {
          toValue: 0,
          duration: beat,
          easing: Easing.inOut(Easing.ease),
          useNativeDriver: true,
        }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [live.on, listening, speaking, calm, pulse]);

  if (!live.on) return null;

  const scale = pulse.interpolate({
    inputRange: [0, 1],
    outputRange: [1, speaking ? 1.18 : 1.08],
  });
  const halo = pulse.interpolate({ inputRange: [0, 1], outputRange: [0.1, 0.22] });

  return (
    <Modal visible animationType="fade" transparent={false} onRequestClose={live.close}>
      <View
        style={[styles.screen, { backgroundColor: colors.backgroundPrimary }]}
        testID="live-voice"
      >
        <View style={[styles.top, { paddingTop: insets.top + tokens.spacing.lg }]}>
          <Text style={[styles.wordmark, { color: colors.textTertiary }]}>ORA</Text>
        </View>

        <View style={styles.middle}>
          <Pressable
            onPress={speaking || preparing ? live.interrupt : undefined}
            accessibilityRole={speaking || preparing ? 'button' : undefined}
            accessibilityLabel={speaking || preparing ? 'Interrompi ORA e parla' : undefined}
            style={styles.markWrap}
            testID="live-voice-orb"
          >
            <Animated.View
              style={[
                styles.halo,
                {
                  backgroundColor: colors.accent,
                  opacity: listening || speaking ? halo : 0,
                  transform: [{ scale }],
                },
              ]}
            />
            <Animated.View
              style={[
                styles.mark,
                {
                  backgroundColor: speaking ? colors.accent : colors.textPrimary,
                  opacity: thinking || preparing ? 0.3 : 1,
                  transform: [{ scale }],
                },
              ]}
            />
          </Pressable>

          <Text
            style={[styles.says, { color: colors.textPrimary }]}
            testID="live-voice-state"
          >
            {live.says}
          </Text>

          {live.hint ? (
            <Text
              style={[styles.hint, { color: colors.textTertiary }]}
              testID="live-voice-hint"
            >
              {live.hint}
            </Text>
          ) : null}

          {listening && live.heard ? (
            <Text
              style={[styles.heard, { color: colors.textSecondary }]}
              numberOfLines={3}
              testID="live-voice-heard"
            >
              {live.heard}
            </Text>
          ) : null}

          {live.canRetry ? (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Riprova"
              onPress={live.retry}
              style={({ pressed }) => [
                styles.retry,
                { borderColor: colors.border, opacity: pressed ? 0.7 : 1 },
              ]}
              testID="live-voice-retry"
            >
              <Text style={[styles.retryText, { color: colors.textPrimary }]}>
                Riprova
              </Text>
            </Pressable>
          ) : null}
        </View>

        <View style={[styles.bottom, { paddingBottom: insets.bottom + tokens.spacing.xl }]}>
          <View style={styles.side}>
            <Control
              icon={live.muted ? 'mic-off-outline' : 'mic-outline'}
              label={live.muted ? 'Riaccendi il microfono' : 'Metti in pausa il microfono'}
              onPress={live.toggleMute}
              tint={live.muted ? colors.accent : colors.textSecondary}
              testID="live-voice-mute"
            />
          </View>
          <Control
            icon="close"
            label="Chiudi la conversazione a voce"
            onPress={live.close}
            tint={colors.textPrimary}
            big
            testID="live-voice-close"
          />
          <View style={styles.side}>
            <Control
              icon="create-outline"
              label="Torna a scrivere"
              onPress={live.close}
              tint={colors.textSecondary}
              testID="live-voice-keyboard"
            />
          </View>
        </View>
      </View>
    </Modal>
  );
}

function Control({
  icon, label, onPress, tint, big, testID,
}: {
  icon: any;
  label: string;
  onPress: () => void;
  tint: string;
  big?: boolean;
  testID: string;
}) {
  const { colors } = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      testID={testID}
      style={({ pressed }) => [
        styles.control,
        big && styles.controlBig,
        {
          borderColor: colors.border,
          backgroundColor: big ? colors.surface || colors.backgroundSecondary : 'transparent',
          opacity: pressed ? 0.7 : 1,
        },
      ]}
    >
      <Ionicons name={icon} size={big ? 24 : 21} color={tint} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  top: { alignItems: 'center' },
  wordmark: { fontSize: 12, letterSpacing: 3, fontWeight: '500' },
  middle: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: tokens.spacing.xl,
  },
  markWrap: {
    width: tokens.touch.min * 2,
    height: tokens.touch.min * 2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  halo: { position: 'absolute', width: 128, height: 128, borderRadius: 64 },
  mark: { width: 44, height: 44, borderRadius: 22 },
  says: {
    fontSize: 19,
    lineHeight: 25,
    letterSpacing: -0.2,
    marginTop: tokens.spacing.xl,
    textAlign: 'center',
  },
  hint: { fontSize: 14, lineHeight: 20, marginTop: 6, textAlign: 'center' },
  heard: {
    fontSize: 15,
    lineHeight: 21,
    textAlign: 'center',
    marginTop: tokens.spacing.lg,
  },
  retry: {
    marginTop: tokens.spacing.lg,
    minHeight: tokens.touch.min,
    justifyContent: 'center',
    paddingHorizontal: tokens.spacing.xl,
    borderRadius: tokens.radius.pill,
    borderWidth: StyleSheet.hairlineWidth,
  },
  retryText: { fontSize: 15, fontWeight: '500' },
  bottom: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    gap: tokens.spacing.xxl,
  },
  side: { width: tokens.touch.min, alignItems: 'center' },
  control: {
    width: tokens.touch.min,
    height: tokens.touch.min,
    borderRadius: tokens.touch.min / 2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  controlBig: {
    width: 64,
    height: 64,
    borderRadius: 32,
    borderWidth: StyleSheet.hairlineWidth,
  },
});
