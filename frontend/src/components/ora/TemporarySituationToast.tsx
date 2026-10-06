import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import type { KnowledgeStar } from './presence/knowledge';
import { presencePalette as palette, presenceColors } from '@/src/theme/presence';
import { situationIcon, situationTitle } from './situationVisual';

function timeLabel(iso?: string | null): string {
  if (!iso) return 'adesso';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return 'adesso';
  return d.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
}

function lifecycleCopy(star: KnowledgeStar): string {
  const status = star.follow_up?.status || 'unavailable';
  const confirmed = ['scheduled', 'due', 'running'].includes(status);
  // Meaning is AI-authored, but a monitoring promise requires persisted work.
  const tracking = confirmed ? String(star.tracking_summary || '').trim() : '';
  const state = confirmed
    ? (status === 'running' ? 'Controllo in corso.' : 'Un controllo risulta programmato nella scheda.')
    : status === 'not_scheduled' ? 'Non risulta ancora un controllo automatico programmato.'
    : status === 'runtime_disabled' ? 'I controlli automatici sono disattivati.'
    : status === 'waiting_for_user' ? 'Il controllo attende informazioni o autorizzazione.'
    : status === 'recovery_pending' ? 'La programmazione del controllo deve essere recuperata.'
    : 'La programmazione del controllo non è confermata.';
  const lifecycle = 'Verrà rimossa dalla mappa quando la situazione sarà risolta o annullata.';
  return `${state} ${tracking ? tracking + ' ' : ''}${lifecycle}`;
}

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
    const timer = setTimeout(() => setHiddenId(star.id), 15000);
    return () => clearTimeout(timer);
  }, [star?.id]);

  const bornAt = star?.created_at || star?.updated_at;
  const age = bornAt ? Date.now() - new Date(bornAt).getTime() : Infinity;
  if (!star || hiddenId === star.id || age < 0 || age > 120000) return null;
  const title = situationTitle(star);

  return (
    <View style={[styles.toast, inline && styles.inlineToast]} testID="ora-temporary-toast">
      <View style={styles.icon}>
        <Ionicons name={situationIcon(star.icon_key)} size={24} color="#ff7373" />
      </View>

      <View style={styles.copy}>
        <View style={styles.head}>
          <Text style={styles.kicker}>Nuova memoria temporanea</Text>
          <Text style={styles.time}>{timeLabel(bornAt)}</Text>
        </View>
        <Text style={styles.title} numberOfLines={1}>{title}</Text>
        <Text style={styles.body}>
          {title} è stata aggiunta alla tua mappa. {lifecycleCopy(star)}
        </Text>
      </View>

      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Chiudi avviso"
        onPress={() => setHiddenId(star.id)}
        style={styles.close}
      >
        <Ionicons name="close" size={18} color={palette.muted} />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  toast: {
    position: 'absolute', left: 18, bottom: 18, width: 420, maxWidth: '46%',
    zIndex: 40, flexDirection: 'row', alignItems: 'flex-start', gap: 12,
    padding: 15, borderRadius: 18, borderWidth: StyleSheet.hairlineWidth,
    borderColor: 'rgba(255,92,92,.26)', backgroundColor: 'rgba(7,15,24,.96)',
    shadowColor: '#000', shadowOpacity: .45, shadowRadius: 18,
  },
  inlineToast: {
    position: 'relative', left: undefined, bottom: undefined, width: '100%', maxWidth: '100%',
    flexShrink: 0,
  },
  icon: {
    width: 46, height: 46, borderRadius: 23, alignItems: 'center', justifyContent: 'center',
    backgroundColor: 'rgba(255,80,90,.12)', borderWidth: 1, borderColor: 'rgba(255,92,92,.42)',
    shadowColor: '#ff5252', shadowOpacity: .35, shadowRadius: 10,
  },
  copy: { flex: 1, minWidth: 0, gap: 3 },
  head: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  kicker: { flex: 1, color: presenceColors.textPrimary, fontSize: 12, fontWeight: '750' as any },
  time: { color: palette.muted, fontSize: 10 },
  title: { color: '#ff9090', fontSize: 11, fontWeight: '800', letterSpacing: .7, textTransform: 'uppercase' },
  body: { color: presenceColors.textSecondary, fontSize: 11, lineHeight: 16 },
  close: { width: 32, height: 32, alignItems: 'center', justifyContent: 'center', marginTop: -3, marginRight: -4 },
});
