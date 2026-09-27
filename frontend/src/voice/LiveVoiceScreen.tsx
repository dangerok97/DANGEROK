/** The same ORA presence in voice; transport and interruption remain in useLiveVoice. */
import React from 'react';
import {
  Modal,
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
import { OraPresence } from '@/src/components/ora/presence/OraPresence';
import { presenceMode, type PresenceActivity } from '@/src/components/ora/presence/state';

export function LiveVoiceScreen({ live, activity = null, openingKey = null }: { live: LiveVoice; activity?: PresenceActivity | null; openingKey?: string | null }) {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const listening = live.state.phase === 'listening' || live.state.phase === 'asking';
  const speaking = live.state.phase === 'speaking';
  const preparing = live.state.phase === 'preparing';
  if (!live.on) return null;

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
          <OraPresence openingKey={openingKey} mode={presenceMode(false, live.state.phase)} activity={activity} />
          {speaking || preparing ? <Pressable
            onPress={speaking || preparing ? live.interrupt : undefined} accessibilityRole="button"
            accessibilityLabel="Interrompi ORA e parla" style={styles.interrupt} testID="live-voice-orb"
          ><Text style={{ color: colors.textSecondary }}>Interrompi e parla</Text></Pressable> : null}

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
  interrupt: { minHeight: tokens.touch.min, justifyContent: 'center', alignItems: 'center' },
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
