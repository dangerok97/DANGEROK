/**
 * Calendario ORA: first-party, always available.
 * Optional Google/Apple connections only add events to the same view.
 */
import { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';

import { api, type AgendaDay, type AgendaEvent, type AgendaMonthResponse } from '@/src/api/client';
import { CalendarEventForm } from '@/src/components/calendar/CalendarEventForm';
import {
  localDayKey, monthCells, monthHeading, selectSource,
  type CalendarSourceFilter,
} from '@/src/components/calendar/nativeMonth';
import { OraCard } from '@/src/components/ora-ui';
import { PaginaOra } from '@/src/components/pagine/PaginaOra';
import { ora, oraType } from '@/src/theme/oraSurface';
import { humanizeError } from '@/src/utils/errors';

const WEEKDAYS = ['LUN', 'MAR', 'MER', 'GIO', 'VEN', 'SAB', 'DOM'];
const LABELS: Record<CalendarSourceFilter, string> = {
  all: 'Tutti', ora: 'ORA', google: 'Google', apple: 'Apple', other: 'Altri',
};

function thisMonth(day: string): string {
  return day.slice(0, 7);
}

export default function Agenda() {
  const router = useRouter();
  const [selected, setSelected] = useState(() => localDayKey(new Date()));
  const [month, setMonth] = useState(() => thisMonth(localDayKey(new Date())));
  const [source, setSource] = useState<CalendarSourceFilter>('all');
  const [creating, setCreating] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [data, setData] = useState<AgendaMonthResponse | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const grid = useMemo(() => monthCells(month), [month]);

  useEffect(() => {
    let live = true;
    setBusy(true);
    api.agendaMonth(month).then((result) => {
      if (!live) return;
      setData(result);
      setError('');
    }).catch((e) => {
      if (live) { setData(null); setError(humanizeError(e)); }
    }).finally(() => { if (live) setBusy(false); });
    return () => { live = false; };
  }, [month, refresh]);

  const days = useMemo(
    () => new Map((data?.days || []).map((day) => [day.date, day])),
    [data],
  );
  const today = localDayKey(new Date());
  const selectedDay = days.get(selected);
  const events = selectSource(selectedDay?.events || [], source);
  const availableSources: CalendarSourceFilter[] = ['all', 'ora'];
  for (const kind of ['google', 'apple', 'other'] as const) {
    if ((data?.connected_sources || []).includes(kind) || (data?.source_counts?.[kind] || 0) > 0) {
      availableSources.push(kind);
    }
  }

  const switchMonth = (offset: number) => {
    const [year, m] = month.split('-').map(Number);
    const next = new Date(year, m - 1 + offset, 1);
    const day = localDayKey(next);
    setMonth(thisMonth(day));
    setSelected(day);
    setCreating(false);
  };

  const goToday = () => {
    const now = localDayKey(new Date());
    setMonth(thisMonth(now));
    setSelected(now);
    setCreating(false);
  };

  const addEvent = () => {
    setCreating(true);
  };

  return (
    <PaginaOra
      titolo="Calendario ORA"
      sottotitolo="Il tuo calendario è già pronto: non serve Google, Apple o un altro account."
      attiva="index"
      testID="pagina-agenda"
      azione={
        <Pressable onPress={addEvent} accessibilityRole="button" testID="calendar-add-event"
          style={styles.newButton}>
          <Ionicons name="add" size={18} color="#fff" />
          <Text style={styles.newLabel}>Nuovo evento</Text>
        </Pressable>
      }
    >
      <OraCard style={styles.calendar} testID="ora-native-calendar">
        <View style={styles.monthHeader}>
          <Pressable accessibilityRole="button" accessibilityLabel="Mese precedente"
            testID="calendar-prev-month" onPress={() => switchMonth(-1)} style={styles.nav}>
            <Ionicons name="chevron-back" size={20} color={ora.ink} />
          </Pressable>
          <Text style={[oraType.section, { color: ora.ink, textTransform: 'capitalize', textAlign: 'center', flex: 1 }]}>
            {monthHeading(month)}
          </Text>
          <Pressable accessibilityRole="button" accessibilityLabel="Vai a oggi"
            testID="calendar-today" onPress={goToday} style={styles.today}>
            <Text style={[oraType.small, { color: ora.deep, fontWeight: '600' }]}>Oggi</Text>
          </Pressable>
          <Pressable accessibilityRole="button" accessibilityLabel="Mese successivo"
            testID="calendar-next-month" onPress={() => switchMonth(1)} style={styles.nav}>
            <Ionicons name="chevron-forward" size={20} color={ora.ink} />
          </Pressable>
        </View>
        <View style={styles.weekdays}>
          {WEEKDAYS.map((weekday) => (
            <Text key={weekday} style={styles.weekday}>{weekday}</Text>
          ))}
        </View>
        <View style={styles.monthGrid}>
          {grid.map((date, index) => {
            if (!date) return <View key={`blank-${index}`} style={styles.dayCell} />;
            const calendarDay = days.get(date);
            const isSelected = date === selected;
            const isToday = date === today;
            const count = selectSource(calendarDay?.events || [], source).length;
            return (
              <Pressable
                key={date}
                onPress={() => { setSelected(date); setCreating(false); }}
                accessibilityRole="button"
                accessibilityLabel={`${date}, ${count} impegni`}
                accessibilityState={{ selected: isSelected }}
                testID={`calendar-day-${date}`}
                style={[styles.dayCell, isSelected && styles.daySelected, isToday && styles.dayToday]}
              >
                <Text style={[styles.dayNumber, { color: isSelected ? '#fff' : ora.ink }]}>
                  {Number(date.slice(-2))}
                </Text>
                {count > 0 ? <Text style={[styles.dayCount, { color: isSelected ? '#fff' : ora.ink3 }]}>
                  {count}
                </Text> : null}
              </Pressable>
            );
          })}
        </View>
        <View style={styles.filters} testID="calendar-source-filters">
          {availableSources.map((kind) => (
            <Pressable
              key={kind}
              onPress={() => setSource(kind)}
              accessibilityRole="button"
              accessibilityState={{ selected: source === kind }}
              testID={`calendar-filter-${kind}`}
              style={[styles.filter, source === kind && styles.filterActive]}
            >
              <Text style={[styles.filterText, { color: source === kind ? '#fff' : ora.ink2 }]}>
                {LABELS[kind]}
              </Text>
            </Pressable>
          ))}
        </View>
        {data ? (
          <Text style={[oraType.small, { color: ora.ink3 }]}>
            {data.total_events === 1 ? '1 appuntamento nel mese' : `${data.total_events} appuntamenti nel mese`}
            {' · '}Gli eventi creati qui restano nel calendario ORA.
          </Text>
        ) : null}
      </OraCard>

      {creating ? (
        <OraCard style={styles.formCard} testID="calendar-create-form">
          <View style={styles.formHead}>
            <Text style={[oraType.section, { color: ora.ink }]}>Nuovo evento ORA</Text>
            <Text style={[oraType.small, { color: ora.ink3 }]}>{selected.split('-').reverse().join('/')}</Text>
          </View>
          <CalendarEventForm
            key={selected}
            day={selected}
            onCancel={() => setCreating(false)}
            onSaved={() => { setCreating(false); setRefresh((old) => old + 1); }}
          />
        </OraCard>
      ) : null}

      {busy ? (
        <ActivityIndicator color={ora.cta} testID="agenda-carico" />
      ) : error ? (
        <OraCard style={styles.dayCard}>
          <Text accessibilityRole="alert" style={[oraType.body, { color: ora.ink }]}>{error}</Text>
          <Pressable accessibilityRole="button" onPress={() => setRefresh((old) => old + 1)}
            style={styles.retry}><Text style={{ color: ora.deep }}>Riprova</Text></Pressable>
        </OraCard>
      ) : (
        <DayAgenda
          day={selectedDay || { date: selected, label: selected, is_today: false, events: [] }}
          events={events}
          onCreate={addEvent}
        />
      )}

      <OraCard style={styles.connections}>
        <View style={styles.connectionText}>
          <Text style={[oraType.body, { color: ora.ink, fontWeight: '600' }]}>
            Calendari esterni, solo se vuoi
          </Text>
          <Text style={[oraType.small, { color: ora.ink3 }]}>
            Puoi aggiungere Google Calendar o il calendario Apple del tuo iPhone.
            Gli eventi si vedono insieme, ma quelli salvati in ORA non vengono copiati sugli altri calendari.
          </Text>
        </View>
        <Pressable onPress={() => router.push('/settings')} accessibilityRole="button"
          testID="calendar-manage-connections" style={styles.link}>
          <Text style={{ color: ora.deep, fontWeight: '600' }}>Gestisci collegamenti</Text>
          <Ionicons name="chevron-forward" size={16} color={ora.deep} />
        </Pressable>
      </OraCard>
    </PaginaOra>
  );
}

function DayAgenda({ day, events, onCreate }: {
  day: AgendaDay; events: AgendaEvent[]; onCreate: () => void;
}) {
  const router = useRouter();
  return (
    <OraCard style={styles.dayCard} testID={`agenda-giorno-${day.date}`}>
      <View style={styles.dayHead}>
        <Text style={[oraType.section, { color: ora.ink, flex: 1, textTransform: 'capitalize' }]}>
          {day.label}
        </Text>
        <Pressable onPress={onCreate} accessibilityRole="button" testID="calendar-add-selected-day"
          style={styles.smallAdd}>
          <Ionicons name="add-circle-outline" size={20} color={ora.deep} />
          <Text style={[oraType.small, { color: ora.deep }]}>Aggiungi</Text>
        </Pressable>
      </View>
      {events.length === 0 ? (
        <Text style={[oraType.body, { color: ora.ink3 }]}>
          Nessun evento {day.is_today ? 'oggi' : 'per questo giorno'}{'.'}
        </Text>
      ) : events.map((e) => (
        <Pressable key={e.id} accessibilityRole="button"
          accessibilityLabel={`Apri ${e.title}`}
          testID={`agenda-evento-${e.id}`}
          onPress={() => router.push(`/calendar-event/${encodeURIComponent(e.id)}` as never)}
          style={styles.event}>
          <Text style={[oraType.small, { color: ora.ink2, width: 88, fontWeight: '600' }]}>
            {e.time_label || '—'}
          </Text>
          <View style={{ flex: 1, gap: 4 }}>
            <Text style={[oraType.body, { color: ora.ink, fontWeight: '600' }]} numberOfLines={2}>{e.title}</Text>
            {e.location ? <Text style={[oraType.small, { color: ora.ink3 }]}>{e.location}</Text> : null}
            <Text style={[oraType.small, { color: ora.ink3 }]}>
              {e.source_label || (e.source_type === 'ora' ? 'Calendario ORA' : 'Fonte non indicata')}
            </Text>
          </View>
          <Ionicons name="chevron-forward" size={16} color={ora.ink3} />
        </Pressable>
      ))}
    </OraCard>
  );
}

const styles = StyleSheet.create({
  newButton: { flexDirection: 'row', gap: 5, alignItems: 'center', borderRadius: 12, padding: 12, backgroundColor: ora.cta },
  newLabel: { color: '#fff', fontWeight: '700' },
  calendar: { padding: 16, gap: 16 },
  monthHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 6 },
  nav: { height: 42, width: 36, alignItems: 'center', justifyContent: 'center' },
  today: { height: 42, paddingHorizontal: 8, justifyContent: 'center' },
  weekdays: { flexDirection: 'row' },
  weekday: { width: '14.2857%', textAlign: 'center', fontSize: 11, color: ora.ink3, fontWeight: '600' },
  monthGrid: { flexDirection: 'row', flexWrap: 'wrap' },
  dayCell: { width: '14.2857%', minHeight: 58, padding: 5, alignItems: 'center', justifyContent: 'center', gap: 3, borderRadius: 9 },
  daySelected: { backgroundColor: ora.deep },
  dayToday: { borderWidth: 1, borderColor: ora.hairline },
  dayNumber: { fontSize: 15, fontWeight: '600' },
  dayCount: { fontSize: 11, fontWeight: '700' },
  filters: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  filter: { borderWidth: 1, borderColor: ora.hairline, borderRadius: 20, paddingHorizontal: 13, paddingVertical: 8 },
  filterActive: { backgroundColor: ora.deep, borderColor: ora.deep },
  filterText: { fontSize: 12, fontWeight: '600' },
  formCard: { padding: 18, gap: 8 },
  formHead: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  dayCard: { padding: 18, gap: 12 },
  dayHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  smallAdd: { flexDirection: 'row', alignItems: 'center', gap: 4, padding: 8 },
  event: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: ora.divider, paddingVertical: 12, flexDirection: 'row', gap: 12, alignItems: 'center' },
  retry: { padding: 10, alignSelf: 'flex-start' },
  connections: { padding: 18, gap: 10 },
  connectionText: { gap: 6 },
  link: { flexDirection: 'row', gap: 5, alignItems: 'center', paddingVertical: 8, alignSelf: 'flex-start' },
});
