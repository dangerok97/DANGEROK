import { useCallback, useEffect, useMemo, useState } from 'react';
import { AppState, Pressable, StyleSheet, Text, View } from 'react-native';
import { PresenceCanvas } from '@/src/components/ora/presence/PresenceCanvas';
import type { KnowledgeGeometry } from '@/src/components/ora/presence/knowledge';
import type { PresenceArea } from '@/src/components/ora/presence/state';
import { presencePalette as palette } from '@/src/theme/presence';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { useReducedMotion } from '@/src/shell';
import { AppInput } from '@/src/components/ui/AppInput';
import { AppButton } from '@/src/components/ui/AppButton';

// Drafts live only in the registration form. Neither names nor examples enter
// the WebView or knowledge API; real stars are created after account saving.
export function registrationStars(first: string, last: string): KnowledgeGeometry[] {
  return [
    ...(first.trim() ? [{ id: 'draft_first_name', area: 'memory' as const, kind: 'node' as const }] : []),
    ...(last.trim() ? [{ id: 'draft_last_name', area: 'memory' as const, kind: 'node' as const }] : []),
  ];
}

export function RegistrationMap({ first, last, example = null, reveal = false, firstStepComplete = false }: {
  first: string; last: string; example?: PresenceArea | null; reveal?: boolean; firstStepComplete?: boolean;
}) {
  const reduced = useReducedMotion();
  const [foreground, setForeground] = useState(AppState.currentState !== 'background');
  const [unavailable, setUnavailable] = useState(false);
  const [paused, setPaused] = useState(false);
  const failed = useCallback(() => setUnavailable(true), []);
  const select = useCallback(() => {}, []);
  useEffect(() => {
    const sub = AppState.addEventListener('change', value => setForeground(value === 'active'));
    return () => sub.remove();
  }, []);
  const stars = useMemo(() => [
    ...(firstStepComplete ? [{ id: 'intro_step_one', area: 'memory' as const, kind: 'node' as const }] : []),
    ...registrationStars(first, last),
    ...(example ? [{ id: `intro_example_${example}`, area: example, kind: 'node' as const }] : []),
  ], [firstStepComplete, first, last, example]);
  const options = useMemo(() => ({
    mode: 'idle' as const, area: example, stars, paused, reduced, active: foreground,
    reveal, revealKey: reveal ? 'registration-intro' : null, intro: true,
  }), [example, stars, paused, reduced, foreground, reveal]);
  const count = Number(!!first.trim()) + Number(!!last.trim());
  return <View style={styles.mapCard} testID="registration-map">
    <View style={styles.mapTop}>
      <Text style={styles.mapCaption}>{example ? 'ESEMPIO DIMOSTRATIVO' : 'LA TUA MAPPA PRENDE FORMA'}</Text>
      {!reduced && !unavailable ? <Pressable accessibilityRole="button" accessibilityLabel={paused ? 'Riprendi anteprima' : 'Metti in pausa anteprima'} onPress={() => setPaused(v => !v)} style={styles.pause}><Text style={styles.mapNote}>{paused ? 'Riprendi' : 'Pausa'}</Text></Pressable> : null}
    </View>
    <View style={styles.canvas} pointerEvents="none">
      {unavailable ? <View style={styles.fallback}><Text style={styles.fallbackText}>✦</Text></View> : <PresenceCanvas options={options} onUnavailable={failed} onSelect={select} />}
    </View>
    <Text accessibilityLiveRegion="polite" style={styles.mapNote} testID="registration-draft-count">
      {count ? `${count === 1 ? '1 prima stella' : '2 prime stelle'} · anteprima` : 'Il punto di partenza sei tu.'}
    </Text>
  </View>;
}

const EXAMPLES = [
  { area: 'home' as const, label: 'Casa', text: 'Una bolletta può aiutare ORA a ricordare una scadenza e cercare offerte più convenienti.' },
  { area: 'calendar' as const, label: 'Impegni', text: 'Sapere dove e quando hai un impegno aiuta ORA a preparare lo spostamento e ricordarti quando partire.' },
  { area: 'people' as const, label: 'Persone', text: 'Un contatto confermato aiuta ORA a raggiungere la persona giusta quando le chiedi di chiamare.' },
];

export function RegistrationIntro({ first, last, onFirstChange, onLastChange, onComplete, onExit, preview = false, busy = false, submitError = '', savedIdentity = false }: {
  first: string; last: string; onFirstChange: (value: string) => void; onLastChange: (value: string) => void;
  onComplete: () => void; onExit: () => void; preview?: boolean; busy?: boolean; submitError?: string; savedIdentity?: boolean;
}) {
  const { colors } = useTheme();
  const [step, setStep] = useState(0);
  const [example, setExample] = useState(-1);
  const [error, setError] = useState('');
  const next = () => {
    if (busy) return;
    if (step === 1 && !preview && !first.trim()) { setError('Inserisci il nome per accendere la prima stella.'); return; }
    if (step === 2 && !preview && !last.trim()) { setError('Inserisci il cognome per accendere la seconda stella.'); return; }
    setError('');
    if (step < 3) setStep(step + 1); else onComplete();
  };
  return <View style={styles.intro} testID="registration-intro">
    <View style={styles.progress}>
      <Text style={{ color: colors.textSecondary }}>Conosci ORA · {step + 1} di 4</Text>
      <Pressable accessibilityRole="button" disabled={busy} onPress={() => { if (step) { setError(''); setStep(step - 1); } else onExit(); }} style={styles.back}><Text style={{ color: colors.textSecondary }}>← Indietro</Text></Pressable>
    </View>
    <Text accessibilityRole="header" style={[styles.title, { color: colors.textPrimary }]}>
      {step === 0 ? 'La tua vita prende forma.' : step === 1 ? 'Partiamo da te.' : step === 2 ? 'La seconda stella è il tuo cognome.' : 'Ogni stella ha uno scopo.'}
    </Text>
    <Text style={[styles.body, { color: colors.textSecondary }]}>
      {step === 0 ? 'Ogni informazione che scegli di condividere diventa una stella. I collegamenti raccontano ciò che ORA conosce della tua vita e la aiutano a rendersi utile.' : step === 1 ? 'Dimmi il tuo nome. Quando lo confermi, si accende la prima stella della tua mappa.' : step === 2 ? 'Il cognome accende la seconda stella. Quando mi chiederai di chiamare qualcuno, mi presenterò con il tuo nome completo.' : 'Casa, impegni, persone: prova a toccare un ramo e scopri a cosa può servire un’informazione.'}
    </Text>
    <RegistrationMap first={step >= 2 ? first : ''} last={step >= 3 ? last : ''} example={step === 3 && example >= 0 ? EXAMPLES[example].area : null} firstStepComplete={step > 0} reveal />
    {step === 1 ? <View style={styles.fields}>
      <AppInput label="Nome" accessibilityLabel="Il tuo nome" value={first} onChangeText={onFirstChange} autoCapitalize="words" autoComplete="given-name" textContentType="givenName" maxLength={60} editable={!busy} />
      <Text style={[styles.small, { color: colors.textSecondary }]}>Il nome resta in anteprima finché non crei l’account.</Text>
    </View> : step === 2 ? <View style={styles.fields}>
      <AppInput label="Cognome" accessibilityLabel="Il tuo cognome" value={last} onChangeText={onLastChange} autoCapitalize="words" autoComplete="family-name" textContentType="familyName" maxLength={60} editable={!busy} />
      <Text style={[styles.quote, { color: colors.textPrimary }]}>«Sono ORA, l’assistente di {first.trim() || 'Nome'} {last.trim() || 'Cognome'}».</Text>
      <Text style={[styles.small, { color: colors.textSecondary }]}>{preview ? 'Stai rivedendo la guida: questi campi non modificano il tuo profilo.' : savedIdentity ? 'Confermeremo nome e cognome nel tuo account quando entrerai in VITA.' : 'Questa è un’anteprima. Salveremo nome e cognome quando creerai l’account.'}</Text>
    </View> : step === 3 ? <View style={styles.fields}>
      <View style={styles.tabs}>{EXAMPLES.map((item, index) => <Pressable key={item.area} accessibilityRole="button" accessibilityState={{ selected: example === index }} onPress={() => setExample(index)} style={[styles.tab, { borderColor: example === index ? colors.accent : colors.border, backgroundColor: example === index ? colors.accentMuted : colors.surface }]}><Text style={{ color: colors.textPrimary }}>{item.label}</Text></Pressable>)}</View>
      <Text accessibilityLiveRegion="polite" style={[styles.body, { color: colors.textPrimary }]}>{example >= 0 ? EXAMPLES[example].text : 'Scegli un ramo per vedere un esempio. Si accenderà soltanto quello che tocchi.'}</Text>
      <Text style={[styles.small, { color: colors.textSecondary }]}>In VITA ogni risposta salvata aggiunge conoscenza alla mappa. Un ramo completo si illumina. Puoi saltare le domande e riprenderle quando vuoi: saltare non crea stelle.</Text>
      <Text style={[styles.small, { color: colors.textSecondary }]}>Tocca una stella in ORA per leggere l’informazione e la sua fonte. Gli esempi di questa guida non vengono salvati.</Text>
    </View> : <Text style={[styles.small, { color: colors.textSecondary }]}>Una breve guida, poi le tue prime stelle. La mappa crescerà con ciò che deciderai di raccontarmi.</Text>}
    {error ? <Text accessibilityRole="alert" style={{ color: colors.error }}>{error}</Text> : null}
    {submitError ? <Text accessibilityRole="alert" style={{ color: colors.error }}>{submitError}</Text> : null}
    <AppButton label={step === 0 ? 'Fammi vedere' : step === 1 ? 'Conferma nome' : step === 2 ? 'Conferma cognome' : preview ? 'Torna a VITA' : savedIdentity ? 'Iniziamo dalla mia vita' : 'Continua con la registrazione'} onPress={next} loading={busy} disabled={busy} fullWidth />
  </View>;
}

const styles = StyleSheet.create({
  intro: { gap: 18 }, progress: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  back: { minHeight: 44, justifyContent: 'center', paddingLeft: 12 },
  title: { fontSize: 30, lineHeight: 36, fontWeight: '600', letterSpacing: -.6 },
  body: { fontSize: 16, lineHeight: 24 }, small: { fontSize: 14, lineHeight: 21 },
  quote: { fontSize: 17, lineHeight: 25, fontWeight: '500' }, fields: { gap: 14 },
  tabs: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  tab: { borderWidth: 1, borderRadius: tokens.radius.full, paddingHorizontal: 18, minHeight: 44, justifyContent: 'center' },
  mapCard: { backgroundColor: palette.background, borderWidth: 1, borderColor: palette.border, borderRadius: tokens.radius.lg, padding: 16, overflow: 'hidden' },
  mapTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
  mapCaption: { color: palette.muted, fontSize: 10, letterSpacing: 1.4, flexShrink: 1 },
  pause: { minHeight: 44, justifyContent: 'center', paddingLeft: 8 },
  mapNote: { color: palette.muted, fontSize: 12, lineHeight: 18 },
  canvas: { height: 220 }, fallback: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  fallbackText: { color: palette.text, fontSize: 42 },
});
