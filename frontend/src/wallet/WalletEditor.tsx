import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Image, Platform, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { FORMATS, walletClient, type CardInput, type Candidate, type LoyaltyCard } from './client';
import { collapseScanCandidates, safePreview } from './scanCandidates';
import { pickPhoto } from './pickPhoto';

type Props = {
  initial: CardInput;
  initialImage?: string;
  onSaved: (card: LoyaltyCard) => void;
  onCancel: () => void;
};
const errorMessage = (error: unknown) => error instanceof Error ? error.message : 'Operazione non riuscita. Riprova.';

/** Photo → deterministic code+format → preview → one Save. Manual is opt-in. */
export function WalletEditor({ initial, initialImage, onSaved, onCancel }: Props) {
  const { colors } = useTheme();
  const alive = useRef(true);
  const locked = useRef(false);
  const [draft, setDraft] = useState(initial);
  const [preview, setPreview] = useState<string | null>(safePreview(initialImage));
  const [choices, setChoices] = useState<Candidate[]>([]);
  const [manual, setManual] = useState(false);
  const [busy, setBusy] = useState<'read' | 'save' | null>(null);
  const [error, setError] = useState('');
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);

  const choose = (candidate: Candidate) => {
    setDraft(value => ({ ...value, code: candidate.code, format: candidate.format, source: 'image' }));
    setPreview(safePreview(candidate.image));
    setChoices([]); setManual(false); setError('');
  };
  const importPhoto = async (camera: boolean) => {
    if (locked.current) return;
    locked.current = true; setBusy('read'); setError('');
    try {
      const photo = await pickPhoto(camera);
      if (!photo || !alive.current) return;
      // A new actual upload invalidates the old result. Cancelling a picker
      // leaves the draft alone; a failed/new/ambiguous scan cannot save it.
      setDraft(value => ({ ...value, code: '', source: 'image' }));
      setPreview(null); setChoices([]); setManual(false);
      const token = await walletClient.token();
      if (!token) throw new Error('Accedi nuovamente a ORA.');
      const result = await walletClient.decode(token, photo);
      if (!alive.current) return;
      const candidates = collapseScanCandidates(result.candidates);
      if (!candidates.length) throw new Error('Non riesco a leggere il codice. Prova una foto più vicina o uno screenshot.');
      if (candidates.length === 1) choose(candidates[0]);
      else setChoices(candidates);
    } catch (err) { if (alive.current) setError(errorMessage(err)); }
    finally { locked.current = false; if (alive.current) setBusy(null); }
  };
  const save = async () => {
    if (locked.current || !draft.code || choices.length) return;
    locked.current = true; setBusy('save'); setError('');
    try {
      const token = await walletClient.token();
      if (!token) throw new Error('Accedi nuovamente a ORA.');
      // The visible notice + explicit Save are the user's static-loyalty
      // declaration. A photo cannot prove staticness or merchant acceptance.
      const result = await walletClient.save(token, { ...draft, name: draft.name.trim() || 'Tessera fedeltà', static_confirmed: true });
      if (alive.current) onSaved(result.card);
    } catch (err) { if (alive.current) setError(errorMessage(err)); }
    finally { locked.current = false; if (alive.current) setBusy(null); }
  };
  const changeManual = (patch: Partial<CardInput>) => {
    setDraft(value => ({ ...value, ...patch, source: 'manual' }));
    setPreview(null); setChoices([]);
  };
  const panel = { backgroundColor: colors.surface, borderColor: colors.border };
  const text = { color: colors.textPrimary };
  const secondary = { color: colors.textSecondary };
  const button = (title: string, action: () => void, testID: string, primary = false, disabled = !!busy) => (
    <Pressable key={testID} onPress={action} disabled={disabled} accessibilityRole="button" accessibilityState={{ disabled }} testID={testID}
      style={({ pressed }) => [s.button, panel, primary && { backgroundColor: colors.accent }, (pressed || disabled) && { opacity: 0.5 }]}>
      <Text style={[s.buttonText, primary ? { color: colors.onAccent } : text]}>{title}</Text>
    </Pressable>
  );
  const ready = !!draft.code && choices.length === 0;
  return <View style={[s.panel, panel]} testID="wallet-editor">
    <Text style={[s.heading, text]}>{initial.revision ? 'La tua tessera' : 'Aggiungi una tessera'}</Text>
    <Text style={[s.body, secondary]}>Carica una foto o uno screenshot: ORA legge il numero e riconosce il formato da sola.</Text>
    <View style={s.row}>
      {Platform.OS === 'web' ? button('Scatta foto', () => { void importPhoto(true); }, 'wallet-camera') : null}
      {button('Carica foto', () => { void importPhoto(false); }, 'wallet-import', true)}
    </View>
    {busy === 'read' ? <View style={s.row} accessibilityLiveRegion="polite"><ActivityIndicator color={colors.accent} /><Text style={[s.body, text]}>Sto leggendo la tessera…</Text></View> : null}
    {error ? <Text accessibilityRole="alert" style={[s.body, text]} testID="wallet-import-error">{error}</Text> : null}
    {choices.length ? <View style={s.stack} testID="wallet-scan-choices">
      <Text style={[s.body, text]}>Nella foto ci sono codici diversi. Tocca quello della tessera che vuoi salvare.</Text>
      {choices.map((candidate, index) => <Pressable key={`${candidate.format}:${candidate.code}`} onPress={() => choose(candidate)} disabled={!!busy}
        accessibilityRole="button" accessibilityLabel={`Scegli codice ${index + 1}`} testID={`wallet-candidate-${index}`} style={[s.choice, panel]}>
        {safePreview(candidate.image) ? <View style={s.codeBox}><Image source={{ uri: safePreview(candidate.image)! }} style={s.choiceImage} resizeMode="contain" accessibilityLabel={`Anteprima codice ${index + 1}`} /></View> : null}
        <Text style={[s.body, text]}>{candidate.code}</Text>
      </Pressable>)}
    </View> : null}
    {ready && !manual ? <View style={s.stack} testID="wallet-import-ready">
      <Text style={[s.heading, text]}>{initial.revision && draft.source !== 'image' ? 'Codice salvato' : draft.source === 'image' ? 'Codice acquisito' : 'Codice pronto'}</Text>
      <View style={s.codeBox}>
        {preview ? <Image source={{ uri: preview }} style={[s.preview, draft.format === 'QR_CODE' && { height: 220 }]} resizeMode="contain" accessibilityLabel="Anteprima codice letto" testID="wallet-import-preview" /> : null}
        <Text selectable style={s.codeText} testID="wallet-read-code">{draft.code}</Text>
      </View>
      <Text style={[s.small, secondary]}>Numero e formato già compilati. Non devi trascrivere il codice.</Text>
    </View> : null}
    <Text style={[s.label, text]}>Nome della tessera (facoltativo)</Text>
    <TextInput value={draft.name} onChangeText={name => setDraft(value => ({ ...value, name }))} maxLength={80} editable={!busy}
      placeholder="Es. Conad — puoi aggiungerlo anche dopo" placeholderTextColor={colors.textTertiary} style={[s.input, panel, text]}
      accessibilityLabel="Nome tessera" testID="wallet-name" />
    {manual ? <View style={s.stack} testID="wallet-manual-fields">
      <Text style={[s.label, text]}>Formato del codice originale</Text>
      <View style={s.row}>{FORMATS.map(format => <Pressable key={format} disabled={!!busy} onPress={() => changeManual({ format })}
        accessibilityRole="radio" accessibilityState={{ checked: draft.format === format }} style={[s.chip, panel, draft.format === format && { borderColor: colors.accent, borderWidth: 2 }]}>
        <Text style={text}>{format.replace('_', ' ')}</Text>
      </Pressable>)}</View>
      <Text style={[s.small, secondary]}>Il formato non si può dedurre con certezza dal solo numero. Carica la foto per riconoscerlo automaticamente.</Text>
      <TextInput value={draft.code} onChangeText={code => changeManual({ code })} maxLength={512} editable={!busy} autoCapitalize="none" autoCorrect={false}
        accessibilityLabel="Codice tessera" testID="wallet-code" style={[s.input, panel, text]} />
    </View> : null}
    {button(manual ? 'Nascondi dettagli tecnici' : ready ? 'Correggi codice a mano' : 'Inserisci codice a mano', () => setManual(value => !value), 'wallet-manual')}
    <Text style={[s.small, secondary]}>Salvando aggiungi una tessera fedeltà a codice fisso. Non carte di pagamento o codici che cambiano. La foto non viene conservata dal server né inviata a modelli AI.</Text>
    <View style={s.row}>
      {button(busy === 'save' ? 'Salvataggio…' : 'Salva tessera', () => { void save(); }, 'wallet-save', true, !!busy || !ready)}
      {button('Annulla', onCancel, 'wallet-cancel')}
    </View>
  </View>;
}
const s = StyleSheet.create({
  panel: { padding: 20, borderWidth: 1, borderRadius: tokens.radius.lg, gap: 16 },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: 12, alignItems: 'center' },
  stack: { gap: 12 }, heading: { fontSize: 21, fontWeight: '600' }, body: { fontSize: 15, lineHeight: 22 },
  small: { fontSize: 13, lineHeight: 20 }, label: { fontSize: 14, fontWeight: '600' },
  button: { minHeight: 48, paddingHorizontal: 16, paddingVertical: 12, borderRadius: tokens.radius.md, borderWidth: 1, justifyContent: 'center' },
  buttonText: { fontSize: 15, fontWeight: '600' }, input: { minHeight: 48, padding: 13, fontSize: 16, borderWidth: 1, borderRadius: tokens.radius.md },
  chip: { minHeight: 44, padding: 12, borderWidth: 1, borderRadius: 10 },
  codeBox: { backgroundColor: '#fff', borderRadius: 12, padding: 16, gap: 10 },
  codeText: { color: '#000', fontSize: 19, textAlign: 'center' }, preview: { width: '100%', height: 130 },
  choice: { padding: 12, gap: 8, borderRadius: 12, borderWidth: 1 }, choiceImage: { width: '100%', height: 90 },
});
