/**
 * Vita → Luoghi.
 *
 * What ORA knows about where someone's life happens. Not a map, and not a
 * permission screen: permission belongs to Profilo, because what ORA *may
 * observe* and what ORA *knows* are different questions and answering them in
 * one place blurs both.
 *
 * A row is a name, a locality and a state. The one row that behaves
 * differently is a place ORA has noticed but nobody has named — it asks,
 * rather than announcing what it thinks the place is.
 */
import * as React from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';

import { api, LifePlace, PlaceCandidate, PlacePresence, PlacesResponse } from '@/src/api/client';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';

type Props = {
  compact?: boolean;
  /** Opens the conversation. No text is passed: the person says what they want. */
  onOpenOra?: () => void;
};

type Status = 'loading' | 'ready' | 'error';

const ROLE_ICON: Record<string, keyof typeof Ionicons.glyphMap> = {
  home: 'home-outline',
  work: 'briefcase-outline',
  other: 'location-outline',
};

/**
 * What to say about being here, in the tense a person would use.
 *
 * `pending_enter` reads as absent on purpose: ninety seconds inside a circle
 * is not having arrived, and "sei qui" said too early is the single-sample
 * mistake wearing better clothes.
 */
function hours(seconds?: number | null): string | null {
  if (!seconds || seconds < 60) return null;
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  if (h && m) return `${h}h ${m}m`;
  if (h) return `${h}h`;
  return `${m}m`;
}

/**
 * One line under a place, and only one.
 *
 * Being here beats having been here, which beats how often. A place that
 * needed three lines to be understood would be a report, and this is a list.
 */
function secondaryLabel(place: LifePlace): string | null {
  if (place.presence?.present) {
    const since = hours(place.presence.current_session_seconds);
    return since ? `Sei qui da ${since}` : 'Sei qui';
  }
  // Somewhere they went several times this week is better described by how
  // often than by when it last happened; somewhere they went once is the
  // opposite. Neither is a statistic — both are the shortest true sentence.
  const week = place.this_week;
  if (week && week.visits >= 2) {
    return `${week.visits} visite questa settimana`;
  }
  return presenceLabel(place.presence);
}

function presenceLabel(presence?: PlacePresence | null): string | null {
  if (!presence) return null;
  if (presence.present) return 'Sei qui';
  const left = presence.last_exited_at;
  if (!left) return null;
  const when = new Date(left);
  if (Number.isNaN(when.getTime())) return null;
  const today = new Date();
  const sameDay = when.toDateString() === today.toDateString();
  const time = when.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
  const day = when.toLocaleDateString('it-IT', { day: 'numeric', month: 'short' });
  return sameDay ? `Ultima presenza: oggi, ${time}` : `Ultima presenza: ${day}, ${time}`;
}

/** The words a person reads for where a place came from. Never an id. */
function originLabel(place: LifePlace): string | null {
  switch (place.source) {
    case 'current_position':
      return 'Fonte: Posizione attuale';
    case 'confirmed_candidate':
      return 'Riconosciuto da spostamenti';
    case 'life_profile':
      return 'Fonte: Impostazioni';
    default:
      return null;
  }
}

export function PlacesSection({ compact, onOpenOra }: Props) {
  const { colors } = useTheme();
  const router = useRouter();
  const [status, setStatus] = React.useState<Status>('loading');
  const [data, setData] = React.useState<PlacesResponse | null>(null);
  const [adding, setAdding] = React.useState(false);
  const [draft, setDraft] = React.useState('');
  const [answering, setAnswering] = React.useState<string | null>(null);
  const [answer, setAnswer] = React.useState('');
  const [busy, setBusy] = React.useState(false);

  const load = React.useCallback(async () => {
    try {
      setData(await api.placesList());
      setStatus('ready');
    } catch {
      setStatus('error');
    }
  }, []);

  React.useEffect(() => {
    void load();
  }, [load]);

  const addPlace = React.useCallback(
    async (useCurrentPosition: boolean) => {
      const label = draft.trim();
      if (!label || busy) return;
      setBusy(true);
      try {
        let coords: { latitude: number; longitude: number; accuracy_meters?: number } | null = null;
        if (useCurrentPosition) {
          const { requestForegroundPosition } = await import('@/src/location/foregroundGeo');
          const fix = await requestForegroundPosition({ maximumAgeMs: 0 });
          // A place saved without the position the person asked for would be a
          // different place than the one they meant, so this stops instead.
          if (!fix.ok) {
            setBusy(false);
            return;
          }
          coords = {
            latitude: fix.latitude,
            longitude: fix.longitude,
            accuracy_meters: fix.accuracyMeters,
          };
        }
        await api.placesCreate({
          label,
          ...(coords ?? {}),
          source: useCurrentPosition ? 'current_position' : 'user_stated',
        });
        setDraft('');
        setAdding(false);
        await load();
      } finally {
        setBusy(false);
      }
    },
    [draft, busy, load],
  );

  const submitAnswer = React.useCallback(
    async (candidateId: string) => {
      const said = answer.trim();
      if (!said || busy) return;
      setBusy(true);
      try {
        await api.placesAnswerCandidate(candidateId, said);
        setAnswer('');
        setAnswering(null);
        await load();
      } finally {
        setBusy(false);
      }
    },
    [answer, busy, load],
  );

  /* --- G. loading ------------------------------------------------------ */
  if (status === 'loading') {
    return (
      <Card testID="places-loading">
        <View style={styles.centred}>
          <ActivityIndicator color={colors.textTertiary} />
        </View>
      </Card>
    );
  }

  /* --- F. errore ------------------------------------------------------- */
  if (status === 'error' || !data) {
    return (
      <Card testID="places-error">
        <Header colors={colors} />
        <Text style={[styles.body, { color: colors.textSecondary }]}>
          Non riesco a leggere i tuoi luoghi in questo momento.
        </Text>
        <Pressable
          onPress={() => void load()}
          style={[styles.secondaryButton, { borderColor: colors.border }]}
          testID="places-retry"
        >
          <Text style={[styles.secondaryButtonText, { color: colors.textPrimary }]}>Riprova</Text>
        </Pressable>
      </Card>
    );
  }

  const { places, candidates, permission } = data;
  const locationOff = permission.preference === 'off' || permission.state === 'denied';

  return (
    <Card testID="places-section">
      <Header colors={colors} onAdd={() => setAdding((v) => !v)} adding={adding} />

      {/* --- A. posizione non autorizzata ------------------------------- */}
      {locationOff ? (
        <View
          style={[styles.notice, { backgroundColor: colors.surface, borderColor: colors.border }]}
          testID="places-permission-off"
        >
          <Ionicons name="location-outline" size={16} color={colors.textTertiary} />
          <Text style={[styles.noticeText, { color: colors.textSecondary }]}>
            La posizione è disattivata. Puoi comunque aggiungere i tuoi luoghi a mano, oppure
            attivarla da Profilo → Privacy e permessi.
          </Text>
        </View>
      ) : null}

      {adding ? (
        <View style={[styles.adder, { borderColor: colors.border }]} testID="places-add-form">
          <TextInput
            value={draft}
            onChangeText={setDraft}
            placeholder="Come si chiama questo posto?"
            placeholderTextColor={colors.textTertiary}
            style={[styles.input, { color: colors.textPrimary, borderColor: colors.border }]}
            testID="places-add-input"
            editable={!busy}
          />
          <View style={styles.adderActions}>
            <Pressable
              onPress={() => void addPlace(true)}
              disabled={!draft.trim() || busy || locationOff}
              style={[
                styles.primaryButton,
                {
                  backgroundColor: colors.accent,
                  opacity: !draft.trim() || busy || locationOff ? 0.4 : 1,
                },
              ]}
              testID="places-add-here"
            >
              <Text style={[styles.primaryButtonText, { color: colors.onAccent }]}>
                Sono qui adesso
              </Text>
            </Pressable>
            <Pressable
              onPress={() => void addPlace(false)}
              disabled={!draft.trim() || busy}
              style={[
                styles.secondaryButton,
                { borderColor: colors.border, opacity: !draft.trim() || busy ? 0.4 : 1 },
              ]}
              testID="places-add-manual"
            >
              <Text style={[styles.secondaryButtonText, { color: colors.textPrimary }]}>
                Salva solo il nome
              </Text>
            </Pressable>
          </View>
        </View>
      ) : null}

      {/* --- B. nessun luogo -------------------------------------------- */}
      {!places.length && !candidates.length ? (
        <Text style={[styles.body, { color: colors.textSecondary }]} testID="places-empty">
          Non conosco ancora nessuno dei tuoi luoghi. Casa, lavoro, o qualsiasi posto che conta
          nella tua giornata.
        </Text>
      ) : null}

      {/* --- C/D. luoghi confermati ------------------------------------- */}
      {places.map((place) => (
        <PlaceRow
          key={place.id}
          place={place}
          colors={colors}
          compact={compact}
          onOpen={() => router.push(`/place/${place.id}` as never)}
        />
      ))}

      {/* --- E. un luogo da confermare ---------------------------------- */}
      {candidates.map((candidate) => (
        <CandidateRow
          key={candidate.id}
          candidate={candidate}
          colors={colors}
          compact={compact}
          open={answering === candidate.id}
          answer={answer}
          busy={busy}
          onOpen={() => {
            setAnswering(answering === candidate.id ? null : candidate.id);
            setAnswer('');
          }}
          onChange={setAnswer}
          onSubmit={() => void submitAnswer(candidate.id)}
        />
      ))}

      {!locationOff ? (
        <Pressable
          onPress={() => onOpenOra?.()}
          style={[styles.banner, { backgroundColor: colors.surface, borderColor: colors.border }]}
          testID="places-banner"
        >
          <Ionicons name="sparkles-outline" size={16} color={colors.accent} />
          <View style={styles.bannerBody}>
            <Text style={[styles.bannerTitle, { color: colors.textPrimary }]}>
              ORA può suggerire luoghi che frequenti spesso
            </Text>
            <Text style={[styles.bannerText, { color: colors.textTertiary }]}>
              Basandosi sui tuoi spostamenti, calendario e attività.
            </Text>
          </View>
          <Ionicons name="chevron-forward" size={16} color={colors.textTertiary} />
        </Pressable>
      ) : null}
    </Card>
  );
}

/* -------------------------------------------------------------------------- */

function Header({
  colors,
  onAdd,
  adding,
}: {
  colors: ReturnType<typeof useTheme>['colors'];
  onAdd?: () => void;
  adding?: boolean;
}) {
  return (
    <View style={styles.header}>
      <View style={styles.headerIcon}>
        <Ionicons name="location-outline" size={18} color={colors.textPrimary} />
      </View>
      <View style={styles.headerBody}>
        <Text style={[styles.title, { color: colors.textPrimary }]}>Luoghi</Text>
        <Text style={[styles.subtitle, { color: colors.textTertiary }]}>
          ORA riconosce e organizza i luoghi importanti della tua routine.
        </Text>
      </View>
      {onAdd ? (
        <Pressable
          onPress={onAdd}
          style={[styles.addButton, { borderColor: colors.border }]}
          testID="places-add-toggle"
          accessibilityLabel="Aggiungi luogo"
        >
          <Ionicons
            name={adding ? 'close' : 'add'}
            size={14}
            color={colors.textPrimary}
          />
          <Text style={[styles.addButtonText, { color: colors.textPrimary }]}>
            {adding ? 'Annulla' : 'Aggiungi luogo'}
          </Text>
        </Pressable>
      ) : null}
    </View>
  );
}

function PlaceRow({
  place,
  colors,
  compact,
  onOpen,
}: {
  place: LifePlace;
  colors: ReturnType<typeof useTheme>['colors'];
  compact?: boolean;
  onOpen: () => void;
}) {
  const origin = originLabel(place);
  const presenceText = secondaryLabel(place);
  const here = Boolean(place.presence?.present);
  return (
    <Pressable
      onPress={onOpen}
      style={[styles.row, { borderColor: colors.divider }]}
      testID={`place-${place.id}`}
      accessibilityLabel={`Apri ${place.label}`}
    >
      <Ionicons
        name={ROLE_ICON[place.role] ?? ROLE_ICON.other}
        size={16}
        color={colors.textSecondary}
        style={styles.rowIcon}
      />
      <View style={styles.rowBody}>
        <View style={styles.rowTitleLine}>
          <Text style={[styles.rowTitle, { color: colors.textPrimary }]} numberOfLines={1}>
            {place.label}
          </Text>
          {here ? (
            <View style={[styles.hereDot, { backgroundColor: colors.success }]} />
          ) : null}
        </View>
        {place.locality || place.address ? (
          <Text style={[styles.rowMeta, { color: colors.textTertiary }]} numberOfLines={1}>
            {place.locality || place.address}
          </Text>
        ) : null}
        {presenceText ? (
          <Text
            style={[
              styles.rowMeta,
              { color: here ? colors.success : colors.textTertiary },
            ]}
            numberOfLines={1}
          >
            {presenceText}
          </Text>
        ) : null}
        {/* On a narrow screen the provenance goes under the name rather than
            into a column that would squeeze the name to nothing. */}
        {compact && origin ? (
          <Text style={[styles.rowMeta, { color: colors.textTertiary }]} numberOfLines={1}>
            {origin}
          </Text>
        ) : null}
      </View>
      {!compact && origin ? (
        <Text style={[styles.rowOrigin, { color: colors.textTertiary }]} numberOfLines={1}>
          {origin}
        </Text>
      ) : null}
      <View style={[styles.badge, { backgroundColor: colors.successBg }]}>
        <Text style={[styles.badgeText, { color: colors.success }]}>Confermato</Text>
      </View>
      <Ionicons name="chevron-forward" size={16} color={colors.textTertiary} />
    </Pressable>
  );
}

function CandidateRow({
  candidate,
  colors,
  compact,
  open,
  answer,
  busy,
  onOpen,
  onChange,
  onSubmit,
}: {
  candidate: PlaceCandidate;
  colors: ReturnType<typeof useTheme>['colors'];
  compact?: boolean;
  open: boolean;
  answer: string;
  busy: boolean;
  onOpen: () => void;
  onChange: (v: string) => void;
  onSubmit: () => void;
}) {
  return (
    <View testID={`candidate-${candidate.id}`}>
      {/* On a narrow screen the badge and the button go under the text: a row
          that squeezes "Luogo frequente da confermare" into "Luogo freq..." has
          hidden the only sentence that explains why it is there. */}
      <View
        style={[
          styles.row,
          compact && styles.rowStacked,
          { borderColor: colors.divider },
        ]}
      >
        <View style={styles.rowLead}>
          <Ionicons
            name="help-circle-outline"
            size={16}
            color={colors.textTertiary}
            style={styles.rowIcon}
          />
          <View style={styles.rowBody}>
            {/* Deliberately not a guess. ORA noticed a place; it does not know
                what it is, and saying otherwise would be inventing a life. */}
            <Text style={[styles.rowTitle, { color: colors.textPrimary }]} numberOfLines={2}>
              Luogo frequente da confermare
            </Text>
            <Text style={[styles.rowMeta, { color: colors.textTertiary }]} numberOfLines={1}>
              {candidate.locality || candidate.address_hint || 'Riconosciuto da spostamenti'}
            </Text>
          </View>
        </View>
        <View style={[styles.rowTail, compact && styles.rowTailStacked]}>
          <View style={[styles.badge, { backgroundColor: colors.warningBg }]}>
            <Text style={[styles.badgeText, { color: colors.warning }]}>Da confermare</Text>
          </View>
          <Pressable
            onPress={onOpen}
            style={[styles.confirmButton, { borderColor: colors.border }]}
            testID={`candidate-open-${candidate.id}`}
          >
            <Text style={[styles.confirmButtonText, { color: colors.textPrimary }]}>Conferma</Text>
          </Pressable>
        </View>
      </View>
      {open ? (
        <View style={styles.candidateForm}>
          <Text style={[styles.rowMeta, { color: colors.textSecondary }]}>
            Che posto è? Chiamalo come lo chiami tu.
          </Text>
          <TextInput
            value={answer}
            onChangeText={onChange}
            placeholder="Es. la palestra, casa di mia madre…"
            placeholderTextColor={colors.textTertiary}
            style={[styles.input, { color: colors.textPrimary, borderColor: colors.border }]}
            testID={`candidate-input-${candidate.id}`}
            editable={!busy}
          />
          <Pressable
            onPress={onSubmit}
            disabled={!answer.trim() || busy}
            style={[
              styles.primaryButton,
              { backgroundColor: colors.accent, opacity: !answer.trim() || busy ? 0.4 : 1 },
            ]}
            testID={`candidate-submit-${candidate.id}`}
          >
            <Text style={[styles.primaryButtonText, { color: colors.onAccent }]}>Salva</Text>
          </Pressable>
        </View>
      ) : null}
    </View>
  );
}

function Card({ children, testID }: { children: React.ReactNode; testID?: string }) {
  const { colors } = useTheme();
  return (
    <View
      style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}
      testID={testID}
    >
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.lg,
    padding: tokens.spacing.lg,
    gap: tokens.spacing.md,
  },
  centred: { paddingVertical: tokens.spacing.lg, alignItems: 'center' },
  header: { flexDirection: 'row', alignItems: 'flex-start', gap: tokens.spacing.md },
  headerIcon: { paddingTop: 2 },
  headerBody: { flex: 1, gap: 2 },
  title: { fontSize: 17, fontWeight: '600' },
  subtitle: { fontSize: 13, lineHeight: 18 },
  body: { fontSize: 14, lineHeight: 20 },
  addButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.md,
    paddingHorizontal: tokens.spacing.md,
    paddingVertical: 8,
    minHeight: tokens.touch.min - 12,
  },
  addButtonText: { fontSize: 13, fontWeight: '500' },
  notice: {
    flexDirection: 'row',
    gap: tokens.spacing.md,
    alignItems: 'flex-start',
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.md,
    padding: tokens.spacing.md,
  },
  noticeText: { flex: 1, fontSize: 13, lineHeight: 18 },
  adder: {
    gap: tokens.spacing.md,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.md,
    padding: tokens.spacing.md,
  },
  adderActions: { flexDirection: 'row', flexWrap: 'wrap', gap: tokens.spacing.md },
  input: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.sm,
    paddingHorizontal: tokens.spacing.md,
    paddingVertical: 10,
    fontSize: 14,
    minHeight: tokens.touch.min,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: tokens.spacing.md,
    borderTopWidth: StyleSheet.hairlineWidth,
    paddingVertical: tokens.spacing.md,
    minHeight: tokens.touch.min,
  },
  rowStacked: { flexDirection: 'column', alignItems: 'stretch', gap: tokens.spacing.md },
  rowLead: { flexDirection: 'row', alignItems: 'center', gap: tokens.spacing.md, flex: 1, minWidth: 0 },
  rowTail: { flexDirection: 'row', alignItems: 'center', gap: tokens.spacing.md },
  rowTailStacked: { paddingLeft: 18 + tokens.spacing.md },
  rowIcon: { width: 18 },
  rowBody: { flex: 1, gap: 1, minWidth: 0 },
  rowTitleLine: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  hereDot: { width: 6, height: 6, borderRadius: 3 },
  rowTitle: { fontSize: 14, fontWeight: '500', flexShrink: 1 },
  rowMeta: { fontSize: 12, lineHeight: 16 },
  rowOrigin: { fontSize: 12, flexShrink: 1, maxWidth: 190 },
  rowAction: { padding: 4 },
  badge: { borderRadius: tokens.radius.sm, paddingHorizontal: 8, paddingVertical: 3 },
  badgeText: { fontSize: 11, fontWeight: '600' },
  confirmButton: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.md,
    paddingHorizontal: tokens.spacing.md,
    paddingVertical: 7,
  },
  confirmButtonText: { fontSize: 12, fontWeight: '500' },
  candidateForm: { gap: tokens.spacing.md, paddingBottom: tokens.spacing.md },
  primaryButton: {
    borderRadius: tokens.radius.md,
    paddingHorizontal: tokens.spacing.lg,
    paddingVertical: 10,
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: tokens.touch.min,
  },
  primaryButtonText: { fontSize: 13, fontWeight: '600' },
  secondaryButton: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.md,
    paddingHorizontal: tokens.spacing.lg,
    paddingVertical: 10,
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: tokens.touch.min,
  },
  secondaryButtonText: { fontSize: 13, fontWeight: '500' },
  banner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: tokens.spacing.md,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.md,
    padding: tokens.spacing.md,
  },
  bannerBody: { flex: 1, gap: 2 },
  bannerTitle: { fontSize: 13, fontWeight: '500' },
  bannerText: { fontSize: 12, lineHeight: 16 },
});
