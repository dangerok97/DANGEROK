/**
 * Canonical production ORA composer — Quiet Premium.
 * Real file attachments via Documents V2 + AI Core ContextFile bind.
 */
import React from 'react';
import {
  ActivityIndicator,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';

export type PendingAttachment = {
  localId: string;
  fileId?: string;
  documentId?: string;
  name: string;
  mimeType: string;
  status: 'uploading' | 'ready' | 'failed';
  error?: string;
  textAvailable?: boolean;
};

type Props = {
  value: string;
  onChangeText: (t: string) => void;
  onSend: () => void;
  busy?: boolean;
  disabled?: boolean;
  placeholder?: string;
  testID?: string;
  showAttach?: boolean;
  attachments?: PendingAttachment[];
  onAttachPress?: () => void;
  onRemoveAttachment?: (localId: string) => void;
  showMicStub?: boolean;
  onMicPress?: () => void;
};

export function OraComposer({
  value,
  onChangeText,
  onSend,
  busy,
  disabled,
  placeholder = 'Messaggio…',
  testID = 'ora-composer',
  showAttach = true,
  attachments = [],
  onAttachPress,
  onRemoveAttachment,
  showMicStub = true,
  onMicPress,
}: Props) {
  const { colors, isDark } = useTheme();
  const hasReadyFile = attachments.some((a) => a.status === 'ready');
  const uploading = attachments.some((a) => a.status === 'uploading');
  const canSend =
    (Boolean(value.trim()) || hasReadyFile) && !busy && !disabled && !uploading;

  return (
    <View testID={testID}>
      {attachments.length ? (
        <View style={styles.chips} testID={`${testID}-attachments`}>
          {attachments.map((a) => (
            <View
              key={a.localId}
              style={[
                styles.chip,
                {
                  backgroundColor: colors.surface || colors.backgroundSecondary,
                  borderColor: colors.border,
                },
              ]}
            >
              <Ionicons
                name={a.status === 'failed' ? 'alert-circle-outline' : 'document-outline'}
                size={16}
                color={a.status === 'failed' ? colors.error : colors.textSecondary}
              />
              <Text
                style={[
                  styles.chipText,
                  {
                    color:
                      a.status === 'failed' ? colors.error : colors.textPrimary,
                  },
                ]}
                numberOfLines={1}
              >
                {a.status === 'uploading'
                  ? `Caricamento… ${a.name}`
                  : a.status === 'failed'
                    ? a.error || `Errore: ${a.name}`
                    : a.name}
              </Text>
              {a.status === 'uploading' ? (
                <ActivityIndicator size="small" color={colors.textSecondary} />
              ) : (
                <Pressable
                  accessibilityLabel="Rimuovi allegato"
                  onPress={() => onRemoveAttachment?.(a.localId)}
                  hitSlop={8}
                  testID={`${testID}-remove-${a.localId}`}
                >
                  <Ionicons name="close" size={16} color={colors.textTertiary} />
                </Pressable>
              )}
            </View>
          ))}
        </View>
      ) : null}

      <View
        style={[
          styles.row,
          {
            borderTopColor: colors.border,
            backgroundColor: colors.backgroundPrimary,
          },
        ]}
      >
        {showAttach ? (
          <Pressable
            accessibilityLabel="Allega file"
            onPress={onAttachPress}
            disabled={busy || disabled || uploading}
            style={styles.iconBtn}
            testID={`${testID}-attach`}
          >
            <Ionicons name="attach-outline" size={20} color={colors.textTertiary} />
          </Pressable>
        ) : null}
        {showMicStub ? (
          <Pressable
            accessibilityLabel="Voce (riconoscimento non ancora attivo)"
            onPress={onMicPress}
            disabled={busy || disabled}
            style={styles.iconBtn}
            testID={`${testID}-mic`}
          >
            <Ionicons name="mic-outline" size={20} color={colors.textTertiary} />
          </Pressable>
        ) : null}
        <TextInput
          testID={`${testID}-input`}
          value={value}
          onChangeText={onChangeText}
          placeholder={placeholder}
          placeholderTextColor={colors.placeholder || colors.textSecondary}
          style={[
            styles.input,
            {
              color: colors.textPrimary,
              backgroundColor: colors.surface || colors.backgroundSecondary,
            },
          ]}
          editable={!busy && !disabled}
          multiline
          onSubmitEditing={() => {
            if (canSend) onSend();
          }}
          returnKeyType="send"
          keyboardAppearance={isDark ? 'dark' : 'light'}
        />
        <Pressable
          testID={`${testID}-send`}
          accessibilityLabel="Invia a ORA"
          onPress={onSend}
          disabled={!canSend}
          style={({ pressed }) => [
            styles.send,
            {
              backgroundColor: canSend ? colors.textPrimary : 'transparent',
              opacity: !canSend ? 0.35 : pressed ? 0.85 : 1,
            },
          ]}
        >
          {busy ? (
            <ActivityIndicator color={colors.backgroundPrimary} size="small" />
          ) : (
            <Ionicons
              name="arrow-up"
              size={18}
              color={canSend ? colors.backgroundPrimary : colors.textTertiary}
            />
          )}
        </Pressable>
      </View>
    </View>
  );
}

/** Pick a document (web + native) — returns RN-style file descriptor. */
export async function pickOraAttachment(): Promise<{
  uri: string;
  name: string;
  type: string;
} | null> {
  // Dynamic import keeps web bundle resilient if native module missing
  const DocumentPicker = await import('expo-document-picker');
  const res = await DocumentPicker.getDocumentAsync({
    type: [
      'application/pdf',
      'text/plain',
      'text/markdown',
      'image/*',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      'application/msword',
    ],
    multiple: false,
    copyToCacheDirectory: true,
  });
  if (res.canceled || !res.assets?.length) return null;
  const a = res.assets[0];
  return {
    uri: a.uri,
    name: a.name || 'file.bin',
    type: a.mimeType || 'application/octet-stream',
  };
}

void Platform;

const styles = StyleSheet.create({
  chips: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    paddingHorizontal: tokens.spacing.md,
    paddingTop: 8,
  },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    maxWidth: '100%',
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderRadius: 10,
    borderWidth: StyleSheet.hairlineWidth,
  },
  chipText: { fontSize: 13, flexShrink: 1, maxWidth: 220 },
  row: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: 6,
    paddingHorizontal: tokens.spacing.md,
    paddingTop: 8,
    borderTopWidth: StyleSheet.hairlineWidth,
  },
  iconBtn: {
    width: 40,
    height: 40,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 2,
  },
  input: {
    flex: 1,
    minHeight: 44,
    maxHeight: 120,
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 10,
    fontSize: 16,
    textAlignVertical: 'top',
  },
  send: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 2,
  },
});
