import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { Image } from 'expo-image';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import * as Crypto from 'expo-crypto';
import { useRouter } from 'expo-router';
import { useAuth } from '@/src/contexts/AuthContext';
import { useTheme } from '@/src/theme/ThemeProvider';
import { useAmbientInset } from '@/src/shell';
import { tokens } from '@/src/theme/tokens';
import { wardrobeClient, CATEGORIES, FORMALITIES, OCCASIONS,
  type Garment, type GarmentInput, type Category, type Formality,
  type GarmentStatus, type Occasion, type OutfitResponse } from './client';
import { pickGarmentPhoto } from './pickPhoto';

const errorText = (error: unknown) => error instanceof Error ? error.message : 'Operazione non riuscita.';
const label = (category: string) => CATEGORIES.find(c => c.value === category)?.label || category;
const styleLabel = (value: string) => FORMALITIES.find(f => f.value === value)?.label || value;

export default function WardrobeRoute() {
  const { user } = useAuth();
  return user ? <WardrobeScreen key={user.user_id} /> : null;
}

function WardrobeScreen() {
  const { colors } = useTheme();
  const router = useRouter();
  const ambient = useAmbientInset();
  const [items, setItems] = useState<Garment[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [draft, setDraft] = useState<GarmentInput | null>(null);
  const [newPhoto, setNewPhoto] = useState<Blob | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Garment | null>(null);
  const [occasion, setOccasion] = useState<Occasion>('casual_evening');
  const [result, setResult] = useState<OutfitResponse | null>(null);

  const load = useCallback(async () => {
    const token = await wardrobeClient.token();
    if (!token) throw new Error('Accedi nuovamente a ORA.');
    const data = await wardrobeClient.list(token);
    setItems(data.items);
  }, []);
  useEffect(() => {
    let live = true;
    setLoading(true);
    wardrobeClient.token().then(token => {
      if (!token) throw new Error('Accedi nuovamente a ORA.');
      return wardrobeClient.list(token);
    }).then(data => { if (live) setItems(data.items); })
      .catch(e => { if (live) setError(errorText(e)); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, []);

  const create = () => {
    setDraft({ id: Crypto.randomUUID().replace(/-/g, ''), revision: 0, name: '',
      category: 'top', color: '', formality: 'casual', seasons: [], status: 'available' });
    setNewPhoto(null); setError(''); setNotice('');
  };
  const edit = (item: Garment) => {
    const { id, revision, name, category, color, formality, seasons, status } = item;
    setDraft({ id, revision, name, category, color, formality, seasons, status });
    setNewPhoto(null); setError(''); setNotice('');
  };
  const patch = (values: Partial<GarmentInput>) => setDraft(previous => previous ? { ...previous, ...values } : null);
  const save = async () => {
    if (!draft || busy) return;
    if (!draft.name.trim() || !draft.color.trim()) {
      setError('Inserisci nome e colore del capo.'); return;
    }
    setBusy(true); setError(''); setNotice('');
    try {
      const token = await wardrobeClient.token();
      if (!token) throw new Error('Accedi nuovamente a ORA.');
      const { item: saved } = await wardrobeClient.save(token, draft);
      let photoProblem = '';
      if (newPhoto) {
        try { await wardrobeClient.photo(token, saved, newPhoto); }
        catch (e) { photoProblem = errorText(e); }
      }
      await load();
      setResult(null); setDraft(null); setNewPhoto(null);
      setNotice(photoProblem ? `Capo salvato, ma la foto non è stata caricata: ${photoProblem}` : 'Capo salvato nel tuo guardaroba.');
    } catch (e) { setError(errorText(e)); }
    finally { setBusy(false); }
  };
  const choosePhoto = async () => {
    try {
      const photo = await pickGarmentPhoto();
      if (photo) { setNewPhoto(photo); setError(''); }
    } catch (e) { setError(errorText(e)); }
  };
  const remove = async () => {
    if (!deleteTarget || busy) return;
    setBusy(true); setError('');
    try {
      const token = await wardrobeClient.token();
      if (!token) throw new Error('Accedi nuovamente a ORA.');
      await wardrobeClient.remove(token, deleteTarget);
      await load();
      setDeleteTarget(null); setResult(null); setNotice('Capo eliminato dal guardaroba.');
    } catch (e) { setError(errorText(e)); }
    finally { setBusy(false); }
  };
  const suggest = async () => {
    if (busy) return;
    setBusy(true); setError(''); setNotice(''); setResult(null);
    try {
      const token = await wardrobeClient.token();
      if (!token) throw new Error('Accedi nuovamente a ORA.');
      setResult(await wardrobeClient.outfits(token, occasion));
    } catch (e) { setError(errorText(e)); }
    finally { setBusy(false); }
  };

  const card = { backgroundColor: colors.surface, borderColor: colors.border };
  const foreground = { color: colors.textPrimary };
  const muted = { color: colors.textSecondary };
  const selection = (active: boolean) => ({
    borderColor: active ? colors.accent : colors.border,
    backgroundColor: active ? colors.accentMuted : colors.surface,
  });
  const chip = (text: string, active: boolean, onPress: () => void, key: string) => (
    <Pressable key={key} onPress={onPress} accessibilityRole="button" accessibilityState={{ selected: active }}
      style={[s.chip, selection(active)]}>
      <Text style={[s.chipText, { color: active ? colors.accent : colors.textPrimary }]}>{text}</Text>
    </Pressable>
  );
  const action = (text: string, onPress: () => void, primary = false, disabled = false) => (
    <Pressable accessibilityRole="button" onPress={onPress} disabled={disabled}
      style={[s.action, { backgroundColor: primary ? colors.accent : colors.surface,
        borderColor: primary ? colors.accent : colors.border, opacity: disabled ? .5 : 1 }]}>
      <Text style={[s.actionText, { color: primary ? colors.onAccent : colors.textPrimary }]}>{text}</Text>
    </Pressable>
  );

  return (
    <SafeAreaView testID="wardrobe-screen" style={{ flex: 1, backgroundColor: colors.backgroundPrimary }}>
      <ScrollView contentContainerStyle={[s.page, { paddingBottom: ambient.paddingBottom + 44 }]}>
        <Pressable onPress={() => router.push('/vita' as any)} accessibilityRole="button" style={s.back}>
          <Ionicons name="arrow-back" color={colors.accent} size={19} />
          <Text style={{ color: colors.accent }}>VITA</Text>
        </Pressable>
        <Text style={[s.hero, foreground]}>Il tuo guardaroba</Text>
        <Text style={[s.subhead, muted]}>I vestiti che possiedi, organizzati per trovare cosa indossare.</Text>
        <View style={[s.card, card]}>
          <Text style={[s.heading, foreground]}>I tuoi capi · {items.length}/75</Text>
          <Text style={[s.note, muted]}>Per questa prima versione indica categoria, colore e stile; le foto sono private e ottimizzate.</Text>
          {!draft ? action('Aggiungi un capo', create, true, busy) : null}
          {loading ? <ActivityIndicator color={colors.accent} /> : null}
          {!loading && !items.length ? <Text style={[s.note, muted]}>Ancora nessun capo. Comincia dai vestiti che usi più spesso.</Text> : null}
          <View style={s.grid}>
            {items.map(item => (
              <View key={item.id} style={[s.item, { borderColor: colors.border }]}>
                {item.photo ? <Image source={{ uri: item.photo }} style={s.photo} contentFit="cover" /> :
                  <View style={[s.photo, s.placeholder, { backgroundColor: colors.backgroundSecondary }]}>
                    <Ionicons name="shirt-outline" size={32} color={colors.textSecondary} />
                  </View>}
                <Text numberOfLines={2} style={[s.itemName, foreground]}>{item.name}</Text>
                <Text style={[s.detail, muted]}>{label(item.category)} · {item.color} · {styleLabel(item.formality)}</Text>
                {item.status !== 'available' ? <Text style={[s.detail, { color: colors.error }]}>
                  {item.status === 'laundry' ? 'Da lavare' : 'Non disponibile'}
                </Text> : null}
                <View style={s.inline}>
                  {action('Modifica', () => edit(item), false, busy)}
                  {action('Elimina', () => setDeleteTarget(item), false, busy)}
                </View>
                {deleteTarget?.id === item.id ? <View testID="wardrobe-delete-confirm" style={{ gap: 8 }}>
                  <Text style={[s.note, foreground]}>Eliminare definitivamente anche la foto?</Text>
                  <View style={s.inline}>
                    {action('Annulla', () => setDeleteTarget(null), false, busy)}
                    {action('Conferma eliminazione', () => { void remove(); }, true, busy)}
                  </View>
                </View> : null}
              </View>
            ))}
          </View>
        </View>

        {draft ? <View style={[s.card, card]} testID="wardrobe-editor">
          <Text style={[s.heading, foreground]}>{draft.revision ? 'Modifica il capo' : 'Nuovo capo'}</Text>
          <Text style={[s.fieldTitle, muted]}>Nome del capo</Text>
          <TextInput value={draft.name} maxLength={80} onChangeText={name => patch({ name })}
            placeholder="Es. Camicia azzurra" placeholderTextColor={colors.textSecondary}
            style={[s.input, foreground, { borderColor: colors.border }]} />
          <Text style={[s.fieldTitle, muted]}>Categoria</Text>
          <View style={s.choices}>{CATEGORIES.map(o => chip(o.label, draft.category === o.value,
            () => patch({ category: o.value as Category }), o.value))}</View>
          <Text style={[s.fieldTitle, muted]}>Colore prevalente</Text>
          <TextInput value={draft.color} maxLength={32} onChangeText={color => patch({ color })}
            placeholder="Es. Blu, bianco, beige" placeholderTextColor={colors.textSecondary}
            style={[s.input, foreground, { borderColor: colors.border }]} />
          <Text style={[s.fieldTitle, muted]}>Stile</Text>
          <View style={s.choices}>{FORMALITIES.map(o => chip(o.label, draft.formality === o.value,
            () => patch({ formality: o.value as Formality }), o.value))}</View>
          <Text style={[s.fieldTitle, muted]}>Disponibilità</Text>
          <View style={s.choices}>
            {chip('Disponibile', draft.status === 'available', () => patch({ status: 'available' as GarmentStatus }), 'available')}
            {chip('Da lavare', draft.status === 'laundry', () => patch({ status: 'laundry' as GarmentStatus }), 'laundry')}
            {chip('Non disponibile', draft.status === 'unavailable', () => patch({ status: 'unavailable' as GarmentStatus }), 'unavailable')}
          </View>
          {action(newPhoto ? 'Foto selezionata · Cambia' : 'Scegli foto (facoltativa)', () => { void choosePhoto(); }, false, busy)}
          <View style={s.inline}>
            {action('Annulla', () => { setDraft(null); setNewPhoto(null); setError(''); }, false, busy)}
            {action(busy ? 'Salvataggio…' : 'Salva capo', () => { void save(); }, true, busy)}
          </View>
        </View> : null}

        <View style={[s.card, card]}>
          <Text style={[s.heading, foreground]}>Scegli un look</Text>
          <Text style={[s.note, muted]}>Indica l'occasione: uso soltanto capi realmente presenti e disponibili.</Text>
          <View style={s.choices}>{OCCASIONS.map(o => chip(o.label, occasion === o.value,
            () => { setOccasion(o.value); setResult(null); }, o.value))}</View>
          {action(busy ? 'Elaborazione…' : 'Proponi gli abbinamenti', () => { void suggest(); }, true, busy)}
          {result ? <View testID="wardrobe-suggestions" style={{ gap: 12 }}>
            {result.missing.length ? <Text style={[s.note, muted]}>
              Mancano capi adatti in queste categorie: {result.missing.map(label).join(', ')}. Non invento ciò che non hai caricato.
            </Text> : result.outfits.map((look, n) => (
              <View key={n} style={[s.look, { borderColor: colors.border }]}>
                <Text style={[s.itemName, foreground]}>Look {n + 1}</Text>
                {look.item_ids.map(id => {
                  const item = items.find(i => i.id === id);
                  return item ? <View key={id} style={s.lookLine}>
                    {item.photo ? <Image source={{ uri: item.photo }} style={s.tinyPhoto} /> : null}
                    <Text style={[s.note, foreground]}>{label(item.category)}: {item.name} ({item.color})</Text>
                  </View> : null;
                })}
                <Text style={[s.note, muted]}>{look.why}</Text>
              </View>
            ))}
            <Text style={[s.note, muted]}>{result.message}</Text>
          </View> : null}
        </View>

        {error ? <Text testID="wardrobe-error" style={{ color: colors.error }}>{error}</Text> : null}
        {notice ? <Text testID="wardrobe-notice" style={{ color: colors.textSecondary }}>{notice}</Text> : null}
        <Text style={[s.note, muted]}>Pilot: il motore attuale usa regole di categoria, formalità e colore. Il riconoscimento fotografico AI e lo stylist personale arriveranno soltanto dopo verifica della qualità.</Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  page: { width: '100%', maxWidth: 1000, alignSelf: 'center', padding: tokens.spacing.lg, gap: 18 },
  back: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 },
  hero: { fontSize: 30, fontWeight: '700' },
  subhead: { fontSize: 15, lineHeight: 22 },
  card: { borderRadius: tokens.radius.lg, borderWidth: 1, padding: tokens.spacing.lg, gap: 14 },
  heading: { fontSize: 20, fontWeight: '700' },
  note: { fontSize: 14, lineHeight: 21 },
  fieldTitle: { fontWeight: '600', fontSize: 14 },
  input: { height: 44, borderWidth: 1, borderRadius: 10, paddingHorizontal: 12, fontSize: 15 },
  choices: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { borderWidth: 1, borderRadius: 20, paddingVertical: 9, paddingHorizontal: 13 },
  chipText: { fontSize: 13, fontWeight: '600' },
  action: { borderWidth: 1, borderRadius: 11, paddingHorizontal: 13, paddingVertical: 11, alignItems: 'center', justifyContent: 'center', minHeight: 41 },
  actionText: { fontSize: 14, fontWeight: '600' },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 12 },
  item: { width: 214, maxWidth: '100%', borderWidth: 1, borderRadius: 14, padding: 10, gap: 7 },
  photo: { width: '100%', height: 145, borderRadius: 10 },
  placeholder: { alignItems: 'center', justifyContent: 'center' },
  itemName: { fontSize: 16, fontWeight: '700' },
  detail: { fontSize: 12, lineHeight: 17 },
  inline: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  look: { borderWidth: 1, borderRadius: 12, padding: 12, gap: 8 },
  lookLine: { flexDirection: 'row', gap: 8, alignItems: 'center' },
  tinyPhoto: { width: 40, height: 40, borderRadius: 6 },
});
