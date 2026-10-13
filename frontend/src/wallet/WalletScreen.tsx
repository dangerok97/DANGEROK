import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Image, Modal, Platform, Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View, useWindowDimensions } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import * as Crypto from 'expo-crypto';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { useAuth } from '@/src/contexts/AuthContext';
import { FORMATS, walletClient, type Candidate, type CardInput, type LoyaltyCard } from './client';
import { pickPhoto } from './pickPhoto';

const label = (format: string) => format.replace('_', ' ').replace('QR CODE', 'QR');
const message = (e: unknown) => e instanceof Error ? e.message : 'Operazione non riuscita. Riprova.';

export default function WalletRoute() {
  const { user } = useAuth();
  return user ? <WalletScreen key={user.user_id} /> : null;
}

function WalletScreen() {
  const { colors } = useTheme();
  const router = useRouter();
  const { width, height } = useWindowDimensions();
  const alive = useRef(true);
  const [cards, setCards] = useState<LoyaltyCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState<LoyaltyCard | null>(null);
  const [draft, setDraft] = useState<CardInput | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [checkout, setCheckout] = useState(false);
  const [notice, setNotice] = useState('');
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const token = await walletClient.token();
      if (!token) throw new Error('Accedi nuovamente a ORA.');
      const result = await walletClient.list(token);
      if (alive.current) setCards(result.cards);
    } catch (e) {
      if (alive.current) setError(message(e));
    } finally { if (alive.current) setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    if (!checkout || Platform.OS !== 'web') return;
    let lock: { release: () => Promise<void> } | undefined;
    let cancelled = false;
    const wakeLock = (navigator as any).wakeLock;
    wakeLock?.request('screen').then((value: typeof lock) => {
      if (cancelled) void value?.release(); else lock = value;
    }).catch(() => {});
    return () => { cancelled = true; void lock?.release(); };
  }, [checkout]);

  const begin = () => {
    setDraft({ id: Crypto.randomUUID().replace(/-/g, ''), name: '', code: '', format: 'CODE_128',
      source: 'manual', static_confirmed: false, revision: 0, favorite: false });
    setSelected(null); setError(''); setNotice(''); setCandidates([]);
  };
  const change = (value: Partial<CardInput>) => setDraft(d => d ? { ...d, ...value } : d);
  const importPhoto = async (camera: boolean) => {
    setError(''); setBusy(true);
    try {
      const photo = await pickPhoto(camera);
      if (!photo || !alive.current) return;
      const token = await walletClient.token();
      if (!token) throw new Error('Accedi nuovamente a ORA.');
      const result = await walletClient.decode(token, photo);
      if (!alive.current) return;
      if (result.candidates.length === 1) {
        change({ ...result.candidates[0], source: 'image', static_confirmed: false });
        setCandidates([]); setNotice('Codice letto. Controlla il nome e conferma che sia una tessera statica.');
      } else { setCandidates(result.candidates); setNotice('La foto contiene più codici: scegli quello della tessera.'); }
    } catch (e) { if (alive.current) setError(message(e)); }
    finally { if (alive.current) setBusy(false); }
  };
  const save = async () => {
    if (!draft?.name.trim() || !draft.code || !draft.static_confirmed || busy) return;
    setBusy(true); setError('');
    try {
      const token = await walletClient.token();
      if (!token) throw new Error('Accedi nuovamente a ORA.');
      const result = await walletClient.save(token, draft);
      if (!alive.current) return;
      setCards(all => [...all.filter(c => c.id !== result.card.id), result.card]);
      setSelected(result.card); setDraft(null); setNotice('Tessera salvata. L’accettazione alla cassa è ancora da verificare.');
    } catch (e) { if (alive.current) setError(message(e)); }
    finally { if (alive.current) setBusy(false); }
  };
  const remove = async () => {
    if (!selected || busy) return;
    setBusy(true); setError('');
    try {
      const token = await walletClient.token();
      if (!token) throw new Error('Accedi nuovamente a ORA.');
      await walletClient.remove(token, selected);
      if (!alive.current) return;
      setCards(all => all.filter(c => c.id !== selected.id));
      setSelected(null); setConfirmDelete(false); setNotice('Tessera eliminata dal portafoglio ORA.');
    } catch (e) { if (alive.current) setError(message(e)); }
    finally { if (alive.current) setBusy(false); }
  };

  const panel = { backgroundColor: colors.surface, borderColor: colors.border };
  const text = { color: colors.textPrimary };
  const secondary = { color: colors.textSecondary };
  const button = (title: string, action: () => void, disabled = false, primary = false, id?: string) => (
    <Pressable onPress={action} disabled={disabled} accessibilityRole="button" accessibilityState={{ disabled }} testID={id}
      style={({ pressed }) => [s.button, panel, primary && { backgroundColor: colors.accent }, (pressed || disabled) && { opacity: 0.5 }]}>
      <Text style={[s.buttonText, primary ? { color: colors.onAccent } : text]}>{title}</Text>
    </Pressable>
  );
  const visible = cards.filter(c => c.name.toLocaleLowerCase().includes(query.toLocaleLowerCase()))
    .sort((a, b) => Number(b.favorite) - Number(a.favorite) || a.name.localeCompare(b.name));
  const closeDetail = () => { setSelected(null); setConfirmDelete(false); setError(''); setNotice(''); };
  const edit = () => {
    if (!selected) return;
    const { id, name, format, code, static_confirmed, source, revision, favorite } = selected;
    setDraft({ id, name, format, code, static_confirmed, source, revision, favorite });
    setSelected(null); setConfirmDelete(false); setNotice(''); setError('');
  };

  return <SafeAreaView style={[s.page, { backgroundColor: colors.backgroundPrimary }]} edges={['top', 'left', 'right']}>
    <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={[s.content, { paddingBottom: 140 }]} testID="wallet-screen">
      <View style={s.row}>
        <View style={s.grow}><Text accessibilityRole="header" style={[s.title, text]}>Portafoglio</Text>
          <Text style={[s.body, secondary]}>Le tue tessere fedeltà, pronte da mostrare.</Text></View>
        {button('Vita', () => router.push('/(tabs)/contesti' as any))}
      </View>
      <Text style={[s.small, secondary]}>Solo codici statici. Non è un sistema di pagamento e non sostituisce NFC, codici che cambiano o coupon da attivare nell’app del negozio.</Text>
      {error ? <View accessibilityRole="alert" style={[s.panel, panel]} testID="wallet-error"><Text style={text}>{error}</Text></View> : null}
      {notice ? <Text accessibilityLiveRegion="polite" style={[s.body, secondary]}>{notice}</Text> : null}

      {draft ? <View style={[s.panel, panel]} testID="wallet-editor">
        <Text style={[s.heading, text]}>{draft.revision ? 'Modifica tessera' : 'Aggiungi tessera'}</Text>
        <Text style={[s.small, secondary]}>La foto viene inviata al server ORA solo per leggere il codice e non viene conservata né inviata a un modello AI.</Text>
        <View style={s.row}>
          {Platform.OS === 'web' ? button('Fotografa il codice', () => { void importPhoto(true); }, busy, false, 'wallet-camera') : null}
          {button('Importa foto', () => { void importPhoto(false); }, busy, false, 'wallet-import')}
        </View>
        {candidates.map((candidate, index) => button(`${label(candidate.format)} · ${candidate.code.length > 35 ? candidate.code.slice(0, 35) + '…' : candidate.code}`, () => {
          change({ ...candidate, source: 'image', static_confirmed: false }); setCandidates([]);
        }, busy, false, `wallet-candidate-${index}`))}
        <Text style={[s.fieldLabel, text]}>Nome del negozio o della tessera</Text>
        <TextInput value={draft.name} onChangeText={name => change({ name })} maxLength={80} placeholder="Es. Tessera supermercato"
          placeholderTextColor={colors.textTertiary} style={[s.input, panel, text]} accessibilityLabel="Nome tessera" testID="wallet-name" editable={!busy} />
        <Text style={[s.fieldLabel, text]}>Formato del codice originale</Text>
        <View style={s.row}>{FORMATS.map(format => <Pressable key={format} onPress={() => change({ format, source: 'manual' })} disabled={busy}
          accessibilityRole="radio" accessibilityState={{ checked: draft.format === format }} style={[s.chip, panel, draft.format === format && { borderColor: colors.accent, borderWidth: 2 }]}>
          <Text style={text}>{label(format)}</Text></Pressable>)}</View>
        <Text style={[s.small, secondary]}>Non conosci il formato? Importa la foto: ORA lo rileva. Non scegliere un formato diverso solo per riuscire a salvare.</Text>
        <Text style={[s.fieldLabel, text]}>Codice esatto, inclusi gli zeri iniziali</Text>
        <TextInput value={draft.code} onChangeText={code => change({ code, source: 'manual' })} maxLength={512} autoCapitalize="none" autoCorrect={false}
          style={[s.input, panel, text]} accessibilityLabel="Codice tessera" testID="wallet-code" editable={!busy} />
        <View style={s.row}><Switch value={draft.favorite} onValueChange={favorite => change({ favorite })} disabled={busy} accessibilityLabel="Tessera preferita" />
          <Text style={[s.body, text, s.grow]}>Mostra fra le preferite</Text></View>
        <View style={s.row}><Switch value={draft.static_confirmed} onValueChange={static_confirmed => change({ static_confirmed })} disabled={busy} accessibilityLabel="Confermo tessera statica" testID="wallet-static" />
          <Text style={[s.body, text, s.grow]}>È una tessera fedeltà con un codice che non cambia. Non sto inserendo una carta di pagamento.</Text></View>
        <View style={s.row}>{button(busy ? 'Operazione in corso…' : 'Salva tessera', () => { void save(); }, busy || !draft.static_confirmed || !draft.name.trim() || !draft.code, true, 'wallet-save')}
          {button('Annulla', () => { setDraft(null); setError(''); setCandidates([]); setNotice(''); }, busy)}</View>
      </View> : selected ? <View style={[s.panel, panel]} testID="wallet-card-detail">
        <Text style={[s.heading, text]}>{selected.name}</Text>
        <View style={s.codeBox}><Image source={{ uri: selected.image }} style={[s.barcode, selected.format === 'QR_CODE' && { height: 300 }]} resizeMode="contain" accessibilityLabel={`Codice ${selected.name}`} />
          <Text selectable style={s.codeText}>{selected.code}</Text></View>
        <Text style={[s.small, secondary]}>{label(selected.format)} · Codice riprodotto e riletto dal software. Accettazione in negozio non ancora verificata.</Text>
        <View style={s.row}>{button('Mostra alla cassa', () => setCheckout(true), false, true, 'wallet-checkout')}{button('Modifica', edit, busy)}{button('Tutte le tessere', closeDetail, busy)}</View>
        {confirmDelete ? <View style={[s.panel, panel]}><Text style={[s.body, text]}>Eliminare questa tessera da ORA? La tessera del negozio non viene annullata.</Text>
          <View style={s.row}>{button('Elimina definitivamente', () => { void remove(); }, busy, false, 'wallet-confirm-delete')}{button('Non eliminare', () => setConfirmDelete(false), busy)}</View></View>
          : button('Elimina da ORA', () => setConfirmDelete(true), busy, false, 'wallet-delete')}
      </View> : <>
        <View style={s.row}>{button('Aggiungi tessera', begin, busy, true, 'wallet-add')}{button('Aggiorna', () => { void load(); }, loading || busy, false, 'wallet-refresh')}</View>
        <TextInput value={query} onChangeText={setQuery} placeholder="Cerca una tessera" placeholderTextColor={colors.textTertiary}
          accessibilityLabel="Cerca tessera" style={[s.input, panel, text]} testID="wallet-search" />
        {loading ? <ActivityIndicator accessibilityLabel="Caricamento tessere" color={colors.accent} /> : null}
        {!loading && !cards.length && !error ? <View style={[s.panel, panel]} testID="wallet-empty"><Ionicons name="wallet-outline" size={38} color={colors.textSecondary} />
          <Text style={[s.heading, text]}>La prossima tessera, qui.</Text><Text style={[s.body, secondary]}>Aggiungi il codice dalla foto oppure inseriscilo manualmente. Nessuna carta di esempio viene aggiunta al tuo account.</Text></View> : null}
        {!loading && cards.length > 0 && !visible.length ? <Text style={[s.body, secondary]}>Nessuna tessera corrisponde alla ricerca.</Text> : null}
        <View style={s.grid}>{visible.map(card => <Pressable key={card.id} onPress={() => { setSelected(card); setError(''); setNotice(''); }} accessibilityRole="button"
          accessibilityLabel={`Apri ${card.name}`} testID={`wallet-card-${card.id}`} style={({ pressed }) => [s.card, panel, { opacity: pressed ? 0.75 : 1 }]}>
          <Ionicons name={card.favorite ? 'star' : 'barcode-outline'} size={24} color={colors.accent} />
          <Text style={[s.heading, text]}>{card.name}</Text><Text style={[s.small, secondary]}>{label(card.format)} · Mostra il codice</Text>
        </Pressable>)}</View>
      </>}
    </ScrollView>
    <Modal visible={checkout && !!selected} animationType="fade" onRequestClose={() => setCheckout(false)}>
      <SafeAreaView style={s.checkout}>
        <ScrollView contentContainerStyle={s.checkoutContent}>
          <Text style={s.checkoutTitle}>{selected?.name}</Text>
          <Text style={s.checkoutHint}>Aumenta la luminosità del telefono e mostra il codice al lettore.</Text>
          {selected ? <Image source={{ uri: selected.image }} resizeMode="contain" style={{ width: Math.min(width - 40, 1000), height: selected.format === 'QR_CODE' ? Math.min(width - 40, 450) : Math.min(height * 0.45, 340) }} accessibilityLabel="Codice da mostrare alla cassa" /> : null}
          <Text selectable style={s.checkoutCode}>{selected?.code}</Text>
          <Text style={s.checkoutHint}>Se non viene letto, mostra il numero o usa la tessera originale.</Text>
          <Pressable onPress={() => setCheckout(false)} accessibilityRole="button" style={s.closeCheckout} testID="wallet-close-checkout"><Text style={{ color: '#fff', fontSize: 17 }}>Chiudi codice</Text></Pressable>
        </ScrollView>
      </SafeAreaView>
    </Modal>
  </SafeAreaView>;
}

const s = StyleSheet.create({
  page: { flex: 1 }, content: { width: '100%', maxWidth: 1000, alignSelf: 'center', padding: tokens.spacing.xl, gap: 18 },
  row: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 12 }, grow: { flex: 1, minWidth: 180 },
  title: { fontSize: 32, fontWeight: '700', letterSpacing: -0.8 }, heading: { fontSize: 21, fontWeight: '600' },
  body: { fontSize: 15, lineHeight: 22 }, small: { fontSize: 13, lineHeight: 20 }, fieldLabel: { fontSize: 14, fontWeight: '600' },
  button: { minHeight: 46, borderRadius: tokens.radius.md, borderWidth: 1, paddingHorizontal: 18, paddingVertical: 12, justifyContent: 'center' },
  buttonText: { fontSize: 15, fontWeight: '600' }, panel: { borderWidth: 1, borderRadius: tokens.radius.lg, padding: 20, gap: 16 },
  input: { minHeight: 48, borderWidth: 1, borderRadius: tokens.radius.md, paddingHorizontal: 14, paddingVertical: 12, fontSize: 16 },
  chip: { borderWidth: 1, borderRadius: 10, padding: 12, minHeight: 44 }, grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 14 },
  card: { flexGrow: 1, flexBasis: 250, minHeight: 140, borderRadius: tokens.radius.lg, borderWidth: 1, padding: 20, gap: 12 },
  codeBox: { backgroundColor: '#fff', borderRadius: 12, padding: 16, gap: 12 }, barcode: { width: '100%', height: 200 },
  codeText: { color: '#000', textAlign: 'center', fontSize: 18 }, checkout: { flex: 1, backgroundColor: '#fff' },
  checkoutContent: { flexGrow: 1, justifyContent: 'center', alignItems: 'center', padding: 20, gap: 24 },
  checkoutTitle: { fontSize: 28, fontWeight: '700', color: '#000', textAlign: 'center' },
  checkoutHint: { color: '#333', fontSize: 15, textAlign: 'center', maxWidth: 500 }, checkoutCode: { color: '#000', fontSize: 22, textAlign: 'center' },
  closeCheckout: { padding: 16, minHeight: 50, borderRadius: 14, backgroundColor: '#111', alignSelf: 'center' },
});
