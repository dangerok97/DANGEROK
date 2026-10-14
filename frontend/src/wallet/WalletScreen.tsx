import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Image, Modal, Platform, Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View, useWindowDimensions } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import * as Crypto from 'expo-crypto';
import * as Clipboard from 'expo-clipboard';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { useAuth } from '@/src/contexts/AuthContext';
import { FORMATS, walletClient, type Candidate, type CardInput, type LoyaltyCard } from './client';
import { pickPhoto } from './pickPhoto';
import { cleanRecent, clearRecent, forgetRecent, getRecent, orderCards, recordRecent } from './recent';

const label = (format: string) => format.replace('_', ' ').replace('QR CODE', 'QR');
const message = (e: unknown) => e instanceof Error ? e.message : 'Operazione non riuscita. Riprova.';

export default function WalletRoute() {
  const { user } = useAuth();
  return user ? <WalletScreen key={user.user_id} owner={user.user_id} /> : null;
}

function WalletScreen({ owner }: { owner: string }) {
  const { colors } = useTheme();
  const router = useRouter();
  const { width, height } = useWindowDimensions();
  const alive = useRef(true);
  const checkoutOrder = useRef<string[]>([]);
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
  const [recentIds, setRecentIds] = useState<string[]>([]);
  const [openedFromList, setOpenedFromList] = useState(false);
  const [rotated, setRotated] = useState(false);
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState('');
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => {
    let cancelled = false;
    void getRecent(owner).then(ids => { if (!cancelled && alive.current) setRecentIds(ids); })
      .catch(() => { /* optional ordering: never prevent wallet use */ });
    return () => { cancelled = true; };
  }, [owner]);

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

  const showCode = (card: LoyaltyCard, fromList: boolean, preserveSequence = false) => {
    // Lock the order as checkout begins. Recency updates must not make
    // Previous/Next bounce between the first two cards.
    if (!preserveSequence) checkoutOrder.current = orderCards(cards, recentIds).map(item => item.id);
    setSelected(card);
    setOpenedFromList(fromList);
    setRotated(false);
    setCopied(false);
    setCopyError('');
    setNotice('');
    setError('');
    setCheckout(true);
    // Only IDs are persisted, on this device and for this account.
    setRecentIds(existing => cleanRecent([card.id, ...existing]));
    void recordRecent(owner, card.id).catch(() => undefined);
  };
  const closeCode = () => {
    checkoutOrder.current = [];
    setCheckout(false);
    setRotated(false);
    setCopied(false);
    setCopyError('');
    if (openedFromList) setSelected(null); // back to the ready-to-scan list
    setOpenedFromList(false);
  };
  const copyCode = async () => {
    if (!selected) return;
    try {
      await Clipboard.setStringAsync(selected.code); // explicit user gesture only
      if (alive.current) { setCopied(true); setCopyError(''); }
    } catch {
      if (alive.current) { setCopied(false); setCopyError('Copia non disponibile. Leggi il numero sotto il codice.'); }
    }
  };

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
      } else { setCandidates(result.candidates); setNotice('Sono possibili più codici o formati: scegli quello che coincide con il numero stampato sulla tessera.'); }
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
  const toggleFavorite = async (card: LoyaltyCard) => {
    if (busy) return;
    setBusy(true); setError('');
    try {
      const token = await walletClient.token();
      if (!token) throw new Error('Accedi nuovamente a ORA.');
      const { id, name, format, code, static_confirmed, source, revision, favorite } = card;
      const response = await walletClient.save(token, {
        id, name, format, code, static_confirmed, source, revision, favorite: !favorite,
      });
      if (alive.current) setCards(all => all.map(item => item.id === id ? response.card : item));
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
      setRecentIds(ids => ids.filter(id => id !== selected.id));
      void forgetRecent(owner, selected.id).catch(() => undefined);
      setSelected(null); setConfirmDelete(false); setNotice('Tessera eliminata dal portafoglio ORA.');
    } catch (e) { if (alive.current) setError(message(e)); }
    finally { if (alive.current) setBusy(false); }
  };

  const panel = { backgroundColor: colors.surface, borderColor: colors.border };
  const text = { color: colors.textPrimary };
  const secondary = { color: colors.textSecondary };
  const button = (title: string, action: () => void, disabled = false, primary = false, id?: string) => (
    <Pressable key={id} onPress={action} disabled={disabled} accessibilityRole="button" accessibilityState={{ disabled }} testID={id}
      style={({ pressed }) => [s.button, panel, primary && { backgroundColor: colors.accent }, (pressed || disabled) && { opacity: 0.5 }]}>
      <Text style={[s.buttonText, primary ? { color: colors.onAccent } : text]}>{title}</Text>
    </Pressable>
  );
  const sorted = orderCards(cards, recentIds);
  const visible = sorted.filter(c => c.name.toLocaleLowerCase().includes(query.toLocaleLowerCase()));
  const recentCards = recentIds.map(id => cards.find(card => card.id === id))
    .filter((card): card is LoyaltyCard => !!card).slice(0, 4);
  const stepCard = (delta: number) => {
    const ids = checkoutOrder.current;
    if (!selected || ids.length < 2) return;
    const index = ids.indexOf(selected.id);
    if (index < 0) return;
    const next = cards.find(card => card.id === ids[(index + delta + ids.length) % ids.length]);
    if (next) showCode(next, openedFromList, true);
  };
  const resetRecent = () => {
    void clearRecent(owner).then(() => { if (alive.current) setRecentIds([]); })
      .catch(() => setNotice('Non riesco a cancellare i recenti su questo dispositivo.'));
  };
  const closeDetail = () => { setSelected(null); setConfirmDelete(false); setError(''); setNotice(''); setCopied(false); };
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
        <Text style={[s.small, secondary]}>La foto viene inviata al server ORA solo per leggere il codice. Il server non la conserva e non la invia a un modello AI.</Text>
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
        <View style={s.row}>{button('Mostra alla cassa', () => showCode(selected, false), false, true, 'wallet-checkout')}{button('Modifica', edit, busy)}{button('Tutte le tessere', closeDetail, busy)}</View>
        {confirmDelete ? <View style={[s.panel, panel]}><Text style={[s.body, text]}>Eliminare questa tessera da ORA? La tessera del negozio non viene annullata.</Text>
          <View style={s.row}>{button('Elimina definitivamente', () => { void remove(); }, busy, false, 'wallet-confirm-delete')}{button('Non eliminare', () => setConfirmDelete(false), busy)}</View></View>
          : button('Elimina da ORA', () => setConfirmDelete(true), busy, false, 'wallet-delete')}
      </View> : <>
        <View style={s.row}>{button('Aggiungi tessera', begin, loading || busy, true, 'wallet-add')}{button('Aggiorna', () => { void load(); }, loading || busy, false, 'wallet-refresh')}</View>
        <TextInput value={query} onChangeText={setQuery} placeholder="Cerca una tessera" placeholderTextColor={colors.textTertiary}
          accessibilityLabel="Cerca tessera" style={[s.input, panel, text]} testID="wallet-search" />
        {loading ? <ActivityIndicator accessibilityLabel="Caricamento tessere" color={colors.accent} /> : null}
        {!loading && !cards.length && !error ? <View style={[s.panel, panel]} testID="wallet-empty"><Ionicons name="wallet-outline" size={38} color={colors.textSecondary} />
          <Text style={[s.heading, text]}>La prossima tessera, qui.</Text><Text style={[s.body, secondary]}>Aggiungi il codice dalla foto oppure inseriscilo manualmente. Nessuna carta di esempio viene aggiunta al tuo account.</Text></View> : null}
        {!loading && cards.length > 0 && !visible.length ? <Text style={[s.body, secondary]}>Nessuna tessera corrisponde alla ricerca.</Text> : null}
        {!query && recentCards.length > 1 ? <View style={s.quick}>
          <View style={s.row}><Text style={[s.fieldLabel, text]}>Usate di recente</Text>
          {button('Cancella recenti', resetRecent, loading || busy, false, 'wallet-clear-recents')}</View>
          <View style={s.row}>{recentCards.map(card => <Pressable key={card.id} onPress={() => showCode(card, true)}
            accessibilityRole="button" accessibilityLabel={`Mostra subito ${card.name}`}
            testID={`wallet-recent-${card.id}`} style={({ pressed }) => [s.chip, panel, { opacity: pressed ? 0.7 : 1 }]}>
            <Text style={[s.body, text]} numberOfLines={1}>{card.name}</Text>
          </Pressable>)}</View>
          <Text style={[s.small, secondary]}>ORA ricorda solo l’ordine delle tessere aperte su questo dispositivo, mai i codici.</Text>
        </View> : null}
        {visible.length > 0 ? <Text style={[s.fieldLabel, secondary]}>{query ? 'Risultati' : 'Le tue tessere'}</Text> : null}
        <View style={s.grid}>{visible.map(card => <View key={card.id} style={[s.card, panel]}>
          <Pressable disabled={loading || busy} onPress={() => showCode(card, true)} accessibilityRole="button"
            accessibilityLabel={`Mostra ${card.name} alla cassa`} testID={`wallet-show-${card.id}`}
            style={({ pressed }) => [s.cardMain, { opacity: pressed ? 0.65 : 1 }]}>
            <Ionicons name={card.favorite ? 'star' : 'barcode-outline'} size={24} color={colors.accent} />
            <Text style={[s.heading, text]} numberOfLines={2}>{card.name}</Text>
            <Text style={[s.small, secondary]}>{label(card.format)} · Tocca per mostrare subito</Text>
          </Pressable>
          <View style={[s.cardActions, { borderTopColor: colors.border }]}>
            <Pressable disabled={loading || busy} onPress={() => { void toggleFavorite(card); }}
              accessibilityRole="button" accessibilityLabel={card.favorite ? `Rimuovi ${card.name} dalle preferite` : `Aggiungi ${card.name} alle preferite`}
              testID={`wallet-favorite-${card.id}`} style={s.manageBtn}>
              <Ionicons name={card.favorite ? 'star' : 'star-outline'} size={18} color={colors.accent} />
              <Text style={[s.small, secondary]}>{card.favorite ? 'Preferita' : 'Preferiti'}</Text>
            </Pressable>
            <Pressable disabled={loading || busy} onPress={() => { setSelected(card); setNotice(''); setError(''); }}
              accessibilityRole="button" accessibilityLabel={`Gestisci ${card.name}`} testID={`wallet-manage-${card.id}`}
              style={s.manageBtn}>
              <Ionicons name="settings-outline" size={16} color={colors.textSecondary}/>
              <Text style={[s.small, secondary]}>Gestisci</Text>
            </Pressable>
          </View>
        </View>)}</View>
      </>}
    </ScrollView>
    <Modal visible={checkout && !!selected} animationType="fade" onRequestClose={closeCode}>
      <SafeAreaView style={s.checkout}>
        <View style={s.checkoutTop}>
          <Text style={{ color: '#444', fontSize: 14, fontWeight: '600' }}>Modalità cassa</Text>
          <Pressable onPress={closeCode} accessibilityRole="button" accessibilityLabel="Chiudi e torna alle tessere"
            testID="wallet-close-top" style={s.checkoutTopClose}>
            <Ionicons name="close" size={19} color="#111" />
            <Text style={{ fontSize: 15, fontWeight: '600', color: '#111' }}>Chiudi</Text>
          </Pressable>
        </View>
        <ScrollView contentContainerStyle={s.checkoutContent} keyboardShouldPersistTaps="always">
          <Text style={s.checkoutTitle} numberOfLines={2}>{selected?.name}</Text>
          <Text style={s.checkoutHint}>Mostra al lettore. Se possibile, aumenta la luminosità del telefono.</Text>
          {selected ? <View style={[s.imageFrame, { width: Math.min(width - 36, 1000),
            height: rotated && selected.format !== 'QR_CODE' ? Math.min(height * 0.60, 540) : selected.format === 'QR_CODE' ? Math.min(width - 36, 440) : Math.min(height * 0.38, 310) }]}
            testID="wallet-code-frame">
            <Image source={{ uri: selected.image }} resizeMode="contain"
              style={rotated && selected.format !== 'QR_CODE'
                ? { width: Math.min(height * 0.54, 500), height: Math.min(width - 52, 210), transform: [{ rotate: '90deg' }] }
                : { width: '100%', height: '100%' }}
              accessibilityLabel="Codice da mostrare alla cassa" />
          </View> : null}
          <Text selectable style={s.checkoutCode}>{selected?.code}</Text>
          {selected && selected.format !== 'QR_CODE' ? <Pressable onPress={() => setRotated(value => !value)}
            accessibilityRole="button" style={s.checkoutSecondary} testID="wallet-rotate">
            <Text style={s.checkoutSecondaryLabel}>{rotated ? 'Mostra orizzontale' : 'Ruota codice di 90°'}</Text>
          </Pressable> : null}
          <View style={[s.row, { justifyContent: 'center' }]}>
            <Pressable onPress={() => { void copyCode(); }} accessibilityRole="button" style={s.checkoutSecondary} testID="wallet-copy">
              <Text style={s.checkoutSecondaryLabel}>{copied ? 'Numero copiato' : 'Copia numero'}</Text>
            </Pressable>
            {sorted.length > 1 ? <>
              <Pressable onPress={() => stepCard(-1)} accessibilityRole="button" style={s.checkoutSecondary} testID="wallet-prev">
                <Text style={s.checkoutSecondaryLabel}>‹ Precedente</Text>
              </Pressable>
              <Pressable onPress={() => stepCard(1)} accessibilityRole="button" style={s.checkoutSecondary} testID="wallet-next">
                <Text style={s.checkoutSecondaryLabel}>Successiva ›</Text>
              </Pressable>
            </> : null}
          </View>
          {copyError ? <Text style={s.checkoutHint} accessibilityRole="alert">{copyError}</Text> : null}
          <Text style={s.checkoutHint}>Se il lettore non riconosce il codice, mostra il numero o usa la tessera originale.</Text>
          <Pressable onPress={closeCode} accessibilityRole="button" style={s.closeCheckout} testID="wallet-close-checkout">
            <Text style={{ color: '#fff', fontSize: 17, textAlign: 'center' }}>Chiudi codice</Text>
          </Pressable>
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
  card: { flexGrow: 1, flexBasis: 250, minHeight: 150, borderRadius: tokens.radius.lg, borderWidth: 1, padding: 16, gap: 8 },
  cardMain: { flex: 1, minHeight: 115, justifyContent: 'center', gap: 9 },
  cardActions: { borderTopWidth: 1, flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', gap: 8 },
  manageBtn: { minHeight: 44, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 7 },
  quick: { gap: 10, marginVertical: 8 },
  codeBox: { backgroundColor: '#fff', borderRadius: 12, padding: 16, gap: 12 }, barcode: { width: '100%', height: 200 },
  codeText: { color: '#000', textAlign: 'center', fontSize: 18 }, checkout: { flex: 1, backgroundColor: '#fff' },
  checkoutContent: { flexGrow: 1, justifyContent: 'center', alignItems: 'center', padding: 20, gap: 24 },
  checkoutTop: { paddingHorizontal: 20, paddingVertical: 8, flexDirection: 'row',
    alignItems: 'center', justifyContent: 'space-between', minHeight: 52 },
  checkoutTopClose: { minWidth: 88, minHeight: 44, paddingHorizontal: 12, flexDirection: 'row',
    gap: 7, alignItems: 'center', justifyContent: 'center', borderRadius: 12,
    borderColor: '#ccc', borderWidth: 1, backgroundColor: '#f8f8f8' },
  checkoutTitle: { fontSize: 28, fontWeight: '700', color: '#000', textAlign: 'center' },
  imageFrame: { alignItems: 'center', justifyContent: 'center', overflow: 'visible' },
  checkoutSecondary: { paddingVertical: 12, paddingHorizontal: 15, minHeight: 48, borderWidth: 1,
    borderColor: '#555', borderRadius: 11, alignItems: 'center', justifyContent: 'center' },
  checkoutSecondaryLabel: { fontSize: 15, fontWeight: '600', color: '#111' },
  checkoutHint: { color: '#333', fontSize: 15, textAlign: 'center', maxWidth: 500 }, checkoutCode: { color: '#000', fontSize: 22, textAlign: 'center' },
  closeCheckout: { padding: 16, minHeight: 50, borderRadius: 14, backgroundColor: '#111', alignSelf: 'center' },
});
