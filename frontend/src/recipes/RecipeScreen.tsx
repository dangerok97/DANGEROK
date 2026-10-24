import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Linking, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '@/src/contexts/AuthContext';
import { useTheme } from '@/src/theme/ThemeProvider';
import { useAmbientInset } from '@/src/shell';
import { tokens } from '@/src/theme/tokens';
import { recipesClient, toRecipeWrite, type Recipe, type RecipePreview, type RecipeWrite } from './client';

const message = (error: unknown) => error instanceof Error ? error.message : 'Operazione non riuscita.';
const splitLines = (source: string) => source.split('\n').map(s => s.trim()).filter(Boolean);
const stateLabel = (recipe: Recipe) => !recipe.ingredients.length || !recipe.steps.length
  ? 'Da completare' : recipe.status === 'cooked' ? 'Già cucinata' : 'Da provare';

export default function RecipeRoute() {
  const { user } = useAuth();
  return user ? <RecipeScreen key={user.user_id} /> : null;
}

function RecipeScreen() {
  const router = useRouter();
  const ambient = useAmbientInset();
  const { colors } = useTheme();
  const params = useLocalSearchParams<{ source?: string; url?: string }>();
  const incoming = typeof params.source === 'string' ? params.source
    : typeof params.url === 'string' ? params.url : '';
  const [items, setItems] = useState<Recipe[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [source, setSource] = useState(incoming.slice(0, 12000));
  const [search, setSearch] = useState('');
  const [previewResult, setPreviewResult] = useState<RecipePreview | null>(null);
  const [draft, setDraft] = useState<RecipeWrite | null>(null);
  const [editId, setEditId] = useState<string | null>(null);
  const [ingredientsText, setIngredientsText] = useState('');
  const [stepsText, setStepsText] = useState('');
  const [tagsText, setTagsText] = useState('');
  const [servingsText, setServingsText] = useState('');
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const scroll = useRef<ScrollView>(null);

  const load = useCallback(async () => {
    const token = await recipesClient.token();
    if (!token) throw new Error('Accedi nuovamente a ORA.');
    const data = await recipesClient.list(token);
    setItems(data.items);
  }, []);

  useEffect(() => {
    let live = true;
    recipesClient.token().then(token => {
      if (!token) throw new Error('Accedi nuovamente a ORA.');
      return recipesClient.list(token);
    }).then(data => { if (live) setItems(data.items); })
      .catch(err => { if (live) setError(message(err)); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, []);

  const cancel = () => {
    setDraft(null); setPreviewResult(null); setEditId(null); setDeleteTarget(null);
    setIngredientsText(''); setStepsText(''); setTagsText(''); setServingsText('');
    setError('');
  };
  const openDraft = (value: RecipeWrite) => {
    setDraft(value);
    setIngredientsText(value.ingredients.join('\n'));
    setStepsText(value.steps.join('\n'));
    setTagsText(value.tags.join(', '));
    setServingsText(value.servings ? String(value.servings) : '');
    scroll.current?.scrollTo({ y: 0, animated: true });
  };
  const startPreview = async () => {
    if (busy || !source.trim()) { setError('Incolla il testo oppure un link HTTPS.'); return; }
    setBusy(true); setError(''); setNotice('');
    try {
      const token = await recipesClient.token();
      if (!token) throw new Error('Accedi nuovamente a ORA.');
      const result = await recipesClient.preview(token, source.trim());
      setPreviewResult(result);
      setEditId(null);
      openDraft({ ...result.draft, revision: 0 });
    } catch (err) { setError(message(err)); }
    finally { setBusy(false); }
  };
  const edit = (item: Recipe) => {
    setError(''); setNotice(''); setPreviewResult(null); setDeleteTarget(null);
    setEditId(item.id);
    openDraft(toRecipeWrite(item));
  };
  const buildWrite = (): RecipeWrite | null => {
    if (!draft) return null;
    const portions = servingsText.trim() ? Number(servingsText.trim()) : null;
    if (portions !== null && (!Number.isInteger(portions) || portions < 1 || portions > 99)) {
      setError('Le porzioni devono essere un numero intero da 1 a 99.'); return null;
    }
    const value = { ...draft, title: draft.title.trim(), ingredients: splitLines(ingredientsText),
      steps: splitLines(stepsText), tags: tagsText.split(',').map(s => s.trim()).filter(Boolean),
      servings: portions };
    if (!value.title || !value.source_url && !value.source_text) {
      setError('Indica un titolo e conserva il link o testo originale.'); return null;
    }
    return value;
  };
  const save = async () => {
    if (busy) return;
    const value = buildWrite();
    if (!value) return;
    setBusy(true); setError(''); setNotice('');
    try {
      const token = await recipesClient.token();
      if (!token) throw new Error('Accedi nuovamente a ORA.');
      const result = editId
        ? { ...(await recipesClient.update(token, editId, value)), created: false }
        : await recipesClient.create(token, value);
      await load();
      cancel(); setSource('');
      setNotice(editId ? 'Modifiche salvate nel tuo ricettario.'
        : result.created ? 'Ricetta salvata. ORA la ritroverà dopo il prossimo accesso.'
          : 'Questa ricetta era già presente: nessun duplicato creato.');
    } catch (err) { setError(message(err)); }
    finally { setBusy(false); }
  };
  const toggleFavorite = async (item: Recipe) => {
    if (busy) return;
    setBusy(true); setError('');
    try {
      const token = await recipesClient.token();
      if (!token) throw new Error('Accedi nuovamente a ORA.');
      await recipesClient.update(token, item.id, { ...toRecipeWrite(item), favorite: !item.favorite });
      await load();
    } catch (err) { setError(message(err)); }
    finally { setBusy(false); }
  };
  const remove = async (item: Recipe) => {
    if (busy) return;
    if (deleteTarget !== item.id) { setDeleteTarget(item.id); return; }
    setBusy(true); setError('');
    try {
      const token = await recipesClient.token();
      if (!token) throw new Error('Accedi nuovamente a ORA.');
      await recipesClient.remove(token, item);
      await load(); setDeleteTarget(null);
      if (editId === item.id) cancel();
      setNotice('Ricetta eliminata dal ricettario.');
    } catch (err) { setError(message(err)); }
    finally { setBusy(false); }
  };
  const visible = items.filter(item => {
    const haystack = [item.title, ...item.ingredients, ...item.tags].join(' ').toLocaleLowerCase('it');
    return haystack.includes(search.toLocaleLowerCase('it').trim());
  });
  const canSave = !!draft && !busy;

  const inputStyle = [styles.input, { borderColor: colors.border, backgroundColor: colors.surface,
    color: colors.textPrimary }];
  const secondary = { color: colors.textSecondary };
  const primary = { color: colors.textPrimary };
  const action = (label: string, fn: () => void, disabled = false) => (
    <Pressable onPress={fn} disabled={disabled} accessibilityRole="button"
      style={({ pressed }) => [styles.action, { backgroundColor: colors.accent },
        (pressed || disabled) && { opacity: 0.6 }]}>
      <Text style={[styles.buttonText, { color: colors.onAccent }]}>{label}</Text>
    </Pressable>
  );

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.backgroundPrimary }} edges={['top']}>
      <ScrollView ref={scroll} keyboardShouldPersistTaps="handled"
        contentContainerStyle={[styles.page, { paddingBottom: ambient.paddingBottom + 45 }]}>
        <View style={styles.header}>
          <View style={{ flex: 1, gap: 6 }}>
            <Text style={[styles.eyebrow, secondary]}>VITA / CUCINA</Text>
            <Text style={[styles.h1, primary]}>Il mio ricettario</Text>
            <Text style={[styles.lead, secondary]}>Una ricetta salvata diventa qualcosa che puoi ritrovare e cucinare.</Text>
          </View>
          <View style={{ gap: 8, alignItems: 'flex-end' }}>
            <Pressable onPress={() => router.push('/cucina-piano' as any)}
              accessibilityRole="button" accessibilityLabel="Apri piano pasti e lista della spesa"
              style={[styles.smallButton, { borderColor: colors.accent, backgroundColor: colors.accentMuted }]}>
              <Text style={[styles.note, primary]}>Piano e spesa</Text>
            </Pressable>
            <Pressable testID="recipes-back" onPress={() => router.push('/vita' as any)}
              accessibilityRole="button" accessibilityLabel="Torna a Vita"
              style={[styles.smallButton, { borderColor: colors.border }]}>
              <Ionicons name="arrow-back" size={21} color={colors.textPrimary} />
            </Pressable>
          </View>
        </View>
        {error ? <Text testID="recipes-error" style={[styles.alert, { color: colors.error,
          backgroundColor: colors.backgroundSecondary }]}>{error}</Text> : null}
        {notice ? <Text testID="recipes-notice" style={[styles.alert,
          { color: colors.textPrimary, backgroundColor: colors.accentMuted }]}>{notice}</Text> : null}

        <View style={[styles.panel, { borderColor: colors.border, backgroundColor: colors.surface }]}>
          <Text style={[styles.h2, primary]}>Salva una ricetta</Text>
          <Text style={[styles.note, secondary]}>Incolla il testo con le sezioni Ingredienti e Procedimento, oppure un link. Per i link social ORA conserva la fonte, ma non inventa ingredienti non letti.</Text>
          <TextInput testID="recipes-source" style={[inputStyle, styles.sourceInput]} multiline
            placeholder="Link Instagram, TikTok, sito ricette oppure testo completo…"
            placeholderTextColor={colors.textSecondary} maxLength={12000}
            autoCapitalize="none" autoCorrect={false} value={source} onChangeText={setSource} />
          {action(busy && !draft ? 'Analisi…' : 'Leggi il contenuto', () => { void startPreview(); }, busy || !source.trim())}
        </View>

        {draft ? (
          <View testID="recipes-editor" style={[styles.panel,
            { borderColor: colors.border, backgroundColor: colors.surface }]}>
            <View style={styles.header}>
              <Text style={[styles.h2, primary]}>{editId ? 'Modifica ricetta' : 'Controlla prima di salvare'}</Text>
              <Pressable accessibilityRole="button" accessibilityLabel="Annulla modifica"
                onPress={cancel}><Ionicons name="close-circle-outline" size={28} color={colors.textSecondary} /></Pressable>
            </View>
            {previewResult?.warnings.map((warning, index) => (
              <Text key={index} style={[styles.note, { color: colors.error }]}>• {warning}</Text>
            ))}
            <Text style={[styles.fieldLabel, primary]}>Nome ricetta</Text>
            <TextInput testID="recipes-title" style={inputStyle} maxLength={140}
              value={draft.title} onChangeText={value => setDraft({ ...draft, title: value })}
              placeholderTextColor={colors.textSecondary} />
            <Text style={[styles.fieldLabel, primary]}>Ingredienti (uno per riga, quantità non inventate)</Text>
            <TextInput testID="recipes-ingredients" style={[inputStyle, styles.multi]}
              multiline value={ingredientsText} onChangeText={setIngredientsText}
              placeholder="250 g di pasta\n2 zucchine" placeholderTextColor={colors.textSecondary} />
            <Text style={[styles.fieldLabel, primary]}>Procedimento (un passaggio per riga)</Text>
            <TextInput testID="recipes-steps" style={[inputStyle, styles.multi]}
              multiline value={stepsText} onChangeText={setStepsText}
              placeholder="Cuoci la pasta\nSalta le zucchine" placeholderTextColor={colors.textSecondary} />
            <Text style={[styles.fieldLabel, primary]}>Porzioni (facoltativo)</Text>
            <TextInput style={inputStyle} keyboardType="number-pad" value={servingsText}
              onChangeText={setServingsText} placeholder="Es. 2" placeholderTextColor={colors.textSecondary} />
            <Text style={[styles.fieldLabel, primary]}>Etichette (separate da virgola)</Text>
            <TextInput style={inputStyle} value={tagsText} onChangeText={setTagsText}
              placeholder="Primi, cena, veloce" placeholderTextColor={colors.textSecondary} />
            <Pressable accessibilityRole="checkbox" accessibilityState={{ checked: draft.favorite }}
              onPress={() => setDraft({ ...draft, favorite: !draft.favorite })}
              style={styles.inline}>
              <Ionicons name={draft.favorite ? 'star' : 'star-outline'} size={20} color={colors.accent} />
              <Text style={primary}>Tra le preferite</Text>
            </Pressable>
            <Pressable accessibilityRole="checkbox" accessibilityState={{ checked: draft.status === 'cooked' }}
              onPress={() => setDraft({ ...draft, status: draft.status === 'cooked' ? 'to_try' : 'cooked' })}
              style={styles.inline}>
              <Ionicons name={draft.status === 'cooked' ? 'checkmark-circle' : 'ellipse-outline'} size={20} color={colors.accent} />
              <Text style={primary}>L'ho già cucinata</Text>
            </Pressable>
            {action(busy ? 'Salvataggio…' : 'Salva nel ricettario', () => { void save(); }, !canSave)}
            <Text style={[styles.note, secondary]}>Salvataggio solo dopo questa conferma. Ogni ricetta rimane nel tuo account.</Text>
          </View>
        ) : null}

        <View style={styles.sectionHeader}>
          <Text style={[styles.h2, primary]}>Ricette salvate ({items.length})</Text>
          {loading ? <ActivityIndicator color={colors.accent} /> : null}
        </View>
        <TextInput testID="recipes-search" style={inputStyle} value={search} onChangeText={setSearch}
          placeholder="Cerca tra piatti, ingredienti ed etichette"
          placeholderTextColor={colors.textSecondary} />
        {!loading && !items.length ? (
          <View style={[styles.panel, { borderColor: colors.border, backgroundColor: colors.surface }]}>
            <Text style={secondary}>Il ricettario è vuoto. Incolla una ricetta qui sopra per iniziare.</Text>
          </View>
        ) : null}
        {!loading && items.length > 0 && !visible.length ? <Text style={secondary}>Nessuna ricetta trovata.</Text> : null}
        {visible.map(item => (
          <View key={item.id} testID="recipes-item" style={[styles.recipeCard,
            { borderColor: colors.border, backgroundColor: colors.surface }]}>
            <View style={[styles.header, { alignItems: 'flex-start' }]}>
              <Pressable onPress={() => edit(item)} accessibilityRole="button" style={{ flex: 1, gap: 5 }}>
                <Text style={[styles.cardTitle, primary]}>{item.title}</Text>
                <Text style={[styles.note, secondary]}>{stateLabel(item)} · {item.ingredients.length} ingredienti · {item.steps.length} passaggi</Text>
              </Pressable>
              <Pressable accessibilityRole="button"
                accessibilityLabel={item.favorite ? 'Rimuovi dai preferiti' : 'Aggiungi ai preferiti'}
                disabled={busy} onPress={() => { void toggleFavorite(item); }}>
                <Ionicons name={item.favorite ? 'star' : 'star-outline'} size={25} color={colors.accent} />
              </Pressable>
            </View>
            {item.ingredients.length ? <Text style={[styles.note, secondary]}
              numberOfLines={2}>{item.ingredients.join(' · ')}</Text> : null}
            {item.source_url ? (
              <Pressable accessibilityRole="link" onPress={() => { void Linking.openURL(item.source_url); }}>
                <Text style={[styles.link, { color: colors.accent }]}>Apri la fonte originale ↗</Text>
              </Pressable>
            ) : null}
            <View style={styles.actionsRow}>
              <Pressable accessibilityRole="button" onPress={() => edit(item)}
                style={[styles.smallButton, { borderColor: colors.border }]}>
                <Text style={[styles.smallButtonText, primary]}>Apri / modifica</Text>
              </Pressable>
              <Pressable accessibilityRole="button" disabled={busy} onPress={() => { void remove(item); }}
                style={[styles.smallButton, { borderColor: deleteTarget === item.id ? colors.error : colors.border }]}>
                <Text style={[styles.smallButtonText, { color: deleteTarget === item.id ? colors.error : colors.textSecondary }]}>
                  {deleteTarget === item.id ? 'Conferma elimina' : 'Elimina'}
                </Text>
              </Pressable>
            </View>
          </View>
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  page: { width: '100%', maxWidth: 920, alignSelf: 'center', padding: tokens.spacing.lg, gap: 18 },
  header: { flexDirection: 'row', alignItems: 'center', gap: 14, justifyContent: 'space-between' },
  h1: { fontSize: 30, lineHeight: 38, fontWeight: '700' },
  h2: { fontSize: 21, lineHeight: 27, fontWeight: '700' },
  eyebrow: { fontSize: 12, fontWeight: '700', letterSpacing: 1.2 },
  lead: { fontSize: 15, lineHeight: 21 },
  panel: { borderWidth: 1, borderRadius: 18, padding: 18, gap: 12 },
  sourceInput: { minHeight: 100, textAlignVertical: 'top' },
  input: { borderWidth: 1, borderRadius: 12, padding: 12, fontSize: 15, minHeight: 46 },
  multi: { minHeight: 100, textAlignVertical: 'top' },
  note: { fontSize: 13, lineHeight: 19 },
  fieldLabel: { fontSize: 14, fontWeight: '600' },
  inline: { flexDirection: 'row', alignItems: 'center', gap: 10, minHeight: 40 },
  action: { borderRadius: 12, padding: 14, alignItems: 'center', justifyContent: 'center', minHeight: 48 },
  buttonText: { fontSize: 15, fontWeight: '700' },
  alert: { borderRadius: 12, padding: 12, fontSize: 14, lineHeight: 21 },
  sectionHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  recipeCard: { borderWidth: 1, borderRadius: 16, padding: 16, gap: 14 },
  cardTitle: { fontSize: 18, lineHeight: 24, fontWeight: '700' },
  actionsRow: { flexDirection: 'row', alignItems: 'center', gap: 10, flexWrap: 'wrap' },
  smallButton: { borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10, borderWidth: 1,
    alignItems: 'center', justifyContent: 'center', minHeight: 42 },
  smallButtonText: { fontSize: 13, fontWeight: '600' },
  link: { fontWeight: '600', fontSize: 14 },
});
