/**
 * Prepariamo ORA — la guida al primo avvio.
 *
 * Senza notifiche, posizione e casa ORA non ha niente da calcolare né un modo
 * per dirtelo: il primo punto del mattino (30/10) è uscito vuoto proprio per
 * questo. Sei passi, ognuno si può saltare; lo stato viene dal server, quindi
 * la guida riprende da dove eri anche su un altro dispositivo.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';

import { api, type PlaceSuggestion } from '@/src/api/client';
import { PaginaOra } from '@/src/components/pagine/PaginaOra';
import { OraCard } from '@/src/components/ora-ui';
import { MorningBrief } from '@/src/components/account/MorningBrief';
import { enablePush } from '@/src/ambient/pushRegistration';
import { webPushSupport } from '@/src/ambient/webPush';
import { ora, oraType } from '@/src/theme/oraSurface';
import { humanizeError } from '@/src/utils/errors';

type Status = Awaited<ReturnType<typeof api.setupStatus>>;
type Mode = Status['travel'];

const MODES: Array<{ id: Mode; label: string; icon: keyof typeof Ionicons.glyphMap }> = [
  { id: 'drive', label: 'In auto', icon: 'car-outline' },
  { id: 'walk', label: 'A piedi', icon: 'walk-outline' },
  { id: 'transit', label: 'Con i mezzi', icon: 'bus-outline' },
  { id: 'bicycle', label: 'In bici', icon: 'bicycle-outline' },
];

export const PROVE = [
  'Ricordami tra 2 minuti di bere un bicchiere d\'acqua',
  'Ho steso i panni',
  'Ho avviato la lavastoviglie',
  'Domani alle 10 ho un appuntamento dal medico in città',
];

export default function Inizia() {
  const router = useRouter();
  const [st, setSt] = useState<Status | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [errore, setErrore] = useState('');
  const [q, setQ] = useState('');
  const [sugg, setSugg] = useState<PlaceSuggestion[]>([]);
  const session = useRef(`setup-${Date.now()}`);

  const leggi = useCallback(async () => {
    try { setSt(await api.setupStatus()); } catch (e) { setErrore(humanizeError(e)); }
  }, []);
  useEffect(() => { void leggi(); }, [leggi]);

  const fai = async (key: string, fn: () => Promise<unknown>) => {
    setBusy(key); setErrore('');
    try { await fn(); await leggi(); } catch (e) { setErrore(humanizeError(e)); } finally { setBusy(null); }
  };

  useEffect(() => {
    if (q.trim().length < 3) { setSugg([]); return; }
    const t = setTimeout(() => {
      api.placesSuggest(q.trim(), session.current).then(r => setSugg(r.suggestions || [])).catch(() => setSugg([]));
    }, 300);
    return () => clearTimeout(t);
  }, [q]);

  const scegliCasa = (s: PlaceSuggestion) => fai('home', async () => {
    if (!s.place_id) throw new Error('Scegli un indirizzo dall\'elenco.');
    const r = await api.placesResolve(s.place_id, session.current);
    if (!r.available) throw new Error('Non riesco a trovare questo indirizzo. Prova a scriverlo per intero.');
    await api.placesCreate({ label: 'Casa', role: 'home', latitude: r.latitude, longitude: r.longitude,
      address: r.address || undefined, locality: r.locality || undefined, google_place_id: r.place_id,
      location_source: 'google_place', source: 'user_stated' });
    setQ(''); setSugg([]);
  });

  const installa = webPushSupport() === 'install_required';
  const fatti = st ? 5 - st.missing.length : 0;

  return (
    <PaginaOra titolo="Prepariamo ORA" sottotitolo={st ? `${fatti} di 5 fatti` : undefined} attiva="index" testID="pagina-inizia">
      <Text style={[oraType.body, { color: ora.ink2 }]}>
        Due minuti, una volta sola. Così ORA può calcolare da sola i tempi della tua giornata e dirtelo al momento giusto.
      </Text>

      <Passo n={1} fatto={!!st?.notifications} titolo="Le notifiche" testo={installa
        ? 'Su iPhone le notifiche arrivano solo se ORA è sulla schermata Home: in Safari tocca Condividi → Aggiungi a Home, poi apri ORA da lì e torna qui.'
        : 'Senza notifiche ORA non può avvisarti quando partire, quando ritirare i panni o dei promemoria.'}>
        {!installa && !st?.notifications ? <Bottone label="Attiva le notifiche" busy={busy === 'push'}
          onPress={() => void fai('push', () => enablePush())} testID="setup-push" /> : null}
      </Passo>

      <Passo n={2} fatto={!!st?.location} titolo="La posizione" testo="Serve per calcolare quando partire da dove sei. ORA la usa solo mentre l'app è aperta.">
        {!st?.location ? <Bottone label="Condividi la posizione" busy={busy === 'loc'} testID="setup-location"
          onPress={() => void fai('loc', async () => {
            const { shareForegroundPosition } = await import('@/src/location/shareForeground');
            await shareForegroundPosition();
          })} /> : null}
      </Passo>

      <Passo n={3} fatto={!!st?.home} titolo="Casa tua" testo="Da qui partono i calcoli quando il telefono non dà la posizione, e da qui viene il meteo del mattino e dei panni stesi.">
        {!st?.home ? <View style={{ gap: 8, alignSelf: 'stretch' }}>
          <TextInput value={q} onChangeText={setQ} placeholder="Indirizzo di casa" autoCorrect={false}
            style={[styles.input, { borderColor: ora.hairline, color: ora.ink }]} testID="setup-home-input" />
          {sugg.filter(s => s.place_id).slice(0, 5).map(s => (
            <Pressable key={s.place_id} onPress={() => void scegliCasa(s)} accessibilityRole="button"
              style={styles.sugg} testID={`setup-home-${s.place_id}`}>
              <Text style={[oraType.body, { color: ora.ink }]}>{s.primary || s.text}</Text>
              {s.secondary ? <Text style={[oraType.small, { color: ora.ink3 }]}>{s.secondary}</Text> : null}
            </Pressable>
          ))}
        </View> : null}
      </Passo>

      <Passo n={4} fatto={!!st?.travel_mode} titolo="Come ti muovi" testo="Per dirti quando partire. Puoi cambiarlo quando vuoi, anche scrivendolo a ORA.">
        <View style={styles.row}>
          {MODES.map(m => (
            <Pressable key={m.id} onPress={() => void fai('mode', () => api.setTravelMode(m.id))} accessibilityRole="button"
              style={[styles.chip, st?.travel_mode && st.travel === m.id && { backgroundColor: ora.cta, borderColor: ora.cta }]}
              testID={`setup-mode-${m.id}`}>
              <Ionicons name={m.icon} size={16} color={st?.travel_mode && st.travel === m.id ? '#fff' : ora.ink} />
              <Text style={{ color: st?.travel_mode && st.travel === m.id ? '#fff' : ora.ink, fontWeight: '600' }}>{m.label}</Text>
            </Pressable>
          ))}
        </View>
      </Passo>

      <Passo n={5} fatto={!!st?.morning_brief} titolo="Il punto del mattino" testo="Ogni mattina la giornata in una notifica. Scegli l'ora, o spegnilo.">
        {!st?.morning_brief ? <Bottone label="Va bene alle 8" busy={busy === 'brief'} testID="setup-brief"
          onPress={() => void fai('brief', () => api.setMorningBrief({ enabled: true, hour: 8 }))} /> : null}
      </Passo>
      {st?.morning_brief ? <MorningBrief /> : null}

      <OraCard style={styles.card} testID="setup-prove">
        <Text style={[oraType.title, { color: ora.ink }]}>Prova subito</Text>
        <Text style={[oraType.body, { color: ora.ink2 }]}>Tocca una frase: si apre ORA con il testo già scritto.</Text>
        {PROVE.map(p => (
          <Pressable key={p} accessibilityRole="button" style={styles.sugg} testID={`setup-try-${PROVE.indexOf(p)}`}
            onPress={() => router.push({ pathname: '/ora', params: { draft: p } } as never)}>
            <Text style={[oraType.body, { color: ora.deep }]}>«{p}»</Text>
          </Pressable>
        ))}
      </OraCard>

      {errore ? <Text accessibilityRole="alert" style={{ color: ora.attention }}>{errore}</Text> : null}
      <Pressable accessibilityRole="button" testID="setup-done" style={styles.fine}
        onPress={() => void api.setupDismiss().finally(() => router.replace('/' as never))}>
        <Text style={[oraType.body, { color: ora.ink3 }]}>{st?.done ? 'Fatto, torna alla Home' : 'Finisco più tardi'}</Text>
      </Pressable>
    </PaginaOra>
  );
}

function Passo({ n, fatto, titolo, testo, children }: { n: number; fatto: boolean; titolo: string; testo: string; children?: React.ReactNode }) {
  return (
    <OraCard style={styles.card} testID={`setup-step-${n}`}>
      <View style={styles.head}>
        <Ionicons name={fatto ? 'checkmark-circle' : 'ellipse-outline'} size={22} color={fatto ? ora.cta : ora.ink3} />
        <Text style={[oraType.title, { color: ora.ink, flex: 1 }]}>{titolo}</Text>
      </View>
      <Text style={[oraType.body, { color: ora.ink2 }]}>{testo}</Text>
      {children}
    </OraCard>
  );
}

function Bottone({ label, onPress, busy, testID }: { label: string; onPress: () => void; busy?: boolean; testID?: string }) {
  return (
    <Pressable accessibilityRole="button" onPress={onPress} disabled={busy} testID={testID}
      style={({ pressed }) => [styles.cta, pressed && { opacity: 0.8 }]}>
      <Text style={{ color: '#fff', fontWeight: '600' }}>{busy ? '…' : label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: { gap: 10, padding: 20, alignItems: 'flex-start' },
  head: { flexDirection: 'row', alignItems: 'center', gap: 10, alignSelf: 'stretch' },
  cta: { minHeight: 44, paddingHorizontal: 16, paddingVertical: 12, borderRadius: 12, backgroundColor: ora.cta },
  input: { borderWidth: 1, borderRadius: 12, minHeight: 44, paddingHorizontal: 12, fontSize: 16, alignSelf: 'stretch' },
  sugg: { paddingVertical: 8, alignSelf: 'stretch' },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { flexDirection: 'row', alignItems: 'center', gap: 6, borderWidth: 1, borderColor: ora.hairline, borderRadius: 20,
    paddingHorizontal: 12, minHeight: 40 },
  fine: { alignSelf: 'center', paddingVertical: 14 },
});
