import { useState } from 'react';
import { Pressable, Text, TextInput, View } from 'react-native';

import { api } from '@/src/api/client';
import type { Aggiornamento } from './aggiornamenti';
import { ora, oraType } from '@/src/theme/oraSurface';
import { humanizeError } from '@/src/utils/errors';

/**
 * Temporary Situation feedback is a statement about the world, never an
 * invented AI completion. A changed state resumes the existing autonomous
 * observation pipeline. Completion and stop are different choices.
 */
export function SituationFeedback({
  item,
  onUpdated,
}: {
  item: Aggiornamento;
  onUpdated: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [description, setDescription] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  if (item.genere !== 'situazione' || !item.situazione_id || !item.situazione_revisione) {
    return null;
  }

  const perform = async (action: 'changed' | 'resolved' | 'stop_monitoring') => {
    if (busy || (action === 'changed' && description.trim().length < 5)) return;
    setBusy(true);
    setError('');
    try {
      const result = await api.updateSituation(item.situazione_id!, {
        action,
        expected_revision: item.situazione_revisione!,
        description: action === 'changed' ? description.trim() : undefined,
      });
      if (!result.ok) throw new Error('Non riesco ad aggiornare la situazione.');
      setMessage(result.message);
      setEditing(false);
      setDescription('');
      onUpdated();
    } catch (cause) {
      setError(humanizeError(cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={{ gap: 12 }} testID="situation-feedback">
      <Text style={[oraType.section, { color: ora.ink }]}>È cambiato qualcosa?</Text>
      <Text style={[oraType.body, { color: ora.ink2 }]}>
        Dimmi soltanto che cosa è successo. ORA aggiornerà questa situazione,
        senza inventare un esito che non può osservare.
      </Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
        <Pressable
          accessibilityRole="button"
          disabled={busy}
          onPress={() => void perform('resolved')}
          testID="situation-done"
          style={{ backgroundColor: ora.cta, padding: 14, borderRadius: 12 }}
        >
          <Text style={{ color: '#fff', fontWeight: '600' }}>Ho concluso</Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          disabled={busy}
          onPress={() => setEditing((old) => !old)}
          testID="situation-changed"
          style={{ borderWidth: 1, borderColor: ora.cta, padding: 14, borderRadius: 12 }}
        >
          <Text style={{ color: ora.cta, fontWeight: '600' }}>È cambiata</Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          disabled={busy}
          onPress={() => void perform('stop_monitoring')}
          testID="situation-stop"
          style={{ padding: 14, borderRadius: 12 }}
        >
          <Text style={{ color: ora.ink3 }}>Non ricordarmelo più</Text>
        </Pressable>
      </View>
      {editing ? (
        <View style={{ gap: 8 }} testID="situation-change-description">
          <Text style={[oraType.body, { color: ora.ink }]}>
            Che cosa è cambiato? (es. l'hai spostato, hai modificato l'orario…)
          </Text>
          <TextInput
            multiline
            accessibilityLabel="Descrivi il nuovo stato della situazione"
            placeholder="Scrivi che cosa è successo…"
            value={description}
            onChangeText={setDescription}
            maxLength={400}
            style={{
              minHeight: 80, padding: 12, borderWidth: 1, borderRadius: 12,
              borderColor: ora.ink3, color: ora.ink,
            }}
          />
          <Pressable
            accessibilityRole="button"
            disabled={busy || description.trim().length < 5}
            onPress={() => void perform('changed')}
            testID="situation-save-change"
            style={{
              padding: 13, alignSelf: 'flex-start',
              backgroundColor: ora.cta, borderRadius: 12,
              opacity: description.trim().length < 5 ? 0.5 : 1,
            }}
          >
            <Text style={{ color: '#fff', fontWeight: '600' }}>
              Aggiorna e ricontrolla
            </Text>
          </Pressable>
        </View>
      ) : null}
      {message ? <Text accessibilityRole="status" style={{ color: ora.ink2 }}>{message}</Text> : null}
      {error ? <Text accessibilityRole="alert" style={{ color: ora.attention }}>{error}</Text> : null}
    </View>
  );
}
