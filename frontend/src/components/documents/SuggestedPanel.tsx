/**
 * Azioni suggerite — quello che conviene fare, dai documenti che ci sono.
 *
 * Niente di generato e niente di generico: ogni riga nasce da uno stato vero
 * di un documento vero (da verificare, lettura non riuscita, azioni aperte).
 * Se non c'è niente da suggerire, il pannello non compare.
 */
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { ora, oraType } from '@/src/theme/oraSurface';
import { Panel } from './LibraryParts';
import type { DocItem } from './libraryView';

type Suggerimento = { id: string; icon: any; title: string; body: string };

export function suggestionsFrom(items: DocItem[]): Suggerimento[] {
  const fuori: Suggerimento[] = [];
  for (const it of items) {
    if (fuori.length >= 3) break;
    if (it.status === 'needs_review') {
      fuori.push({
        id: it.id,
        icon: 'alert-circle-outline',
        title: `Verifica «${it.title}»`,
        body: 'ORA non è riuscita a leggerlo bene: serve una copia più chiara.',
      });
    } else if (it.status === 'failed') {
      fuori.push({
        id: it.id,
        icon: 'refresh-outline',
        title: `Riprova con «${it.title}»`,
        body: 'La lettura non è andata a buon fine.',
      });
    } else if ((it.open_actions || 0) > 0) {
      fuori.push({
        id: it.id,
        icon: 'sparkles-outline',
        title: `Azioni da «${it.title}»`,
        body: `${it.open_actions} cose che ORA può fare da questo documento.`,
      });
    }
  }
  return fuori;
}

export function SuggestedPanel({
  items,
  onOpen,
}: {
  items: DocItem[];
  onOpen: (id: string) => void;
}) {
  const righe = suggestionsFrom(items || []);
  if (!righe.length) return null;

  return (
    <Panel title="Azioni suggerite" testID="documents-suggested">
      {righe.map((r) => (
        <Pressable
          key={r.id}
          onPress={() => onOpen(r.id)}
          accessibilityRole="button"
          accessibilityLabel={r.title}
          style={({ pressed, hovered }: any) => [
            styles.row,
            hovered && { backgroundColor: ora.hover },
            pressed && { opacity: 0.7 },
          ]}
          testID={`documents-suggested-${r.id}`}
        >
          <Ionicons name={r.icon} size={18} color={ora.deep} style={{ marginTop: 2 }} />
          <View style={{ flex: 1 }}>
            <Text style={[oraType.small, { color: ora.ink, fontWeight: '600' }]} numberOfLines={2}>
              {r.title}
            </Text>
            <Text style={[oraType.small, { color: ora.ink2 }]} numberOfLines={2}>
              {r.body}
            </Text>
          </View>
        </Pressable>
      ))}
    </Panel>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    gap: 10,
    alignItems: 'flex-start',
    paddingVertical: 8,
    paddingHorizontal: 4,
    borderRadius: 10,
  },
});
