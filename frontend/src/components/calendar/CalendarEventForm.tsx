import { useRef, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { digestStringAsync, CryptoDigestAlgorithm, randomUUID } from 'expo-crypto';
import { api, type CalendarEventDetail, type HomeCalendarEvent, type HomeEventInput } from '@/src/api/client';
import { useTheme } from '@/src/theme/ThemeProvider';
import { useAuth } from '@/src/contexts/AuthContext';
import { tokens } from '@/src/theme/tokens';

function localParts(value: string, timezone: string) {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(new Date(value));
  const get = (key: string) => parts.find((p) => p.type === key)?.value || '';
  return { day: `${get('day')}/${get('month')}/${get('year')}`, time: `${get('hour')}:${get('minute')}` };
}

export function CalendarEventForm({ day, event, onSaved, onCancel, onBusyChange }: {
  day?: string;
  event?: CalendarEventDetail;
  onSaved: (saved: HomeCalendarEvent | CalendarEventDetail) => void;
  onCancel: () => void;
  onBusyChange?: (busy: boolean) => void;
}) {
  const { colors } = useTheme();
  const { user } = useAuth();
  const timezone = event?.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone || 'Europe/Rome';
  const initial = event?.starts_at ? localParts(event.starts_at, timezone) : { day: (day || '').split('-').reverse().join('/'), time: '09:00' };
  const [title, setTitle] = useState(event?.title || '');
  const [date, setDate] = useState(initial.day);
  const [time, setTime] = useState(initial.time);
  const [duration, setDuration] = useState(String(event?.starts_at && event.ends_at
    ? Math.round((Date.parse(event.ends_at) - Date.parse(event.starts_at)) / 60000) : 60));
  const [location, setLocation] = useState(event?.location || '');
  const [description, setDescription] = useState(event?.description || '');
  const [expanded, setExpanded] = useState(!!(event?.location || event?.description));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const submitting = useRef(false);

  async function save() {
    if (submitting.current) return;
    if (!title.trim()) { setError('Scrivi cosa devi fare.'); return; }
    const match = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(date);
    if (!match) { setError('Inserisci il giorno nel formato 28/09/2026.'); return; }
    if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(time)) { setError('Inserisci l’ora nel formato 09:00.'); return; }
    const minutes = Number(duration);
    if (!Number.isInteger(minutes) || minutes < 5 || minutes > 1440) {
      setError('La durata deve essere tra 5 e 1440 minuti.'); return;
    }
    const body: HomeEventInput = {
      title: title.trim(), day: `${match[3]}-${match[2]}-${match[1]}`, time,
      duration_minutes: minutes, location: location.trim(), description: description.trim(), timezone,
    };
    submitting.current = true;
    setBusy(true); onBusyChange?.(true); setError('');
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 20000);
    try {
      let saved: HomeCalendarEvent | CalendarEventDetail;
      if (event) {
        saved = await api.updateHomeEvent(event.id, { ...body, expected_updated_at: event.updated_at! }, controller.signal);
      } else {
        // A lost response or a remount retries the same request. Store only a
        // digest and a random key, never the person's appointment details.
        const digest = await digestStringAsync(CryptoDigestAlgorithm.SHA256, JSON.stringify([user?.user_id, body]));
        const key = `ora:calendar:pending:${digest}`;
        const requestId = await AsyncStorage.getItem(key) || randomUUID();
        await AsyncStorage.setItem(key, requestId);
        saved = await api.createHomeEvent({ ...body, request_id: requestId }, controller.signal);
        await AsyncStorage.removeItem(key).catch(() => undefined);
      }
      onSaved(saved);
    } catch (e: any) {
      setError(e?.status === 409
        ? 'L’impegno è cambiato. Chiudi la modifica e riapri la scheda per vedere i dati aggiornati.'
        : e?.status === 422
          ? 'Controlla giorno e ora: questa data o questo orario non sono validi.'
          : 'Non riesco a confermare il salvataggio. Riprova: lo stesso impegno non verrà duplicato.');
    } finally {
      clearTimeout(timer);
      submitting.current = false;
      setBusy(false); onBusyChange?.(false);
    }
  }

  const inputStyle = [styles.input, { color: colors.textPrimary, borderColor: colors.border }];
  const labelStyle = [styles.label, { color: colors.textSecondary }];
  return (
    <View style={styles.form} testID="calendar-event-form">
      <Text style={labelStyle}>Impegno</Text>
      <TextInput value={title} onChangeText={setTitle} editable={!busy} style={inputStyle} placeholder="Es. Visita dal dentista" placeholderTextColor={colors.textTertiary} maxLength={200} accessibilityLabel="Titolo dell'impegno" />
      {event ? <>
        <Text style={labelStyle}>Giorno · gg/mm/aaaa</Text>
        <TextInput value={date} onChangeText={setDate} editable={!busy} style={inputStyle} maxLength={10} keyboardType="numbers-and-punctuation" accessibilityLabel="Giorno dell'impegno" />
      </> : null}
      <View style={styles.row}>
        <View style={styles.field}>
          <Text style={labelStyle}>Ora</Text>
          <TextInput value={time} onChangeText={setTime} editable={!busy} style={inputStyle} maxLength={5} keyboardType="numbers-and-punctuation" accessibilityLabel="Ora dell'impegno, formato 09:00" />
        </View>
        <View style={styles.field}>
          <Text style={labelStyle}>Durata · minuti</Text>
          <TextInput value={duration} onChangeText={setDuration} editable={!busy} style={inputStyle} maxLength={4} keyboardType="number-pad" accessibilityLabel="Durata in minuti" />
        </View>
      </View>
      <Pressable onPress={() => setExpanded(!expanded)} disabled={busy} accessibilityRole="button" accessibilityState={{ expanded }} style={styles.more}>
        <Text style={{ color: colors.accent }}>{expanded ? 'Nascondi luogo e note' : '+ Luogo e note'}</Text>
      </Pressable>
      {expanded ? <>
        <Text style={labelStyle}>Luogo</Text>
        <TextInput value={location} onChangeText={setLocation} editable={!busy} style={inputStyle} placeholder="Indirizzo o nome del posto" placeholderTextColor={colors.textTertiary} maxLength={300} accessibilityLabel="Luogo dell'impegno" />
        <Text style={labelStyle}>Note</Text>
        <TextInput value={description} onChangeText={setDescription} editable={!busy} style={[inputStyle, styles.notes]} placeholder="Cosa ricordare o portare con te" placeholderTextColor={colors.textTertiary} maxLength={800} multiline accessibilityLabel="Note dell'impegno" />
      </> : null}
      <Text style={[styles.hint, { color: colors.textSecondary }]}>Calendario ORA · {timezone.replace(/_/g, ' ')}</Text>
      {error ? <Text accessibilityRole="alert" style={{ color: colors.error }}>{error}</Text> : null}
      <View style={styles.row}>
        <Pressable disabled={busy} onPress={onCancel} accessibilityRole="button" style={styles.cancel}>
          <Text style={{ color: colors.textSecondary }}>Annulla</Text>
        </Pressable>
        <Pressable disabled={busy} onPress={() => void save()} accessibilityRole="button" accessibilityLabel="Salva impegno" accessibilityState={{ busy, disabled: busy }} style={[styles.save, { backgroundColor: colors.accent, opacity: busy ? 0.65 : 1 }]} testID="rail-save-event">
          {busy ? <ActivityIndicator color={colors.onAccent} /> : <Text style={{ color: colors.onAccent, fontWeight: '700' }}>{event ? 'Salva modifiche' : 'Salva impegno'}</Text>}
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  form: { gap: 8, marginTop: 12 },
  label: { fontSize: 13, fontWeight: '500' },
  input: { borderWidth: 1, borderRadius: tokens.radius.md, padding: 12, minHeight: 46, fontSize: 16 },
  row: { flexDirection: 'row', gap: 12, alignItems: 'center' },
  field: { flex: 1, gap: 8 },
  notes: { minHeight: 80, textAlignVertical: 'top' },
  more: { minHeight: 44, justifyContent: 'center' },
  hint: { fontSize: 12, marginBottom: 4 },
  save: { flex: 1, minHeight: 48, borderRadius: tokens.radius.md, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 10 },
  cancel: { minHeight: 48, paddingHorizontal: 12, justifyContent: 'center' },
});
