import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { useTheme } from '@/src/theme/ThemeProvider';
import { API_BASE_URL, authToken } from '@/src/api/client';
import { recipesClient, type Recipe } from './client';

type Slot = { day: number; meal: 'breakfast' | 'lunch' | 'dinner'; recipe_id: string; servings: number };
type Plan = { week_start: string; revision: number; household_size: number; budget_eur: number | null; preferences: string[]; slots: Slot[] };
type Item = { id: string; name: string; category: string; checked: boolean; kind: string; recipe_title?: string | null; quantity?: string };
const dayNames = ['Lunedì', 'Martedì', 'Mercoledì', 'Giovedì', 'Venerdì', 'Sabato', 'Domenica'];
const dateString = (d: Date) => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
function mondayOfWeek() { const d = new Date(); d.setHours(12,0,0,0); d.setDate(d.getDate() - ((d.getDay()+6)%7)); return d; }
function shiftWeek(week: string, amount: number) { const d = new Date(week + 'T12:00:00'); d.setDate(d.getDate() + amount*7); return dateString(d); }

export default function CookingPlannerScreen() {
  const router = useRouter();
  const { colors } = useTheme();
  const [week, setWeek] = useState(dateString(mondayOfWeek()));
  const [recipes, setRecipes] = useState<Recipe[]>([]);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [items, setItems] = useState<Item[]>([]);
  const [day, setDay] = useState(0);
  const [servings, setServings] = useState('2');
  const [manual, setManual] = useState('');
  const [budget, setBudget] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const token = useCallback(async () => {
    const t = await authToken.get();
    if (!t) throw new Error('Accedi nuovamente a ORA.');
    return t;
  }, []);
  const request = useCallback(async (path: string, init: RequestInit = {}) => {
    const t = await token();
    if (!API_BASE_URL) throw new Error('Collegamento a ORA non configurato.');
    const response = await fetch(`${API_BASE_URL}/api/cooking${path}`, {
      ...init, cache: 'no-store',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${t}`, ...init.headers },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Operazione non riuscita. Riprova.');
    return data;
  }, [token]);
  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const t = await token();
      const [r, p, s] = await Promise.all([
        recipesClient.list(t),
        request(`/plan?week_start=${week}`),
        request(`/shopping-list?week_start=${week}`),
      ]);
      setRecipes(r.items);
      const next = p.plan as Plan | null;
      setPlan(next ?? { week_start: week, revision: 0, household_size: 2, budget_eur: null, preferences: [], slots: [] });
      setBudget(next?.budget_eur == null ? '' : String(next.budget_eur));
      setItems((s.items ?? []) as Item[]);
    } catch (e) { setError(e instanceof Error ? e.message : 'Cucina non disponibile.'); }
    finally { setLoading(false); }
  }, [request, token, week]);
  useEffect(() => { void load(); }, [load]);
  const recipeById = useMemo(() => new Map(recipes.map(r => [r.id, r])), [recipes]);
  const panel = { backgroundColor: colors.surface, borderColor: colors.border };
  const primary = { color: colors.textPrimary };
  const secondary = { color: colors.textSecondary };
  const savePlan = async () => {
    if (!plan) return;
    setBusy(true); setError(''); setNotice('');
    try {
      // Send only writable fields: the stored plan also carries server metadata (created_at, updated_at).
      const { week_start, revision, household_size, preferences, slots } = plan;
      const data = await request('/plan', { method: 'PUT', body: JSON.stringify({ week_start, revision, household_size, preferences, slots, budget_eur: budget.trim() ? Number(budget) : null }) });
      setPlan(data.plan as Plan);
      const s = await request(`/shopping-list?week_start=${week}`);
      setItems((s.items ?? []) as Item[]);
      setNotice('Piano salvato e lista della spesa aggiornata.');
    } catch (e) { setError(e instanceof Error ? e.message : 'Salvataggio non riuscito.'); }
    finally { setBusy(false); }
  };
  const tick = async (item: Item) => {
    try {
      await request(`/shopping-list/${item.id}?week_start=${week}`, { method: 'PUT', body: JSON.stringify({ checked: !item.checked }) });
      setItems(old => old.map(x => x.id === item.id ? { ...x, checked: !x.checked } : x));
    } catch (e) { setError(e instanceof Error ? e.message : 'Spunta non salvata.'); }
  };
  const addManual = async () => {
    if (!manual.trim()) return;
    try {
      await request(`/shopping-list/manual?week_start=${week}`, { method: 'POST', body: JSON.stringify({ name: manual.trim(), category: 'Altro', quantity: '' }) });
      setManual('');
      const s = await request(`/shopping-list?week_start=${week}`);
      setItems((s.items ?? []) as Item[]);
    } catch (e) { setError(e instanceof Error ? e.message : 'Articolo non aggiunto.'); }
  };
  const action = (label: string, fn: () => void, disabled = false) => (
    <Pressable onPress={fn} disabled={disabled} accessibilityRole="button"
      style={[styles.button, { backgroundColor: colors.accent, opacity: disabled ? 0.55 : 1 }]}>
      <Text style={{ color: colors.onAccent, fontWeight: '700' }}>{label}</Text>
    </Pressable>
  );
  return <SafeAreaView style={{ flex: 1, backgroundColor: colors.backgroundPrimary }} edges={['top']}>
    <ScrollView contentContainerStyle={styles.page} keyboardShouldPersistTaps="handled">
      <View style={styles.header}>
        <View style={{ flex: 1 }}>
          <Text style={[styles.eyebrow, secondary]}>VITA / CUCINA</Text>
          <Text style={[styles.title, primary]}>Piano pasti e spesa</Text>
          <Text style={[styles.body, secondary]}>Organizza le ricette e ricava la lista della spesa.</Text>
        </View>
        <Pressable onPress={() => router.back()} style={[styles.outline, { borderColor: colors.border }]}><Text style={primary}>Ricette</Text></Pressable>
      </View>
      <View style={[styles.panel, panel]}>
        <View style={styles.weekRow}>
          <Pressable onPress={() => setWeek(w => shiftWeek(w, -1))}><Text style={[styles.nav, primary]}>‹</Text></Pressable>
          <Text style={[styles.section, primary]}>{week}</Text>
          <Pressable onPress={() => setWeek(w => shiftWeek(w, 1))}><Text style={[styles.nav, primary]}>›</Text></Pressable>
        </View>
        <Text style={[styles.body, secondary]}>Seleziona il giorno, poi aggiungi una ricetta salvata.</Text>
        <View style={styles.days}>{dayNames.map((name, i) => <Pressable key={name} onPress={() => setDay(i)}
          style={[styles.day, { borderColor: day === i ? colors.accent : colors.border, backgroundColor: day === i ? colors.accentMuted : 'transparent' }]}>
          <Text style={[styles.body, primary]}>{name.slice(0,3)}</Text></Pressable>)}</View>
        {plan?.slots.filter(s => s.day === day).map((slot, i) => <View key={i} style={styles.row}>
          <Text style={[styles.body, primary]}>{slot.meal === 'dinner' ? 'Cena' : slot.meal} · {recipeById.get(slot.recipe_id)?.title ?? 'Ricetta non disponibile'}</Text>
          <Pressable onPress={() => setPlan(p => p ? { ...p, slots: p.slots.filter(x => x !== slot) } : p)}><Text style={{ color: colors.error }}>Rimuovi</Text></Pressable>
        </View>)}
        <Text style={[styles.label, primary]}>Ricetta da aggiungere</Text>
        {recipes.length ? <View style={styles.recipeList}>{recipes.map(r => <Pressable key={r.id} onPress={() => {
          if (!plan) return;
          const servingsNum = Number(servings);
          if (!Number.isInteger(servingsNum) || servingsNum < 1 || servingsNum > 30) { setError('Inserisci porzioni da 1 a 30.'); return; }
          const slots = plan.slots.filter(s => !(s.day === day && s.meal === 'dinner'));
          slots.push({ day, meal: 'dinner', recipe_id: r.id, servings: servingsNum });
          setPlan({ ...plan, slots }); setNotice(`Aggiunta “${r.title}” a ${dayNames[day]}.`);
        }} style={[styles.recipe, { borderColor: colors.border }]}><Text style={[styles.body, primary]}>{r.title}</Text><Text style={[styles.caption, secondary]}>Aggiungi a cena</Text></Pressable>)}</View>
          : <Text style={[styles.body, secondary]}>Prima salva almeno una ricetta nel ricettario.</Text>}
        <Text style={[styles.label, primary]}>Porzioni</Text>
        <TextInput value={servings} onChangeText={setServings} keyboardType="number-pad" style={[styles.input, { color: colors.textPrimary, borderColor: colors.border }]} />
        <Text style={[styles.label, primary]}>Budget settimanale (€), facoltativo</Text>
        <TextInput value={budget} onChangeText={setBudget} keyboardType="decimal-pad" style={[styles.input, { color: colors.textPrimary, borderColor: colors.border }]} placeholder="es. 70" placeholderTextColor={colors.textSecondary} />
        {action(busy ? 'Salvataggio…' : 'Salva piano e aggiorna la spesa', () => { void savePlan(); }, busy || loading)}
      </View>
      <View style={[styles.panel, panel]}>
        <Text style={[styles.section, primary]}>Lista della spesa ({items.filter(i => !i.checked).length} da prendere)</Text>
        <Text style={[styles.body, secondary]}>Le quantità restano quelle scritte nelle ricette; ORA non inventa conversioni.</Text>
        {items.length ? items.map(item => <Pressable key={item.id} onPress={() => { void tick(item); }} style={[styles.item, { borderBottomColor: colors.border }]}>
          <Text style={[styles.check, { color: item.checked ? colors.accent : colors.textSecondary }]}>{item.checked ? '☑' : '□'}</Text>
          <View style={{ flex: 1 }}><Text style={[styles.body, primary, item.checked && { textDecorationLine: 'line-through' }]}>{item.name}</Text>
            <Text style={[styles.caption, secondary]}>{item.category}{item.recipe_title ? ` · ${item.recipe_title}` : ''}</Text></View>
        </Pressable>) : <Text style={[styles.body, secondary]}>La lista si popola quando salvi un piano con ricette.</Text>}
        <View style={styles.row}><TextInput value={manual} onChangeText={setManual} placeholder="Aggiungi un prodotto" placeholderTextColor={colors.textSecondary}
          style={[styles.input, { flex: 1, color: colors.textPrimary, borderColor: colors.border }]} />
          {action('Aggiungi', () => { void addManual(); }, !manual.trim())}</View>
      </View>
      {loading ? <ActivityIndicator color={colors.accent} /> : null}
      {error ? <Text style={[styles.alert, { color: colors.error }]}>{error}</Text> : null}
      {notice ? <Text style={[styles.alert, { color: colors.textPrimary, backgroundColor: colors.accentMuted }]}>{notice}</Text> : null}
    </ScrollView>
  </SafeAreaView>;
}
const styles = StyleSheet.create({
  page: { padding: 18, paddingBottom: 50, gap: 16, maxWidth: 900, width: '100%', alignSelf: 'center' },
  header: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  eyebrow: { fontSize: 11, letterSpacing: 1.2, fontWeight: '700', marginBottom: 5 },
  title: { fontSize: 27, fontWeight: '800' }, section: { fontSize: 19, fontWeight: '800' },
  body: { fontSize: 14, lineHeight: 21 }, caption: { fontSize: 12, marginTop: 3 },
  label: { fontSize: 13, fontWeight: '700', marginTop: 8, marginBottom: 5 },
  panel: { borderWidth: 1, borderRadius: 18, padding: 16, gap: 12 },
  weekRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  nav: { fontSize: 28, paddingHorizontal: 8 }, days: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  day: { borderWidth: 1, borderRadius: 10, paddingVertical: 9, paddingHorizontal: 10 },
  recipeList: { gap: 7 }, recipe: { borderWidth: 1, borderRadius: 12, padding: 10 },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  input: { borderWidth: 1, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10, minWidth: 70 },
  button: { borderRadius: 11, paddingHorizontal: 14, paddingVertical: 11, alignItems: 'center', justifyContent: 'center' },
  outline: { borderWidth: 1, borderRadius: 10, padding: 10 }, item: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 10, borderBottomWidth: StyleSheet.hairlineWidth },
  check: { fontSize: 22 }, alert: { padding: 12, borderRadius: 10, overflow: 'hidden' },
});
