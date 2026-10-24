import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Linking, Modal, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { Image } from 'expo-image';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '@/src/contexts/AuthContext';
import { useTheme } from '@/src/theme/ThemeProvider';
import { useAmbientInset } from '@/src/shell';
import { tokens } from '@/src/theme/tokens';
import { pickGarmentPhoto } from '@/src/wardrobe/pickPhoto';
import { recipesClient, toRecipeWrite, type Recipe, type RecipePreview, type RecipeWrite } from './client';
import { matchesFilter, minutesLabel, scaleLine, stepTimerMinutes, type RecipeFilter } from './cooking';

const message = (error: unknown) => error instanceof Error ? error.message : 'Operazione non riuscita.';
const splitLines = (source: string) => source.split('\n').map(s => s.trim()).filter(Boolean);
const stateLabel = (recipe: Recipe) => !recipe.ingredients.length || !recipe.steps.length
  ? 'Da completare' : recipe.status === 'cooked' ? 'Già cucinata' : 'Da provare';
const QUALITY: Record<string, string> = {
  structured_page: 'Letta dalla pagina della ricetta',
  ai_from_caption: 'Ricavata dal testo del post',
  ai_from_text: 'Riordinata dal testo incollato',
  ai_from_photo: 'Trascritta dalla foto',
  structured_text: 'Letta dal testo incollato',
};

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
  const [reading, setReading] = useState<'' | 'link' | 'photo'>('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [source, setSource] = useState(incoming.slice(0, 12000));
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<RecipeFilter | `tag:${string}`>('all');
  const [previewResult, setPreviewResult] = useState<RecipePreview | null>(null);
  const [draft, setDraft] = useState<RecipeWrite | null>(null);
  const [editId, setEditId] = useState<string | null>(null);
  const [ingredientsText, setIngredientsText] = useState('');
  const [stepsText, setStepsText] = useState('');
  const [tagsText, setTagsText] = useState('');
  const [servingsText, setServingsText] = useState('');
  const [minutesText, setMinutesText] = useState('');
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [viewing, setViewing] = useState<Recipe | null>(null);
  const scroll = useRef<ScrollView>(null);
  const autoRead = useRef(false);

  const load = useCallback(async () => {
    const token = await recipesClient.token();
    if (!token) throw new Error('Accedi nuovamente a ORA.');
    const data = await recipesClient.list(token);
    setItems(data.items);
    return data.items;
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
    setIngredientsText(''); setStepsText(''); setTagsText(''); setServingsText(''); setMinutesText('');
    setError('');
  };
  const openDraft = (value: RecipeWrite) => {
    setDraft(value);
    setIngredientsText(value.ingredients.join('\n'));
    setStepsText(value.steps.join('\n'));
    setTagsText(value.tags.join(', '));
    setServingsText(value.servings ? String(value.servings) : '');
    setMinutesText(value.total_minutes ? String(value.total_minutes) : '');
    scroll.current?.scrollTo({ y: 0, animated: true });
  };
  const startPreview = useCallback(async (text?: string) => {
    const value = (text ?? source).trim();
    if (busy || !value) { setError('Incolla il link o il testo della ricetta.'); return; }
    setBusy(true); setReading('link'); setError(''); setNotice('');
    try {
      const token = await recipesClient.token();
      if (!token) throw new Error('Accedi nuovamente a ORA.');
      const result = await recipesClient.preview(token, value);
      setPreviewResult(result);
      setEditId(null);
      openDraft({ ...result.draft, revision: 0 });
    } catch (err) { setError(message(err)); }
    finally { setBusy(false); setReading(''); }
  }, [busy, source]);

  // Opened from a shared link (ORA chat, Siri, a link to /cucina?url=…): read it straight away.
  useEffect(() => {
    if (incoming && !autoRead.current && !loading) {
      autoRead.current = true;
      void startPreview(incoming);
    }
  }, [incoming, loading, startPreview]);

  const fromPhoto = async () => {
    if (busy) return;
    setError(''); setNotice('');
    try {
      const photo = await pickGarmentPhoto();
      if (!photo) return;
      setBusy(true); setReading('photo');
      const token = await recipesClient.token();
      if (!token) throw new Error('Accedi nuovamente a ORA.');
      const result = await recipesClient.previewPhoto(token, photo);
      if (result.quality === 'unreadable') { setError(result.warnings[0] || 'Foto non leggibile.'); return; }
      setPreviewResult(result); setEditId(null);
      openDraft({ ...result.draft, revision: 0 });
    } catch (err) { setError(message(err)); }
    finally { setBusy(false); setReading(''); }
  };
  const edit = (item: Recipe) => {
    setError(''); setNotice(''); setPreviewResult(null); setDeleteTarget(null); setViewing(null);
    setEditId(item.id);
    openDraft(toRecipeWrite(item));
  };
  const buildWrite = (): RecipeWrite | null => {
    if (!draft) return null;
    const portions = servingsText.trim() ? Number(servingsText.trim()) : null;
    if (portions !== null && (!Number.isInteger(portions) || portions < 1 || portions > 99)) {
      setError('Le porzioni devono essere un numero intero da 1 a 99.'); return null;
    }
    const minutes = minutesText.trim() ? Number(minutesText.trim()) : null;
    if (minutes !== null && (!Number.isInteger(minutes) || minutes < 1 || minutes > 10080)) {
      setError('Il tempo totale è in minuti, ad esempio 45.'); return null;
    }
    const value = { ...draft, title: draft.title.trim(), ingredients: splitLines(ingredientsText),
      steps: splitLines(stepsText), tags: tagsText.split(',').map(s => s.trim()).filter(Boolean),
      servings: portions, total_minutes: minutes };
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
  const patchSaved = async (item: Recipe, change: Partial<RecipeWrite>) => {
    if (busy) return;
    setBusy(true); setError('');
    try {
      const token = await recipesClient.token();
      if (!token) throw new Error('Accedi nuovamente a ORA.');
      const { item: updated } = await recipesClient.update(token, item.id, { ...toRecipeWrite(item), ...change });
      await load();
      setViewing(current => current && current.id === item.id ? updated : current);
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
  const shop = async (lines: string[]) => {
    setBusy(true); setError('');
    try {
      const token = await recipesClient.token();
      if (!token) throw new Error('Accedi nuovamente a ORA.');
      await recipesClient.addToShopping(token, lines);
      setNotice(`${lines.length} ${lines.length === 1 ? 'ingrediente aggiunto' : 'ingredienti aggiunti'} alla lista della spesa.`);
    } catch (err) { setError(message(err)); }
    finally { setBusy(false); }
  };

  const tags = useMemo(() => {
    const counts = new Map<string, number>();
    items.forEach(item => item.tags.forEach(t => {
      const key = t.toLocaleLowerCase('it'); counts.set(key, (counts.get(key) || 0) + 1);
    }));
    return [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8).map(([t]) => t);
  }, [items]);
  const visible = items.filter(item => {
    const haystack = [item.title, ...item.ingredients, ...item.tags].join(' ').toLocaleLowerCase('it');
    return haystack.includes(search.toLocaleLowerCase('it').trim()) && matchesFilter(item, filter);
  });
  const canSave = !!draft && !busy;

  const inputStyle = [styles.input, { borderColor: colors.border, backgroundColor: colors.surface,
    color: colors.textPrimary }];
  const secondary = { color: colors.textSecondary };
  const primary = { color: colors.textPrimary };
  const action = (label: string, fn: () => void, disabled = false, icon?: keyof typeof Ionicons.glyphMap, quiet = false) => (
    <Pressable onPress={fn} disabled={disabled} accessibilityRole="button" accessibilityLabel={label}
      style={({ pressed }) => [styles.action, quiet
        ? { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border }
        : { backgroundColor: colors.accent }, (pressed || disabled) && { opacity: 0.6 }]}>
      {icon ? <Ionicons name={icon} size={18} color={quiet ? colors.textPrimary : colors.onAccent} /> : null}
      <Text style={[styles.buttonText, { color: quiet ? colors.textPrimary : colors.onAccent }]}>{label}</Text>
    </Pressable>
  );
  const chip = (label: string, key: RecipeFilter | `tag:${string}`) => (
    <Pressable key={key} onPress={() => setFilter(key)} accessibilityRole="button"
      accessibilityState={{ selected: filter === key }}
      style={[styles.chip, { borderColor: filter === key ? colors.accent : colors.border,
        backgroundColor: filter === key ? colors.accentMuted : colors.surface }]}>
      <Text style={[styles.chipText, { color: filter === key ? colors.accent : colors.textPrimary }]}>{label}</Text>
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
            <Text style={[styles.lead, secondary]}>Incolla un link da Instagram, TikTok, YouTube o da un sito: ORA legge la ricetta e la mette in ordine.</Text>
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
          <TextInput testID="recipes-source" style={[inputStyle, styles.sourceInput]} multiline
            placeholder="Link Instagram, TikTok, YouTube, sito di ricette — oppure il testo"
            placeholderTextColor={colors.textSecondary} maxLength={12000}
            autoCapitalize="none" autoCorrect={false} value={source} onChangeText={setSource} />
          <View style={styles.actionsRow}>
            <View style={{ flexGrow: 1 }}>{action(reading === 'link' ? 'Sto leggendo la ricetta…' : 'Leggi il contenuto',
              () => { void startPreview(); }, busy || !source.trim(), 'sparkles-outline')}</View>
            <View style={{ flexGrow: 1 }}>{action(reading === 'photo' ? 'Leggo la foto…' : 'Da foto o screenshot',
              () => { void fromPhoto(); }, busy, 'camera-outline', true)}</View>
          </View>
          {reading ? <View style={styles.inline}><ActivityIndicator color={colors.accent} />
            <Text style={[styles.note, secondary]}>Può volerci qualche secondo: leggo la pagina o il testo del post e metto in ordine ingredienti e passaggi.</Text></View> : null}
          <Text style={[styles.note, secondary]}>Su Instagram, se il post non si apre, copia la didascalia e incollala qui. Le quantità non scritte nella fonte non vengono mai inventate.</Text>
        </View>

        {draft ? (
          <View testID="recipes-editor" style={[styles.panel,
            { borderColor: colors.border, backgroundColor: colors.surface }]}>
            <View style={styles.header}>
              <Text style={[styles.h2, primary]}>{editId ? 'Modifica ricetta' : 'Controlla prima di salvare'}</Text>
              <Pressable accessibilityRole="button" accessibilityLabel="Annulla modifica"
                onPress={cancel}><Ionicons name="close-circle-outline" size={28} color={colors.textSecondary} /></Pressable>
            </View>
            {previewResult && QUALITY[previewResult.quality] ? <Text testID="recipes-quality"
              style={[styles.badge, { color: colors.accent, backgroundColor: colors.accentMuted }]}>
              {QUALITY[previewResult.quality]}{previewResult.source_label ? ` · ${previewResult.source_label}` : ''}
            </Text> : null}
            {previewResult?.warnings.map((warning, index) => (
              <Text key={index} style={[styles.note, { color: colors.error }]}>• {warning}</Text>
            ))}
            {draft.image_url ? <Image source={{ uri: draft.image_url }} style={styles.heroImage} contentFit="cover" /> : null}
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
            <View style={styles.actionsRow}>
              <View style={{ flex: 1, gap: 6 }}>
                <Text style={[styles.fieldLabel, primary]}>Porzioni</Text>
                <TextInput style={inputStyle} keyboardType="number-pad" value={servingsText}
                  onChangeText={setServingsText} placeholder="Es. 2" placeholderTextColor={colors.textSecondary} />
              </View>
              <View style={{ flex: 1, gap: 6 }}>
                <Text style={[styles.fieldLabel, primary]}>Tempo (minuti)</Text>
                <TextInput testID="recipes-minutes" style={inputStyle} keyboardType="number-pad" value={minutesText}
                  onChangeText={setMinutesText} placeholder="Es. 30" placeholderTextColor={colors.textSecondary} />
              </View>
            </View>
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
        {items.length ? <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chips}
          testID="recipes-filters">
          {chip('Tutte', 'all')}{chip('Preferite', 'favorite')}{chip('Da provare', 'to_try')}{chip('Veloci', 'quick')}
          {tags.map(t => chip(t, `tag:${t}`))}
        </ScrollView> : null}
        {!loading && !items.length ? (
          <View style={[styles.panel, { borderColor: colors.border, backgroundColor: colors.surface }]}>
            <Text style={secondary}>Il ricettario è vuoto. Incolla qui sopra il link di una ricetta che hai visto sui social, oppure fotografa una pagina del tuo libro di cucina.</Text>
          </View>
        ) : null}
        {!loading && items.length > 0 && !visible.length ? <Text style={secondary}>Nessuna ricetta trovata.</Text> : null}
        <View style={styles.grid}>
          {visible.map(item => (
            <View key={item.id} testID="recipes-item" style={[styles.recipeCard,
              { borderColor: colors.border, backgroundColor: colors.surface }]}>
              <Pressable onPress={() => setViewing(item)} accessibilityRole="button"
                accessibilityLabel={`Apri ${item.title}`} style={{ gap: 10 }}>
                {item.image_url ? <Image source={{ uri: item.image_url }} style={styles.cardImage} contentFit="cover" />
                  : <View style={[styles.cardImage, styles.placeholder, { backgroundColor: colors.backgroundSecondary }]}>
                    <Ionicons name="restaurant-outline" size={30} color={colors.textTertiary} />
                  </View>}
                <Text style={[styles.cardTitle, primary]} numberOfLines={2}>{item.title}</Text>
                <Text style={[styles.note, secondary]}>{stateLabel(item)} · {item.ingredients.length} ingredienti · {item.steps.length} passaggi{item.total_minutes ? ` · ${minutesLabel(item.total_minutes)}` : ''}</Text>
              </Pressable>
              <View style={styles.actionsRow}>
                <Pressable accessibilityRole="button"
                  accessibilityLabel={item.favorite ? 'Rimuovi dai preferiti' : 'Aggiungi ai preferiti'}
                  disabled={busy} onPress={() => { void patchSaved(item, { favorite: !item.favorite }); }}
                  style={[styles.iconButton, { borderColor: colors.border }]}>
                  <Ionicons name={item.favorite ? 'star' : 'star-outline'} size={20} color={colors.accent} />
                </Pressable>
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
        </View>
      </ScrollView>

      {viewing ? <RecipeView recipe={viewing} busy={busy} onClose={() => setViewing(null)}
        onEdit={() => edit(viewing)} onShop={lines => { void shop(lines); }}
        onCooked={() => { void patchSaved(viewing, { status: 'cooked' }); }} /> : null}
    </SafeAreaView>
  );
}

function RecipeView({ recipe, busy, onClose, onEdit, onShop, onCooked }: {
  recipe: Recipe; busy: boolean; onClose: () => void; onEdit: () => void;
  onShop: (lines: string[]) => void; onCooked: () => void;
}) {
  const { colors } = useTheme();
  const [servings, setServings] = useState(recipe.servings || 0);
  const [have, setHave] = useState<Set<number>>(new Set());
  const [cooking, setCooking] = useState(false);
  const factor = recipe.servings && servings ? servings / recipe.servings : 1;
  const lines = recipe.ingredients.map(line => scaleLine(line, factor));
  const missing = lines.filter((_, i) => !have.has(i));
  const primary = { color: colors.textPrimary };
  const secondary = { color: colors.textSecondary };

  if (cooking) return <CookingMode recipe={recipe} lines={lines} onClose={() => setCooking(false)} onDone={() => { setCooking(false); onCooked(); }} />;

  return (
    <Modal visible animationType="slide" onRequestClose={onClose} presentationStyle="pageSheet">
      <SafeAreaView style={{ flex: 1, backgroundColor: colors.backgroundPrimary }}>
        <ScrollView contentContainerStyle={[styles.page, { paddingBottom: 60 }]} testID="recipes-view">
          <View style={styles.header}>
            <Pressable onPress={onClose} accessibilityRole="button" accessibilityLabel="Chiudi ricetta"
              style={[styles.iconButton, { borderColor: colors.border }]}>
              <Ionicons name="chevron-down" size={22} color={colors.textPrimary} />
            </Pressable>
            <Pressable onPress={onEdit} accessibilityRole="button" style={[styles.smallButton, { borderColor: colors.border }]}>
              <Text style={[styles.smallButtonText, primary]}>Modifica</Text>
            </Pressable>
          </View>
          {recipe.image_url ? <Image source={{ uri: recipe.image_url }} style={styles.heroImage} contentFit="cover" /> : null}
          <Text style={[styles.h1, primary]}>{recipe.title}</Text>
          <Text style={[styles.note, secondary]}>
            {[recipe.total_minutes ? minutesLabel(recipe.total_minutes) : '', recipe.tags.join(' · '),
              recipe.status === 'cooked' ? 'Già cucinata' : ''].filter(Boolean).join('  ·  ')}
          </Text>
          {recipe.steps.length ? <Pressable testID="recipes-cook" onPress={() => setCooking(true)} accessibilityRole="button"
            style={[styles.action, { backgroundColor: colors.accent }]}>
            <Ionicons name="flame-outline" size={18} color={colors.onAccent} />
            <Text style={[styles.buttonText, { color: colors.onAccent }]}>Cucina ora, passo passo</Text>
          </Pressable> : null}

          <View style={styles.sectionHeader}>
            <Text style={[styles.h2, primary]}>Ingredienti</Text>
            {recipe.servings ? <View style={[styles.stepper, { borderColor: colors.border }]}>
              <Pressable accessibilityRole="button" accessibilityLabel="Meno porzioni" disabled={servings <= 1}
                onPress={() => setServings(s => Math.max(1, s - 1))} style={styles.stepButton}>
                <Ionicons name="remove" size={18} color={colors.accent} /></Pressable>
              <Text testID="recipes-servings" style={[styles.fieldLabel, primary]}>{servings} {servings === 1 ? 'porzione' : 'porzioni'}</Text>
              <Pressable accessibilityRole="button" accessibilityLabel="Più porzioni" disabled={servings >= 40}
                onPress={() => setServings(s => Math.min(40, s + 1))} style={styles.stepButton}>
                <Ionicons name="add" size={18} color={colors.accent} /></Pressable>
            </View> : null}
          </View>
          <Text style={[styles.note, secondary]}>Spunta quello che hai già in casa.</Text>
          {lines.map((line, i) => (
            <Pressable key={i} accessibilityRole="checkbox" accessibilityState={{ checked: have.has(i) }}
              onPress={() => setHave(prev => { const next = new Set(prev); if (next.has(i)) next.delete(i); else next.add(i); return next; })}
              style={styles.ingredientRow}>
              <Ionicons name={have.has(i) ? 'checkmark-circle' : 'ellipse-outline'} size={22} color={colors.accent} />
              <Text style={[styles.body, primary, have.has(i) && { textDecorationLine: 'line-through', color: colors.textTertiary }]}>{line}</Text>
            </Pressable>
          ))}
          {missing.length ? <Pressable testID="recipes-shop" disabled={busy} onPress={() => onShop(missing)} accessibilityRole="button"
            style={[styles.action, { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border }]}>
            <Ionicons name="cart-outline" size={18} color={colors.textPrimary} />
            <Text style={[styles.buttonText, primary]}>Aggiungi {missing.length === lines.length ? 'tutto' : `i ${missing.length} mancanti`} alla spesa</Text>
          </Pressable> : null}

          {recipe.steps.length ? <Text style={[styles.h2, primary]}>Procedimento</Text> : null}
          {recipe.steps.map((step, i) => (
            <View key={i} style={styles.stepRow}>
              <Text style={[styles.stepNumber, { color: colors.accent }]}>{i + 1}</Text>
              <Text style={[styles.body, primary, { flex: 1 }]}>{step}</Text>
            </View>
          ))}
          {recipe.source_url ? (
            <Pressable accessibilityRole="link" onPress={() => { void Linking.openURL(recipe.source_url); }}>
              <Text style={[styles.link, { color: colors.accent }]}>Apri la fonte originale ↗</Text>
            </Pressable>
          ) : null}
        </ScrollView>
      </SafeAreaView>
    </Modal>
  );
}

function CookingMode({ recipe, lines, onClose, onDone }: {
  recipe: Recipe; lines: string[]; onClose: () => void; onDone: () => void;
}) {
  const { colors } = useTheme();
  const [index, setIndex] = useState(0);
  const [showIngredients, setShowIngredients] = useState(false);
  const [timerEnd, setTimerEnd] = useState<number | null>(null);
  const [now, setNow] = useState(Date.now());
  const step = recipe.steps[index] || '';
  const minutes = stepTimerMinutes(step);
  const last = index === recipe.steps.length - 1;

  useEffect(() => {
    if (!timerEnd) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [timerEnd]);
  const left = timerEnd ? Math.max(0, Math.round((timerEnd - now) / 1000)) : 0;
  const clock = `${Math.floor(left / 60)}:${String(left % 60).padStart(2, '0')}`;

  return (
    <Modal visible animationType="fade" onRequestClose={onClose}>
      <SafeAreaView style={{ flex: 1, backgroundColor: colors.backgroundPrimary }} testID="recipes-cooking">
        <View style={[styles.page, { flex: 1 }]}>
          <View style={styles.header}>
            <Pressable onPress={onClose} accessibilityRole="button" accessibilityLabel="Esci dalla modalità cucina"
              style={[styles.iconButton, { borderColor: colors.border }]}>
              <Ionicons name="close" size={22} color={colors.textPrimary} />
            </Pressable>
            <Text style={[styles.note, { color: colors.textSecondary, flex: 1, textAlign: 'center' }]} numberOfLines={1}>{recipe.title}</Text>
            <Pressable onPress={() => setShowIngredients(v => !v)} accessibilityRole="button"
              style={[styles.smallButton, { borderColor: colors.border }]}>
              <Text style={[styles.smallButtonText, { color: colors.textPrimary }]}>{showIngredients ? 'Passaggi' : 'Ingredienti'}</Text>
            </Pressable>
          </View>
          <View style={[styles.progress, { backgroundColor: colors.divider }]}>
            <View style={{ width: `${((index + 1) / recipe.steps.length) * 100}%`, height: '100%', backgroundColor: colors.accent, borderRadius: 3 }} />
          </View>
          <ScrollView style={{ flex: 1 }} contentContainerStyle={{ gap: 18, paddingVertical: 20 }}>
            {showIngredients ? lines.map((line, i) => <Text key={i} style={[styles.cookIngredient, { color: colors.textPrimary }]}>• {line}</Text>) : <>
              <Text style={[styles.eyebrow, { color: colors.accent }]}>PASSAGGIO {index + 1} DI {recipe.steps.length}</Text>
              <Text testID="recipes-cooking-step" style={[styles.cookStep, { color: colors.textPrimary }]}>{step}</Text>
              {minutes ? (timerEnd ? <View style={[styles.timer, { borderColor: colors.accent, backgroundColor: colors.accentMuted }]}>
                <Ionicons name={left ? 'timer-outline' : 'notifications'} size={22} color={colors.accent} />
                <Text style={[styles.timerText, { color: colors.accent }]}>{left ? clock : 'Tempo scaduto'}</Text>
                <Pressable onPress={() => setTimerEnd(null)} accessibilityRole="button"><Text style={[styles.smallButtonText, { color: colors.textSecondary }]}>Ferma</Text></Pressable>
              </View> : <Pressable testID="recipes-timer" onPress={() => { setTimerEnd(Date.now() + minutes * 60000); setNow(Date.now()); }}
                accessibilityRole="button" style={[styles.timer, { borderColor: colors.border }]}>
                <Ionicons name="timer-outline" size={22} color={colors.textPrimary} />
                <Text style={[styles.timerText, { color: colors.textPrimary }]}>Avvia timer {minutesLabel(minutes)}</Text>
              </Pressable>) : null}
            </>}
          </ScrollView>
          <View style={styles.actionsRow}>
            <Pressable disabled={index === 0} onPress={() => { setIndex(i => i - 1); setTimerEnd(null); }} accessibilityRole="button"
              style={[styles.action, { flex: 1, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border }, index === 0 && { opacity: 0.4 }]}>
              <Text style={[styles.buttonText, { color: colors.textPrimary }]}>Indietro</Text>
            </Pressable>
            <Pressable onPress={() => { if (last) onDone(); else { setIndex(i => i + 1); setTimerEnd(null); } }} accessibilityRole="button"
              testID="recipes-cooking-next" style={[styles.action, { flex: 2, backgroundColor: colors.accent }]}>
              <Text style={[styles.buttonText, { color: colors.onAccent }]}>{last ? 'Fatto! Segna come cucinata' : 'Avanti'}</Text>
            </Pressable>
          </View>
        </View>
      </SafeAreaView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  page: { width: '100%', maxWidth: 920, alignSelf: 'center', padding: tokens.spacing.lg, gap: 18 },
  header: { flexDirection: 'row', alignItems: 'center', gap: 14, justifyContent: 'space-between' },
  h1: { fontSize: 30, lineHeight: 38, fontWeight: '700' },
  h2: { fontSize: 21, lineHeight: 27, fontWeight: '700' },
  eyebrow: { fontSize: 12, fontWeight: '700', letterSpacing: 1.2 },
  lead: { fontSize: 15, lineHeight: 21 },
  body: { fontSize: 16, lineHeight: 24 },
  panel: { borderWidth: 1, borderRadius: 18, padding: 18, gap: 12 },
  sourceInput: { minHeight: 90, textAlignVertical: 'top' },
  input: { borderWidth: 1, borderRadius: 12, padding: 12, fontSize: 15, minHeight: 46 },
  multi: { minHeight: 100, textAlignVertical: 'top' },
  note: { fontSize: 13, lineHeight: 19 },
  badge: { alignSelf: 'flex-start', borderRadius: 999, paddingHorizontal: 12, paddingVertical: 6, fontSize: 13, fontWeight: '600', overflow: 'hidden' },
  fieldLabel: { fontSize: 14, fontWeight: '600' },
  inline: { flexDirection: 'row', alignItems: 'center', gap: 10, minHeight: 40 },
  action: { borderRadius: 12, padding: 14, alignItems: 'center', justifyContent: 'center', minHeight: 48, flexDirection: 'row', gap: 8 },
  buttonText: { fontSize: 15, fontWeight: '700' },
  alert: { borderRadius: 12, padding: 12, fontSize: 14, lineHeight: 21 },
  sectionHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' },
  chips: { flexDirection: 'row', gap: 8, paddingVertical: 2 },
  chip: { borderWidth: 1, borderRadius: 999, paddingHorizontal: 14, paddingVertical: 8 },
  chipText: { fontSize: 13, fontWeight: '600' },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 14 },
  recipeCard: { borderWidth: 1, borderRadius: 16, padding: 12, gap: 12, flexGrow: 1, flexBasis: 260, maxWidth: '100%' },
  cardImage: { width: '100%', height: 150, borderRadius: 12 },
  heroImage: { width: '100%', height: 220, borderRadius: 16 },
  placeholder: { alignItems: 'center', justifyContent: 'center' },
  cardTitle: { fontSize: 18, lineHeight: 24, fontWeight: '700' },
  actionsRow: { flexDirection: 'row', alignItems: 'center', gap: 10, flexWrap: 'wrap' },
  smallButton: { borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10, borderWidth: 1,
    alignItems: 'center', justifyContent: 'center', minHeight: 42 },
  iconButton: { borderRadius: 10, borderWidth: 1, width: 42, height: 42, alignItems: 'center', justifyContent: 'center' },
  smallButtonText: { fontSize: 13, fontWeight: '600' },
  link: { fontWeight: '600', fontSize: 14 },
  stepper: { flexDirection: 'row', alignItems: 'center', borderWidth: 1, borderRadius: 12, paddingHorizontal: 4 },
  stepButton: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  ingredientRow: { flexDirection: 'row', alignItems: 'center', gap: 12, minHeight: 40 },
  stepRow: { flexDirection: 'row', gap: 14, alignItems: 'flex-start' },
  stepNumber: { fontSize: 18, fontWeight: '800', width: 24 },
  progress: { height: 6, borderRadius: 3, overflow: 'hidden' },
  cookStep: { fontSize: 26, lineHeight: 36, fontWeight: '600' },
  cookIngredient: { fontSize: 20, lineHeight: 30 },
  timer: { flexDirection: 'row', alignItems: 'center', gap: 12, borderWidth: 1, borderRadius: 14, padding: 14, alignSelf: 'flex-start' },
  timerText: { fontSize: 18, fontWeight: '700' },
});
