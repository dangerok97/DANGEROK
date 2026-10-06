import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import type { KnowledgeStar } from './presence/knowledge';
import { presencePalette as palette, presenceColors } from '@/src/theme/presence';
import { situationIcon, situationTitle } from './situationVisual';

export function TemporarySituationToast({
  star,
  inline = false,
}: {
  star: KnowledgeStar | null;
  inline?: boolean;
}) {
  const [hiddenId, setHiddenId] = useState<string | null>(null);
  useEffect(() => {
    if (!star?.id) return;
    setHiddenId(null);
    const timer = setTimeout(() => setHiddenId(star.id), 9000);
    return () => clearTimeout(timer);
  }, [star?.id]);

  const age = star?.updated_at ? Date.now() - new Date(star.updated_at).getTime() : Infinity;
  if (!star || hiddenId === star.id || age < 0 || age > 120000) return null;
  return (
    <View style={[styles.toast, inline && styles.inlineToast]} testID="ora-temporary-toast">
      <View style={styles.icon}>
        <Ionicons name={situationIcon(star.icon_key)} size={22} color="#ff7373" />
      </View>
      <View style={styles.copy}>
        <Text style={styles.kicker}>Nuova memoria temporanea</Text>
        <Text style={styles.title} numberOfLines={1}>{situationTitle(star)}</Text>
        <Text style={styles.body} numberOfLines={2}>
          {star.statement} · Verrà rimossa dalla mappa quando la situazione termina.
        </Text>
      </View>
      <Pressable accessibilityRole="button" accessibilityLabel="Chiudi avviso" onPress={() => setHiddenId(star.id)} style={styles.close}>
        <Ionicons name="close" size={18} color={palette.muted} />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  toast: {
    position: 'absolute', left: 18, bottom: 18, width: 380, maxWidth: '42%',
    zIndex: 40, flexDirection: 'row', alignItems: 'center', gap: 12,
    padding: 14, borderRadius: 18, borderWidth: StyleSheet.hairlineWidth,
    borderColor: 'rgba(255,92,92,.26)', backgroundColor: 'rgba(7,15,24,.96)',
    shadowColor: '#000', shadowOpacity: .45, shadowRadius: 18,
  },
  inlineToast: {
    position: 'relative', left: undefined, bottom: undefined, width: '100%', maxWidth: '100%',
    flexShrink: 0,
  },
  icon: {
    width: 44, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center',
    backgroundColor: 'rgba(255,80,90,.12)', borderWidth: 1, borderColor: 'rgba(255,92,92,.42)',
  },
  copy: { flex: 1, minWidth: 0, gap: 2 },
  kicker: { color: presenceColors.textPrimary, fontSize: 12, fontWeight: '750' as any },
  title: { color: '#ff9090', fontSize: 11, fontWeight: '800', letterSpacing: .7, textTransform: 'uppercase' },
  body: { color: presenceColors.textSecondary, fontSize: 11, lineHeight: 16 },
  close: { width: 36, height: 36, alignItems: 'center', justifyContent: 'center' },
});
