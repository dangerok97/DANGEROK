/**
 * Adding a place, and correcting one. The same editor for both.
 *
 *     ADDRESS != LOCATION
 *
 * Three ways in, because people know where things are in three different ways:
 * they are standing in it, they can name the street, or they can only point at
 * it. None of the three is the "real" one, so none of them is the only one —
 * but they are not equals on the screen either: being here is one tap, an
 * address is typing, and the map is for everything with no address at all.
 *
 * Whatever route they take, the map has the last word. Google's pin lands on
 * the street and the entrance is round the back; if somebody moves the map,
 * that is the point that gets saved and `map_selection` records why.
 *
 * The same component does "Modifica posizione" from the place detail. A place
 * corrected six months later goes through exactly the path that created it,
 * which is the only way the two stay consistent.
 */
import * as React from 'react';
import {
  ActivityIndicator,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { api, PlaceSuggestion } from '@/src/api/client';
import { MapPicker, MapPoint } from '@/src/components/vita/MapPicker';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';

export type LocationSource =
  | 'current_position'
  | 'google_place'
  | 'map_selection'
  | 'name_only';

export type EditorResult = {
  label: string;
  latitude?: number;
  longitude?: number;
  address?: string;
  locality?: string;
  google_place_id?: string;
  location_source: LocationSource;
  currently_here: boolean;
};

type Props = {
  /** Editing an existing place: the name is fixed and only the point moves. */
  mode?: 'create' | 'relocate';
  initialLabel?: string;
  initialPoint?: MapPoint | null;
  onCancel: () => void;
  onSave: (result: EditorResult) => Promise<void>;
  compact?: boolean;
};

type Step = 'choose' | 'address' | 'map';

/** Somewhere to open the map when nothing else is known. Never presented as a fact. */
const NEUTRAL_FALLBACK: MapPoint = { latitude: 41.9028, longitude: 12.4964 };

export function PlaceEditor({
  mode = 'create',
  initialLabel = '',
  initialPoint = null,
  onCancel,
  onSave,
  compact,
}: Props) {
  const { colors } = useTheme();
  const [label, setLabel] = React.useState(initialLabel);
  const [step, setStep] = React.useState<Step>(mode === 'relocate' ? 'map' : 'choose');
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  // What has been chosen so far. `point` is the answer; the rest describes it.
  const [point, setPoint] = React.useState<MapPoint | null>(initialPoint);
  const [address, setAddress] = React.useState('');
  const [locality, setLocality] = React.useState('');
  const [placeId, setPlaceId] = React.useState('');
  const [source, setSource] = React.useState<LocationSource>('name_only');
  const [fromCurrentPosition, setFromCurrentPosition] = React.useState(false);
  // True once the map has settled somewhere other than where it opened.
  const [movedByHand, setMovedByHand] = React.useState(false);

  const [query, setQuery] = React.useState('');
  const [suggestions, setSuggestions] = React.useState<PlaceSuggestion[]>([]);
  const [searching, setSearching] = React.useState(false);

  /**
   * One token for a whole search: every keystroke plus the detail call that
   * ends it are billed as a single lookup instead of eight.
   */
  const sessionToken = React.useRef(newToken());
  const openedAt = React.useRef<MapPoint | null>(initialPoint);

  /* --- autocomplete ---------------------------------------------------- */
  React.useEffect(() => {
    const typed = query.trim();
    if (step !== 'address' || typed.length < 3) {
      setSuggestions([]);
      return;
    }
    let cancelled = false;
    // Debounce: a request per keystroke is billed per keystroke, and nobody
    // reads suggestions that change faster than they type.
    const timer = setTimeout(async () => {
      setSearching(true);
      try {
        const res = await api.placesSuggest(typed, sessionToken.current);
        if (!cancelled) setSuggestions(res.suggestions ?? []);
      } catch {
        if (!cancelled) setSuggestions([]);
      } finally {
        if (!cancelled) setSearching(false);
      }
    }, 350);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [query, step]);

  const pickSuggestion = React.useCallback(async (suggestion: PlaceSuggestion) => {
    if (!suggestion.place_id) return;
    setBusy(true);
    setError(null);
    try {
      const resolved = await api.placesResolve(suggestion.place_id, sessionToken.current);
      // The token is spent: the next search is a new one.
      sessionToken.current = newToken();
      const next = { latitude: resolved.latitude, longitude: resolved.longitude };
      setPoint(next);
      openedAt.current = next;
      setMovedByHand(false);
      setAddress(resolved.address ?? suggestion.text ?? '');
      setLocality(resolved.locality ?? '');
      setPlaceId(resolved.place_id);
      setSource('google_place');
      setFromCurrentPosition(false);
      setSuggestions([]);
      setQuery(resolved.address ?? '');
    } catch {
      setError('Non riesco a recuperare questo indirizzo. Riprova o scegli sulla mappa.');
    } finally {
      setBusy(false);
    }
  }, []);

  /* --- current position ------------------------------------------------ */
  const useCurrentPosition = React.useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const { requestForegroundPosition } = await import('@/src/location/foregroundGeo');
      const fix = await requestForegroundPosition({ maximumAgeMs: 0 });
      if (!fix.ok) {
        setError(
          fix.reason === 'denied'
            ? 'Senza il permesso di posizione non posso sapere dove sei. Puoi cercare l’indirizzo o scegliere sulla mappa.'
            : 'Non riesco a leggere la posizione adesso. Puoi cercare l’indirizzo o scegliere sulla mappa.',
        );
        return;
      }
      const next = { latitude: fix.latitude, longitude: fix.longitude };
      setPoint(next);
      openedAt.current = next;
      setMovedByHand(false);
      setAddress('');
      setLocality('');
      setPlaceId('');
      setSource('current_position');
      setFromCurrentPosition(true);
      setStep('map');
    } finally {
      setBusy(false);
    }
  }, []);

  /* --- the map has the last word --------------------------------------- */
  const onPointChange = React.useCallback((next: MapPoint) => {
    setPoint(next);
    const opened = openedAt.current;
    const moved =
      !opened ||
      Math.abs(opened.latitude - next.latitude) > 1e-6 ||
      Math.abs(opened.longitude - next.longitude) > 1e-6;
    if (moved) {
      setMovedByHand(true);
      // Their point beats the one that was proposed. The address stays: it is
      // still what this place is called, it is just not where it is.
      setSource('map_selection');
      setFromCurrentPosition(false);
    }
  }, []);

  const save = React.useCallback(
    async (nameOnly: boolean) => {
      const name = label.trim();
      if (!name || busy) return;
      setBusy(true);
      setError(null);
      try {
        await onSave({
          label: name,
          ...(nameOnly || !point
            ? { location_source: 'name_only' as LocationSource }
            : {
                latitude: point.latitude,
                longitude: point.longitude,
                address: address || undefined,
                locality: locality || undefined,
                google_place_id: placeId || undefined,
                location_source: source,
              }),
          location_source: nameOnly || !point ? 'name_only' : source,
          // A statement, not a sensor reading — and only when the point is
          // still the one the device gave.
          currently_here: !nameOnly && fromCurrentPosition && !movedByHand,
        });
      } catch {
        setError('Non riesco a salvare in questo momento.');
      } finally {
        setBusy(false);
      }
    },
    [label, busy, point, address, locality, placeId, source, fromCurrentPosition, movedByHand, onSave],
  );

  const canSavePoint = Boolean(label.trim()) && Boolean(point);

  return (
    <View style={[styles.card, { borderColor: colors.border }]} testID="place-editor">
      {mode === 'create' ? (
        <View style={styles.field}>
          <Text style={[styles.fieldLabel, { color: colors.textTertiary }]}>
            Nome del luogo
          </Text>
          <TextInput
            value={label}
            onChangeText={setLabel}
            placeholder="Casa"
            placeholderTextColor={colors.textTertiary}
            style={[styles.input, { color: colors.textPrimary, borderColor: colors.border }]}
            testID="editor-name"
            editable={!busy}
          />
        </View>
      ) : null}

      {step === 'choose' ? (
        <View style={styles.field}>
          <Text style={[styles.fieldLabel, { color: colors.textTertiary }]}>Posizione</Text>
          {/* Not three equal buttons: being here is one tap, an address is
              typing, the map is for what has no address. */}
          <Pressable
            onPress={() => void useCurrentPosition()}
            disabled={busy || !label.trim()}
            style={[
              styles.primaryChoice,
              { backgroundColor: colors.accent, opacity: busy || !label.trim() ? 0.4 : 1 },
            ]}
            testID="editor-here"
          >
            <Ionicons name="navigate-outline" size={16} color={colors.onAccent} />
            <Text style={[styles.primaryChoiceText, { color: colors.onAccent }]}>
              Sono qui adesso
            </Text>
          </Pressable>
          <View style={[styles.secondaryRow, compact && styles.secondaryStacked]}>
            <Choice
              icon="search-outline"
              label="Inserisci indirizzo"
              onPress={() => setStep('address')}
              disabled={busy || !label.trim()}
              colors={colors}
              testID="editor-address-mode"
            />
            <Choice
              icon="map-outline"
              label="Scegli sulla mappa"
              onPress={() => {
                openedAt.current = null;
                setStep('map');
              }}
              disabled={busy || !label.trim()}
              colors={colors}
              testID="editor-map-mode"
            />
          </View>
          <Pressable
            onPress={() => void save(true)}
            disabled={busy || !label.trim()}
            style={styles.quiet}
            testID="editor-name-only"
          >
            <Text style={[styles.quietText, { color: colors.textTertiary }]}>
              Salva solo il nome
            </Text>
          </Pressable>
        </View>
      ) : null}

      {step === 'address' ? (
        <View style={styles.field}>
          <Text style={[styles.fieldLabel, { color: colors.textTertiary }]}>Indirizzo</Text>
          <TextInput
            value={query}
            onChangeText={setQuery}
            placeholder="Inizia a scrivere…"
            placeholderTextColor={colors.textTertiary}
            style={[styles.input, { color: colors.textPrimary, borderColor: colors.border }]}
            testID="editor-address-input"
            editable={!busy}
            autoCorrect={false}
          />
          {searching ? (
            <ActivityIndicator color={colors.textTertiary} style={styles.searching} />
          ) : null}
          {suggestions.length ? (
            <View style={[styles.suggestions, { borderColor: colors.divider }]}>
              {suggestions.map((s) => (
                <Pressable
                  key={s.place_id ?? s.text}
                  onPress={() => void pickSuggestion(s)}
                  style={[styles.suggestion, { borderColor: colors.divider }]}
                  testID={`editor-suggestion-${s.place_id}`}
                  accessibilityRole="button"
                >
                  <Text style={[styles.suggestionMain, { color: colors.textPrimary }]} numberOfLines={1}>
                    {s.primary ?? s.text}
                  </Text>
                  {s.secondary ? (
                    <Text style={[styles.suggestionMeta, { color: colors.textTertiary }]} numberOfLines={1}>
                      {s.secondary}
                    </Text>
                  ) : null}
                </Pressable>
              ))}
            </View>
          ) : null}
        </View>
      ) : null}

      {(step === 'map' || (step === 'address' && point)) ? (
        <View style={styles.field}>
          <MapPicker
            center={point ?? openedAt.current ?? NEUTRAL_FALLBACK}
            onPointChange={onPointChange}
            height={compact ? 220 : 280}
            testID="editor-map"
          />
          <Text style={[styles.fieldLabel, { color: colors.textTertiary }]}>
            Punto selezionato
          </Text>
          {/* Never coordinates. A person cannot check a decimal, and the map
              above is the check. */}
          <Text style={[styles.selected, { color: colors.textSecondary }]} testID="editor-selected">
            {address
              ? movedByHand
                ? `${address} — punto spostato a mano`
                : address
              : point
                ? movedByHand || step === 'map'
                  ? 'Il punto che hai scelto sulla mappa'
                  : 'La tua posizione attuale'
                : 'Muovi la mappa per scegliere il punto'}
          </Text>
        </View>
      ) : null}

      {error ? (
        <Text style={[styles.error, { color: colors.warning }]} testID="editor-error">
          {error}
        </Text>
      ) : null}

      <View style={[styles.actions, compact && styles.secondaryStacked]}>
        <Pressable onPress={onCancel} style={styles.quiet} testID="editor-cancel">
          <Text style={[styles.quietText, { color: colors.textTertiary }]}>Annulla</Text>
        </Pressable>
        {step !== 'choose' ? (
          <Pressable
            onPress={() => void save(false)}
            disabled={!canSavePoint || busy}
            style={[
              styles.primaryChoice,
              { backgroundColor: colors.accent, opacity: !canSavePoint || busy ? 0.4 : 1 },
            ]}
            testID="editor-confirm"
          >
            <Text style={[styles.primaryChoiceText, { color: colors.onAccent }]}>
              {mode === 'relocate' ? 'Conferma questo punto' : 'Conferma e salva'}
            </Text>
          </Pressable>
        ) : null}
      </View>
    </View>
  );
}

function Choice({
  icon,
  label,
  onPress,
  disabled,
  colors,
  testID,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  onPress: () => void;
  disabled?: boolean;
  colors: ReturnType<typeof useTheme>['colors'];
  testID?: string;
}) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      style={[
        styles.choice,
        { borderColor: colors.border, opacity: disabled ? 0.4 : 1 },
      ]}
      testID={testID}
    >
      <Ionicons name={icon} size={15} color={colors.textSecondary} />
      <Text style={[styles.choiceText, { color: colors.textPrimary }]}>{label}</Text>
    </Pressable>
  );
}

function newToken(): string {
  return `pst_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;
}

const styles = StyleSheet.create({
  card: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.md,
    padding: tokens.spacing.md,
    gap: tokens.spacing.md,
  },
  field: { gap: tokens.spacing.sm },
  fieldLabel: { fontSize: 11, fontWeight: '600', letterSpacing: 0.5 },
  input: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.sm,
    paddingHorizontal: tokens.spacing.md,
    paddingVertical: 10,
    fontSize: 14,
    minHeight: tokens.touch.min,
  },
  primaryChoice: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    borderRadius: tokens.radius.md,
    paddingHorizontal: tokens.spacing.lg,
    paddingVertical: 11,
    minHeight: tokens.touch.min,
  },
  primaryChoiceText: { fontSize: 13, fontWeight: '600' },
  secondaryRow: { flexDirection: 'row', gap: tokens.spacing.md },
  secondaryStacked: { flexDirection: 'column' },
  choice: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.md,
    paddingHorizontal: tokens.spacing.md,
    paddingVertical: 10,
    minHeight: tokens.touch.min,
  },
  choiceText: { fontSize: 13, fontWeight: '500' },
  quiet: { alignItems: 'center', justifyContent: 'center', paddingVertical: 10, minHeight: 40 },
  quietText: { fontSize: 12 },
  searching: { alignSelf: 'flex-start' },
  suggestions: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.sm,
  },
  suggestion: {
    borderBottomWidth: StyleSheet.hairlineWidth,
    paddingVertical: 10,
    paddingHorizontal: tokens.spacing.sm,
    gap: 1,
    minHeight: tokens.touch.min,
    justifyContent: 'center',
  },
  suggestionMain: { fontSize: 14, fontWeight: '500' },
  suggestionMeta: { fontSize: 12 },
  selected: { fontSize: 13, lineHeight: 18 },
  error: { fontSize: 12, lineHeight: 17 },
  actions: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: tokens.spacing.md,
  },
});
