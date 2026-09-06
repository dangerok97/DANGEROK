/**
 * Un appuntamento, guardato da vicino.
 *
 * Toccare la visita dal dentista apriva un flusso generico che chiedeva «vuoi
 * preparare un esame oppure creare un evento?». La risposta giusta a quel
 * tocco non e' una domanda: e' l'appuntamento, con quello che serve sapere e
 * le due cose che ci si puo' fare — spostarlo o toglierlo.
 *
 * Qui dentro non compare niente di tecnico: nessun id, nessun JSON, nessuna
 * capability. Un appuntamento e' un titolo, un giorno, un'ora, un posto e da
 * dove lo sappiamo.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Stack, useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { tokens } from '@/src/theme/tokens';
import { api, CalendarEventDetail } from '@/src/api/client';
import { haptic } from '@/src/utils/haptic';
import { humanizeError } from '@/src/utils/errors';
import { ConfirmDialog } from '@/src/components/ui/ConfirmDialog';
import { buildOraConversationHref } from '@/src/ora/oraNav';

const MAX_WIDTH = 720;

/** «giovedì 10 settembre», come lo direbbe una persona. */
function humanDay(value?: string | null): string {
  if (!value) return '';
  const when = new Date(value);
  if (Number.isNaN(when.getTime())) return '';
  return when.toLocaleDateString('it-IT', {
    weekday: 'long', day: 'numeric', month: 'long',
  });
}

/** «10:00 – 11:00», o solo l'inizio quando non c'e' una fine. */
function humanTime(start?: string | null, end?: string | null, allDay?: boolean): string {
  if (allDay) return 'Tutto il giorno';
  if (!start) return '';
  const from = new Date(start);
  if (Number.isNaN(from.getTime())) return '';
  const fmt = (d: Date) => d.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
  if (!end) return fmt(from);
  const to = new Date(end);
  if (Number.isNaN(to.getTime())) return fmt(from);
  return `${fmt(from)} – ${fmt(to)}`;
}

function Row({ icon, label, value }: { icon: any; label: string; value: string }) {
  if (!value) return null;
  return (
    <View style={styles.row}>
      <Ionicons name={icon} size={18} color={tokens.color.textSecondary} style={styles.rowIcon} />
      <View style={{ flex: 1 }}>
        <Text style={styles.rowLabel}>{label}</Text>
        <Text style={styles.rowValue}>{value}</Text>
      </View>
    </View>
  );
}

export default function CalendarEventScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [event, setEvent] = useState<CalendarEventDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [gone, setGone] = useState(false);

  const load = useCallback(async () => {
    if (!id) return;
    try {
      setEvent(await api.calendarEvent(String(id)));
      setError(null);
    } catch (e: any) {
      setError(humanizeError(e, 'default'));
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { void load(); }, [load]);

  const remove = useCallback(async () => {
    if (!event) return;
    setBusy(true);
    try {
      // Il titolo viaggia con la conferma: e' quello che la persona aveva
      // davanti quando ha detto di si'.
      const out = await api.calendarEventDelete(String(id), event.title);
      // «Eliminato» si dice solo se il server ha verificato che non c'e' piu'.
      if (out.ok && out.verified) {
        void haptic('success');
        setGone(true);
        setAsking(false);
      } else {
        setError('Non sono riuscita a toglierlo. È ancora in calendario.');
        setAsking(false);
      }
    } catch (e: any) {
      setError(humanizeError(e, 'default'));
      setAsking(false);
    } finally {
      setBusy(false);
    }
  }, [event, id]);

  const day = useMemo(() => humanDay(event?.starts_at), [event?.starts_at]);
  const time = useMemo(
    () => humanTime(event?.starts_at, event?.ends_at, event?.all_day),
    [event?.starts_at, event?.ends_at, event?.all_day],
  );

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.header}>
        <Pressable
          onPress={() => router.back()}
          style={styles.back}
          accessibilityRole="button"
          accessibilityLabel="Torna indietro"
          testID="event-back"
        >
          <Ionicons name="chevron-back" size={22} color={tokens.color.textPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Appuntamento</Text>
        <View style={styles.back} />
      </View>

      <ScrollView contentContainerStyle={styles.scroll}>
        <View style={styles.column}>
          {loading ? (
            <ActivityIndicator style={{ marginTop: 40 }} color={tokens.color.textPrimary} />
          ) : gone ? (
            <View style={styles.card} testID="event-deleted">
              <Text style={styles.title}>Eliminato</Text>
              <Text style={styles.body}>
                «{event?.title}» non è più nel tuo calendario.
              </Text>
              <Pressable
                style={styles.primary}
                onPress={() => router.replace('/(tabs)' as any)}
                accessibilityRole="button"
              >
                <Text style={styles.primaryText}>Torna alla Home</Text>
              </Pressable>
            </View>
          ) : error && !event ? (
            <View style={styles.card}>
              <Text style={styles.body}>{error}</Text>
            </View>
          ) : event ? (
            <>
              <View style={styles.card} testID="event-detail">
                <Text style={styles.title}>{event.title}</Text>
                <Text style={styles.when}>
                  {day}{time ? ` · ${time}` : ''}
                </Text>

                <View style={styles.rows}>
                  <Row icon="location-outline" label="Dove" value={event.location || ''} />
                  <Row
                    icon="calendar-outline"
                    label="Da dove arriva"
                    value={event.where_it_comes_from || ''}
                  />
                  <Row icon="checkmark-circle-outline" label="Stato" value={event.state || ''} />
                  <Row
                    icon="document-text-outline"
                    label="Note"
                    value={(event.description || '').trim()}
                  />
                </View>
              </View>

              {error ? <Text style={styles.error}>{error}</Text> : null}

              <View style={styles.actions}>
                <Pressable
                  style={styles.primary}
                  testID="event-edit"
                  accessibilityRole="button"
                  onPress={() => {
                    void haptic('tap');
                    // Lo spostamento passa dalla conversazione, che e' dove
                    // vive il percorso di modifica gia' corretto: un intento
                    // di spostare non puo' essere soddisfatto creando.
                    const ask = encodeURIComponent(
                      `Sposta «${event.title}» a un altro orario.`,
                    );
                    router.push(`${buildOraConversationHref({})}${
                      buildOraConversationHref({}).includes('?') ? '&' : '?'
                    }draft=${ask}` as any);
                  }}
                >
                  <Ionicons name="time-outline" size={18} color={tokens.color.onAccent} />
                  <Text style={styles.primaryText}>Modifica evento</Text>
                </Pressable>

                <Pressable
                  style={styles.danger}
                  testID="event-delete"
                  accessibilityRole="button"
                  onPress={() => { void haptic('tap'); setAsking(true); }}
                >
                  <Ionicons name="trash-outline" size={18} color={tokens.color.error} />
                  <Text style={styles.dangerText}>Elimina evento</Text>
                </Pressable>
              </View>

              <Text style={styles.footnote}>
                Eliminandolo lo tolgo anche dal tuo Google Calendar.
              </Text>
            </>
          ) : null}
        </View>
      </ScrollView>

      <ConfirmDialog
        open={asking}
        title="Elimino questo appuntamento?"
        body={
          event
            ? `«${event.title}»${day ? `, ${day}` : ''}${time ? ` alle ${time}` : ''}. `
              + 'Lo tolgo anche dal tuo Google Calendar.'
            : ''
        }
        confirmLabel="Elimina"
        cancelLabel="Annulla"
        destructive
        busy={busy}
        onCancel={() => setAsking(false)}
        onConfirm={remove}
        testID="event-delete-confirm"
        confirmTestID="event-delete-confirm-yes"
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: tokens.color.backgroundPrimary },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 8, paddingVertical: 6,
  },
  back: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  headerTitle: {
    fontSize: 13, letterSpacing: 1.2, textTransform: 'uppercase',
    color: tokens.color.textSecondary, fontWeight: '600',
  },
  scroll: { paddingBottom: 48 },
  column: { width: '100%', maxWidth: MAX_WIDTH, alignSelf: 'center', paddingHorizontal: 20 },
  card: {
    backgroundColor: tokens.color.surface,
    borderRadius: tokens.radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: tokens.color.border,
    padding: 20,
    marginTop: 8,
  },
  title: { fontSize: 26, fontWeight: '700', color: tokens.color.textPrimary, lineHeight: 32 },
  when: { marginTop: 6, fontSize: 16, color: tokens.color.textSecondary },
  rows: { marginTop: 18, gap: 14 },
  row: { flexDirection: 'row', alignItems: 'flex-start', gap: 12 },
  rowIcon: { marginTop: 2 },
  rowLabel: {
    fontSize: 11, letterSpacing: 0.8, textTransform: 'uppercase',
    color: tokens.color.textSecondary, fontWeight: '600',
  },
  rowValue: { fontSize: 15, color: tokens.color.textPrimary, marginTop: 2 },
  actions: { marginTop: 18, gap: 10 },
  primary: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
    backgroundColor: tokens.color.accent,
    paddingVertical: 14, borderRadius: tokens.radius.lg,
  },
  primaryText: { color: tokens.color.onAccent, fontSize: 15, fontWeight: '600' },
  danger: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
    paddingVertical: 14, borderRadius: tokens.radius.lg,
    borderWidth: StyleSheet.hairlineWidth, borderColor: tokens.color.error,
    backgroundColor: tokens.color.errorBg,
  },
  dangerText: { color: tokens.color.error, fontSize: 15, fontWeight: '600' },
  body: { fontSize: 15, color: tokens.color.textPrimary, marginTop: 8, lineHeight: 22 },
  error: { marginTop: 12, fontSize: 14, color: tokens.color.error },
  footnote: { marginTop: 12, fontSize: 13, color: tokens.color.textSecondary, textAlign: 'center' },
});
