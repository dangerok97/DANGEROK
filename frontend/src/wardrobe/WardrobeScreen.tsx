import React, { useCallback, useEffect, useRef, useState } from 'react';
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
  type GarmentStatus, type Occasion, type OutfitResponse, type GarmentAnalysis } from './client';
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
  const [analyzing, setAnalyzing] = useState(false);
  const [recognition, setRecognition] = useState<GarmentAnalysis | null>(null);
  const [analysisNote, setAnalysisNote] = useState('');
  // Discard AI results after switching draft, photo, or manual field edits.
  const photoEpoch = useRef(0);
  const [deleteTarget, setDeleteTarget] = useState<Garment | null>(null);
  const [occasion, setOccasion] = useState<Occasion>('casual_evening');
  const [styleNote, setStyleNote] = useState('');
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
    photoEpoch.current += 1; setRecognition(null); setAnalysisNote('');
    setDraft({ id: Crypto.randomUUID().replace(/-/g, ''), revision: 0, name: '',
      category: 'top', color: '', formality: 'casual', seasons: [], status: 'available' });
    setNewPhoto(null); setError(''); setNotice('');
  };
  const edit = (item: Garment) => {
    photoEpoch.current += 1; setRecognition(null); setAnalysisNote('');
    const { id, revision, name, category, color, formality, seasons, status } = item;
    setDraft({ id, revision, name, category, color, formality, seasons, status });
    setNewPhoto(null); setError(''); setNotice('');
  };
  const patch = (values: Partial<GarmentInput>) => {
    photoEpoch.current += 1;
    setRecognition(null);
    setDraft(previous => previous ? { ...previous, ...values } : null);
  };
  const save = async () => {
    if (!draft || busy || analyzing) return;
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
      photoEpoch.current += 1;
      setResult(null); setDraft(null); setNewPhoto(null);
      setRecognition(null); setAnalysisNote('');
      setNotice(photoProblem ? `Capo salvato, ma la foto non è stata caricata: ${photoProblem}` : 'Capo salvato nel tuo guardaroba.');
    } catch (e) { setError(errorText(e)); }
    finally { setBusy(false); }
  };
  const choosePhoto = async () => {
    if (!draft || busy || analyzing) return;
    try {
      const photo = await pickGarmentPhoto();
      if (photo) {
        photoEpoch.current += 1;
        setNewPhoto(photo); setRecognition(null); setAnalysisNote('');
        setError('');
      }
    } catch (e) { setError(errorText(e)); }
  };
  const analyze = async () => {
    if (!draft || !newPhoto || busy || analyzing) return;
    const currentEpoch = photoEpoch.current;
    setAnalyzing(true); setError(''); setAnalysisNote('');
    try {
      const token = await wardrobeClient.token();
      if (!token) throw new Error('Accedi nuovamente a ORA.');
      const suggestion = await wardrobeClient.analyze(token, newPhoto);
      if (photoEpoch.current !== currentEpoch) return;
      setRecognition(suggestion);
      setAnalysisNote(suggestion.message);
      if (suggestion.recognized && suggestion.suggestion) {
        setDraft(previous => previous ? { ...previous, ...suggestion.suggestion } : null);
      }
    } catch (e) {
      if (photoEpoch.current === currentEpoch) {
        setRecognition(null);
        setAnalysisNote(errorText(e) + ' Puoi comunque compilare i campi a mano.');
      }
    } finally { setAnalyzing(false); }
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
      setResult(await wardrobeClient.outfits(token, occasion, styleNote));
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
          <Text style={[s.note, muted]}>Le foto salvate sono protette e ottimizzate. L'analisi AI è facoltativa: la attivi solo tu.</Text>
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
          {action(newPhoto ? 'Foto selezionata · Cambia foto' : 'Scegli una foto del capo', () => { void choosePhoto(); }, false, busy || analyzing)}
          <Text style={[s.note, muted]}>Se vuoi, premi «Riconosci con AI»: una copia ridotta della foto sarà inviata al provider AI configurato per proporti i campi. Non viene salvato nulla senza il tuo «Salva capo».</Text>
          {newPhoto ? action(analyzing ? 'Riconoscimento in corso…' : 'Riconosci con AI', () => { void analyze(); }, true, busy || analyzing) : null}
          {analyzing ? <ActivityIndicator testID="wardrobe-analyzing" color={colors.accent} /> : null}
          {analysisNote ? <Text testID="wardrobe-analysis-note" style={[s.note, recognition?.recognized ? { color: colors.accent } : muted]}>
            {analysisNote}{recognition?.recognized ? ' Controlla nome, colore, categoria e stile.' : ''}
          </Text> : null}
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
          <View style={s.inline}>
            {action('Annulla', () => { photoEpoch.current += 1; setDraft(null); setNewPhoto(null); setRecognition(null); setAnalysisNote(''); setError(''); }, false, busy || analyzing)}
            {action(busy ? 'Salvataggio…' : 'Salva capo', () => { void save(); }, true, busy || analyzing)}
          </View>
        </View> : null}

        <View style={[s.card, card]}>
          <Text style={[s.heading, foreground]}>Scegli un look</Text>
          <Text style={[s.note, muted]}>ORA valuta gli abbinamenti con l'AI, utilizzando esclusivamente i capi realmente presenti e disponibili. L'analisi invia al modello soltanto le descrizioni dei vestiti, mai le fotografie.</Text>
          <View style={s.choices}>{OCCASIONS.map(o => chip(o.label, occasion === o.value,
            () => { setOccasion(o.value); setResult(null); }, o.value))}</View>
          <TextInput testID="wardrobe-style-note" value={styleNote} maxLength={200}
            onChangeText={text => { setStyleNote(text); setResult(null); }}
            placeholder="Facoltativo: locale elegante ma non troppo formale, stile minimal..."
            placeholderTextColor={colors.textSecondary}
            style={[s.input, foreground, { borderColor: colors.border }]} />
          {action(busy ? 'ORA sta valutando i look…' : 'Proponi gli abbinamenti con AI', () => { void suggest(); }, true, busy)}
          {result ? <Text testID="wardrobe-ai-status" style={[s.note, result.engine === 'ai-stylist-v1'
            ? { color: colors.accent } : muted]}>
            {result.engine === 'ai-stylist-v1' ? 'Stylist AI · Valutazione delle schede dei tuoi capi'
              : result.ai_status === 'unavailable' ? 'Stylist AI non disponibile · Consigli preliminari'
              : result.ai_status === 'rate_limited' ? 'Limite AI raggiunto · Consigli preliminari'
              : 'Suggerimenti preliminari dai tuoi capi'}
          </Text> : null}
          {result ? <View testID="wardrobe-suggestions" style={{ gap: 12 }}>
            {result.missing.length ? <Text style={[s.note, muted]}>
              Mancano capi adatti in queste categorie: {result.missing.map(label).join(', ')}. Non invento ciò che non hai caricato.
            </Text> : result.outfits.map((look, n) => (
              <View key={n} style={[s.look, { borderColor: colors.border }]}>
                <Text style={[s.itemName, foreground]}>Look {n + 1} · {look.title}</Text>
                <View style={s.outfitItems}>
                  {look.item_ids.map(id => {
                    const item = items.find(i => i.id === id);
                    return item ? <View key={id}
                      style={[s.outfitItem, { borderColor: colors.border, backgroundColor: colors.backgroundSecondary }]}>
                      {item.photo ? <Image source={{ uri: item.photo }} style={s.outfitPhoto} contentFit="contain" /> :
                        <View style={[s.outfitPhoto, s.placeholder, { backgroundColor: colors.surface }]}>
                          <Ionicons name="shirt-outline" size={27} color={colors.textSecondary} />
                        </View>}
                      <Text style={[s.outfitCategory, muted]}>{label(item.category)}</Text>
                      <Text numberOfLines={3} style={[s.outfitName, foreground]}>{item.name}</Text>
                      <Text style={[s.outfitColor, muted]}>{item.color}</Text>
                    </View> : null;
                  })}
                </View>
                <Text style={[s.note, foreground]}>{look.why}</Text>
                {look.cautions?.length ? <View testID="wardrobe-cautions" style={s.cautions}>
                  <Text style={[s.fieldTitle, foreground]}>Da considerare</Text>
                  {look.cautions.map((warning, i) =>
                    <Text key={i} style={[s.note, muted]}>• {warning}</Text>)}
                </View> : null}
                {look.styling_tip ? <Text style={[s.note, foreground]}>Consiglio sul capo: {look.styling_tip}</Text> : null}
              </View>
            ))}
            <Text style={[s.note, muted]}>{result.message}</Text>
          </View> : null}
        </View>

        {error ? <Text testID="wardrobe-error" style={{ color: colors.error }}>{error}</Text> : null}
        {notice ? <Text testID="wardrobe-notice" style={{ color: colors.textSecondary }}>{notice}</Text> : null}
        <Text style={[s.note, muted]}>Lo stylist AI propone abbinamenti tra i tuoi capi verificati e spiega i motivi. In caso di indisponibilità dell'AI, ORA indica chiaramente quando usa regole preliminari. I consigli non garantiscono vestibilità o conformità al dress code.</Text>
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
  outfitItems: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  outfitItem: { width: 148, maxWidth: '100%', borderWidth: 1, borderRadius: 12,
    padding: 9, gap: 5, overflow: 'hidden' },
  outfitPhoto: { width: '100%', height: 128, borderRadius: 9 },
  outfitCategory: { fontSize: 12, lineHeight: 16 },
  outfitName: { fontWeight: '600', fontSize: 14, lineHeight: 18, minHeight: 18 },
  outfitColor: { fontSize: 12 },
  cautions: { gap: 5, paddingTop: 7 },

});
