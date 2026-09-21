/**
 * Agenda — quando succedono le cose.
 *
 *     «VEDI AGENDA» NON È «VEDI TUTTO».
 *
 * V3.21.3b: questo link portava alla «Situazione completa», cioè a una
 * panoramica dello stato della vita. Chi apre l'agenda non sta chiedendo come
 * sta andando: sta chiedendo *quando*, e vuole vedere i giorni uno sotto
 * l'altro.
 *
 * Gli eventi arrivano da `/api/agenda`, che legge gli stessi nodi del
 * riepilogo della giornata: niente seconda verità sul calendario, e un giorno
 * senza impegni resta visibile e vuoto — perché «non hai niente giovedì» è
 * un'informazione, non un buco da nascondere.
 */
import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';

import { api, type AgendaDay, type AgendaResponse } from '@/src/api/client';
import { OraBadge, OraCard } from '@/src/components/ora-ui';
import { NienteQui, PaginaOra } from '@/src/components/pagine/PaginaOra';
import { ora, oraType } from '@/src/theme/oraSurface';
import { humanizeError } from '@/src/utils/errors';

export default function Agenda() {
  const [dati, setDati] = useState<AgendaResponse | null>(null);
  const [errore, setErrore] = useState<string | null>(null);
  const [carico, setCarico] = useState(true);

  const leggi = useCallback(async () => {
    setCarico(true);
    try {
      setDati(await api.agenda(7));
      setErrore(null);
    } catch (e) {
      setErrore(humanizeError(e));
    } finally {
      setCarico(false);
    }
  }, []);

  useEffect(() => {
    void leggi();
  }, [leggi]);

  const giorni = dati?.days || [];
  const quanti = dati?.total_events ?? 0;

  return (
    <PaginaOra
      titolo="Agenda"
      sottotitolo={
        carico
          ? 'Sto guardando i prossimi giorni…'
          : quanti === 0
            ? 'I prossimi sette giorni, e per ora sono liberi.'
            : quanti === 1
              ? 'Un impegno nei prossimi sette giorni.'
              : `${quanti} impegni nei prossimi sette giorni.`
      }
      attiva="index"
      testID="pagina-agenda"
    >
      {carico ? (
        <ActivityIndicator color={ora.cta} testID="agenda-carico" />
      ) : errore ? (
        <NienteQui testo={errore} testID="agenda-errore" />
      ) : (
        <>
          {giorni.map((g) => (
            <Giorno key={g.date} giorno={g} />
          ))}
          {dati && !dati.calendar_connected ? (
            <Text style={[oraType.small, { color: ora.ink3 }]} testID="agenda-nota-calendario">
              Nessun calendario collegato: qui vedi solo quello che è già dentro ORA.
            </Text>
          ) : null}
        </>
      )}
    </PaginaOra>
  );
}

function Giorno({ giorno }: { giorno: AgendaDay }) {
  const router = useRouter();

  return (
    <OraCard style={styles.giorno} testID={`agenda-giorno-${giorno.date}`}>
      <View style={styles.testaGiorno}>
        <Text
          style={[oraType.section, { color: giorno.is_today ? ora.deep : ora.ink }]}
          accessibilityRole="header"
          aria-level={2}
        >
          {giorno.label}
        </Text>
        {/* Il titolo dice già «Oggi»: ripeterlo in un badge non aggiunge niente. */}
        {giorno.is_today && giorno.events.length ? (
          <OraBadge label={giorno.events.length === 1 ? '1 impegno' : `${giorno.events.length} impegni`} tone="info" />
        ) : null}
      </View>

      {giorno.events.length === 0 ? (
        <Text style={[oraType.small, { color: ora.ink3 }]}>Niente in programma.</Text>
      ) : (
        giorno.events.map((e) => (
          <Pressable
            key={e.id}
            onPress={() => router.push(`/calendar-event/${encodeURIComponent(e.id)}` as never)}
            accessibilityRole="button"
            accessibilityLabel={`Apri ${e.title}`}
            style={({ pressed }) => [styles.evento, pressed && { opacity: 0.7 }]}
            testID={`agenda-evento-${e.id}`}
          >
            <Text style={[styles.ora, { color: ora.ink2 }]}>{e.time_label || '—'}</Text>
            <View style={{ flex: 1, gap: 2 }}>
              <Text style={[oraType.body, { color: ora.ink, fontWeight: '600' }]} numberOfLines={2}>
                {e.title}
              </Text>
              {e.location ? (
                <Text style={[oraType.small, { color: ora.ink3 }]} numberOfLines={1}>
                  <Ionicons name="location-outline" size={12} color={ora.ink3} /> {e.location}
                </Text>
              ) : null}
              {/*
                Che cosa c'entra ORA con questo appuntamento, quando c'entra
                davvero. Una riga che comparisse sempre non direbbe niente.
              */}
              {e.ora_note ? (
                <Text style={[oraType.small, { color: ora.deep }]} numberOfLines={2}>
                  {e.ora_note}
                </Text>
              ) : null}
              {e.source_label ? (
                <Text style={[oraType.small, { color: ora.ink3 }]}>Da: {e.source_label}</Text>
              ) : null}
            </View>
            <Ionicons name="chevron-forward" size={16} color={ora.ink3} />
          </Pressable>
        ))
      )}
    </OraCard>
  );
}

const styles = StyleSheet.create({
  giorno: { gap: 12, padding: 20 },
  testaGiorno: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  evento: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 14,
    paddingVertical: 12,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: ora.divider,
  },
  ora: { fontSize: 13, fontWeight: '600', width: 96 },
});
