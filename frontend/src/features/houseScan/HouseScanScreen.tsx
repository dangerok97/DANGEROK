import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, AppState, Linking, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useAuth } from '@/src/contexts/AuthContext';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { loginHrefFor, useAmbientInset } from '@/src/shell';
import { houseScanApi } from './api';
import { formatMetres, parseMetres, roomName, wallMeasurement } from './geometry';
import { getHouseScanLaunch } from './launch';
import { getHouseScanAvailability, scanHouse, cancelHouseScan } from './native';
import type { HouseScanAvailability } from './nativeTypes';
import type { HouseCapture, HouseScan, HouseScanPatch, HouseScanSummary } from './types';
import FloorPlan from './FloorPlan';

type PendingCapture = { capture: HouseCapture; token: string };
type Busy = 'capture' | 'save' | 'edit' | 'delete' | null;

function errorText(error: unknown): string {
  const e = error as { code?: string; status?: number; message?: string };
  if (e?.status === 401) return 'Accedi nuovamente a ORA per continuare.';
  if (e?.status === 409) return 'Questa pianta è stata aggiornata da un altro dispositivo. Premi Aggiorna e ripeti la modifica.';
  if (e?.code === 'ERR_ROOMPLAN_CAMERA_PERMISSION') return 'Consenti a ORA di usare la fotocamera nelle Impostazioni di iPhone, poi riprova.';
  if (e?.code === 'ERR_ROOMPLAN_INTERRUPTED') return 'La scansione è stata interrotta. Torna nella stanza e avviala di nuovo.';
  if (e?.code === 'ERR_ROOMPLAN_EMPTY') return 'Non sono state rilevate pareti sufficienti. Ripeti la scansione seguendo le indicazioni.';
  if (e?.code === 'ERR_ROOMPLAN_UNSUPPORTED') return 'La scansione richiede un iPhone o iPad con LiDAR e iOS 17 o successivo.';
  if (e?.code === 'ERR_ROOMPLAN_BUSY') return 'È già in corso una scansione.';
  if (e?.code === 'ERR_ROOMPLAN_CONFIGURATION') return 'Questa versione di ORA non è configurata per usare la fotocamera. Serve la versione iPhone con la scansione casa.';
  if (e?.code === 'ERR_ROOMPLAN_PROCESSING' || e?.code === 'ERR_ROOMPLAN_CAPTURE') return 'Non è stato possibile completare il rilievo. Riprova con la stanza ben illuminata.';
  if (e?.code === 'network_unreachable' || e?.message === 'Failed to fetch' || e?.message?.includes('abort')) return 'Collegamento interrotto. Controlla la connessione e riprova.';
  return e?.message || 'Operazione non riuscita. Riprova.';
}

function dateLabel(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Data non disponibile' : date.toLocaleString('it-IT', {
    day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

export default function HouseScanRoute() {
  const { user, loading } = useAuth();
  const { colors } = useTheme();
  const router = useRouter();
  const params = useLocalSearchParams<{ scan?: string }>();
  if (loading) return <View style={styles.center}><ActivityIndicator color={colors.accent} /></View>;
  if (!user) return <View style={styles.center}>
    <Text style={[styles.body, { color: colors.textPrimary }]}>Accedi a ORA per salvare la pianta nel tuo account.</Text>
    <Action label="Accedi a ORA" onPress={() => router.replace(loginHrefFor(params.scan === '1' ? '/casa?scan=1' : '/casa') as never)} />
  </View>;
  return <HouseScanScreen key={user.user_id} accountEmail={user.email} startFromLink={params.scan === '1'} />;
}

function HouseScanScreen({ accountEmail, startFromLink }: { accountEmail: string; startFromLink: boolean }) {
  const { colors } = useTheme();
  const router = useRouter();
  const ambient = useAmbientInset();
  const [items, setItems] = useState<HouseScanSummary[]>([]);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [moreLoading, setMoreLoading] = useState(false);
  const [selected, setSelected] = useState<HouseScan | null>(null);
  const [roomId, setRoomId] = useState<string | null>(null);
  const [wallId, setWallId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [busy, setBusy] = useState<Busy>(null);
  const [availability, setAvailability] = useState<HouseScanAvailability | null>(null);
  const [pending, setPending] = useState<PendingCapture | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [installedConfirmed, setInstalledConfirmed] = useState(false);
  const [launchAttempted, setLaunchAttempted] = useState(false);
  const [rename, setRename] = useState('');
  const [measurement, setMeasurement] = useState('');
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const alive = useRef(true);
  const session = useRef<string | null>(null);
  const readEpoch = useRef(0);
  const detailReadEpoch = useRef(0);
  const operation = useRef(false);
  const automaticStart = useRef(false);
  const selectedRef = useRef<HouseScan | null>(null);

  const browser = Platform.OS === 'web' && typeof navigator !== 'undefined' ? navigator : null;
  const launch = getHouseScanLaunch(Platform.OS, browser?.userAgent || '', browser?.maxTouchPoints || 0);
  const room = selected?.capture.rooms.find(item => item.id === roomId) || selected?.capture.rooms[0] || null;
  const wall = room?.walls.find(item => item.id === wallId) || null;
  const quote = selected && room && wall ? wallMeasurement(selected, room, wall) : null;

  const token = useCallback(async () => {
    if (!session.current) session.current = await houseScanApi.token();
    if (!session.current) throw new Error('Accedi nuovamente a ORA.');
    return session.current;
  }, []);

  const applyScan = useCallback((scan: HouseScan) => {
    selectedRef.current = scan;
    setSelected(scan);
    setLoading(false);
    setRoomId(previous => scan.capture.rooms.some(value => value.id === previous) ? previous : scan.capture.rooms[0]?.id || null);
    setItems(previous => [scan, ...previous.filter(value => value.id !== scan.id)]);
  }, []);

  const refresh = useCallback(async (showSpinner = false) => {
    if (operation.current || detailReadEpoch.current) return;
    const epoch = ++readEpoch.current;
    if (showSpinner) setLoading(true);
    try {
      const auth = await token();
      const result = await houseScanApi.list(auth);
      if (!alive.current || readEpoch.current !== epoch) return;
      setItems(result.scans);
      setNextOffset(result.has_more ? result.next_offset : null);
      if (selectedRef.current) {
        const id = selectedRef.current.id;
        try {
          const response = await houseScanApi.get(auth, id);
          if (alive.current && readEpoch.current === epoch && selectedRef.current?.id === id) {
            selectedRef.current = response.scan; setSelected(response.scan);
          }
        } catch (e) {
          if ((e as { status?: number }).status !== 404) throw e;
          if (alive.current && readEpoch.current === epoch) {
            selectedRef.current = null; setSelected(null); setWallId(null);
          }
        }
      }
    } catch (e) { if (alive.current && readEpoch.current === epoch) setError(errorText(e)); }
    finally { if (alive.current && readEpoch.current === epoch) setLoading(false); }
  }, [token]);

  useEffect(() => {
    alive.current = true;
    void refresh(true);
    void getHouseScanAvailability().then(value => { if (alive.current) setAvailability(value); })
      .catch(e => { if (alive.current) setError(errorText(e)); });
    return () => {
      alive.current = false; readEpoch.current += 1;
      void cancelHouseScan().catch(() => undefined);
    };
  }, [refresh]);

  useEffect(() => {
    if (!pending || Platform.OS !== 'web' || typeof window === 'undefined') return;
    const warnBeforeClose = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warnBeforeClose);
    return () => window.removeEventListener('beforeunload', warnBeforeClose);
  }, [pending]);

  useEffect(() => {
    const onFocus = () => { void refresh(); };
    const onVisibility = () => { if (typeof document !== 'undefined' && document.visibilityState === 'visible') onFocus(); };
    const appState = AppState.addEventListener('change', state => { if (state === 'active') onFocus(); });
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      window.addEventListener('focus', onFocus);
      document.addEventListener('visibilitychange', onVisibility);
    }
    return () => {
      appState.remove();
      if (Platform.OS === 'web' && typeof window !== 'undefined') {
        window.removeEventListener('focus', onFocus);
        document.removeEventListener('visibilitychange', onVisibility);
      }
    };
  }, [refresh]);

  const saveCapture = useCallback(async (draft: PendingCapture) => {
    setBusy('save'); setError('');
    try {
      const result = await houseScanApi.create(draft.token, draft.capture);
      if (!alive.current) return;
      readEpoch.current += 1;
      applyScan(result.scan); setPending(null); setWallId(null); setRename(''); setMeasurement('');
      setNotice(result.created ? 'Pianta salvata nel tuo account. È disponibile anche su ORA web.' : 'Questa scansione era già stata salvata. Ho riaperto la stessa pianta.');
    } catch (e) {
      if (alive.current) setError(`${errorText(e)} La scansione è ancora qui: riprova il salvataggio senza rifarla.`);
    } finally { if (alive.current) setBusy(null); }
  }, [applyScan]);

  const startCapture = useCallback(async () => {
    if (operation.current || pending || !availability?.supported) return;
    operation.current = true; readEpoch.current += 1; detailReadEpoch.current = 0;
    setLoading(false); setDetailLoading(false); setBusy('capture'); setError(''); setNotice('');
    try {
      const frozenToken = await token();
      const capture = await scanHouse();
      if (!alive.current) return;
      const draft = { capture, token: frozenToken };
      setPending(draft);
      await saveCapture(draft);
    } catch (e) {
      if (alive.current) {
        if ((e as { code?: string })?.code === 'ERR_ROOMPLAN_CANCELLED') setNotice('Scansione annullata. Nessuna nuova pianta è stata salvata.');
        else setError(errorText(e));
      }
    } finally { operation.current = false; if (alive.current) setBusy(null); }
  }, [availability?.supported, pending, token, saveCapture]);

  useEffect(() => {
    if (startFromLink && Platform.OS === 'ios' && availability?.supported && !loading && !automaticStart.current) {
      automaticStart.current = true;
      void startCapture();
    }
  }, [startFromLink, availability?.supported, loading, startCapture]);

  const retrySave = async () => {
    if (!pending || operation.current) return;
    operation.current = true; readEpoch.current += 1; detailReadEpoch.current = 0;
    setLoading(false); setDetailLoading(false);
    try { await saveCapture(pending); } finally { operation.current = false; }
  };

  const loadMore = async () => {
    if (nextOffset === null || moreLoading || operation.current) return;
    const epoch = readEpoch.current;
    setMoreLoading(true);
    try {
      const result = await houseScanApi.list(await token(), nextOffset);
      if (alive.current && readEpoch.current === epoch) {
        setItems(previous => [...previous, ...result.scans.filter(item => !previous.some(existing => existing.id === item.id))]);
        setNextOffset(result.has_more ? result.next_offset : null);
      }
    } catch (e) { if (alive.current && readEpoch.current === epoch) setError(errorText(e)); }
    finally { if (alive.current) setMoreLoading(false); }
  };

  const openScan = async (id: string) => {
    if (operation.current) return;
    const epoch = ++readEpoch.current;
    detailReadEpoch.current = epoch;
    setLoading(false);
    setDetailLoading(true); setError(''); setNotice(''); setDeleteConfirm(false); setWallId(null); setRename(''); setMeasurement('');
    try {
      const result = await houseScanApi.get(await token(), id);
      if (alive.current && readEpoch.current === epoch) applyScan(result.scan);
    } catch (e) { if (alive.current && readEpoch.current === epoch) setError(errorText(e)); }
    finally {
      if (detailReadEpoch.current === epoch) detailReadEpoch.current = 0;
      if (alive.current && readEpoch.current === epoch) setDetailLoading(false);
    }
  };

  const update = async (patch: Omit<HouseScanPatch, 'revision'>, success: string) => {
    if (!selected || operation.current) return false;
    operation.current = true; readEpoch.current += 1; detailReadEpoch.current = 0;
    setLoading(false); setDetailLoading(false); setBusy('edit'); setError(''); setNotice('');
    try {
      const response = await houseScanApi.patch(await token(), selected.id, { ...patch, revision: selected.revision });
      if (alive.current) { readEpoch.current += 1; applyScan(response.scan); setNotice(success); }
      return true;
    } catch (e) { if (alive.current) setError(errorText(e)); return false; }
    finally { operation.current = false; if (alive.current) setBusy(null); }
  };

  const deleteScan = async () => {
    if (!selected || operation.current) return;
    operation.current = true; readEpoch.current += 1; detailReadEpoch.current = 0;
    setLoading(false); setDetailLoading(false); setBusy('delete'); setError('');
    try {
      await houseScanApi.remove(await token(), selected);
      if (alive.current) {
        readEpoch.current += 1;
        setItems(previous => previous.filter(item => item.id !== selected.id));
        selectedRef.current = null; setSelected(null); setWallId(null); setDeleteConfirm(false);
        setNotice('Pianta eliminata dal tuo account.');
      }
    } catch (e) { if (alive.current) setError(errorText(e)); }
    finally { operation.current = false; if (alive.current) setBusy(null); }
  };

  const openNative = async () => {
    if (!launch.nativeUrl) return;
    setError(''); setLaunchAttempted(true);
    try { await Linking.openURL(launch.nativeUrl); }
    catch { setError('Non riesco ad aprire ORA per iPhone. Verifica che la versione con scansione casa sia installata.'); }
  };

  const selectRoom = (id: string) => { setRoomId(id); setWallId(null); setRename(''); setMeasurement(''); };
  const selectWall = (id: string) => { setWallId(id); setMeasurement(''); };
  const nativeMessage = availability?.reason === 'requires_ios17'
    ? 'La scansione richiede iOS 17 o successivo.'
    : availability?.reason === 'requires_lidar'
      ? 'Questo dispositivo non ha il LiDAR necessario. Puoi consultare le piante salvate dal tuo iPhone compatibile.'
      : 'Questa installazione di ORA non include ancora la scansione casa. Serve la versione iPhone con il modulo di scansione.';

  return <SafeAreaView edges={['top']} style={[styles.screen, { backgroundColor: colors.backgroundPrimary }]}>
    <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={[styles.content, { paddingBottom: ambient.paddingBottom + 28 }]}>
      <View style={styles.topBar}>
        <Action label="Vita" quiet icon="arrow-back" onPress={() => router.push('/vita' as never)} />
        <Action label="Aggiorna" quiet icon="refresh-outline" testID="house-refresh" disabled={!!busy || loading} onPress={() => { setError(''); void refresh(true); }} />
      </View>
      <View style={styles.header}>
        <View style={[styles.heroIcon, { backgroundColor: colors.accentMuted }]}><Ionicons name="home-outline" size={30} color={colors.accent} /></View>
        <Text style={[styles.title, { color: colors.textPrimary }]}>La tua casa</Text>
        <Text style={[styles.body, { color: colors.textSecondary }]}>Scansiona le stanze. Ritrova pianta e misure quando ti servono.</Text>
        <Text style={[styles.caption, { color: colors.textTertiary }]}>Account: {accountEmail}</Text>
      </View>

      {error ? <View testID="house-error" accessibilityRole="alert" style={[styles.message, { backgroundColor: colors.errorBg }]}><Text style={[styles.small, { color: colors.error }]}>{error}</Text></View> : null}
      {notice ? <View testID="house-notice" accessibilityLiveRegion="polite" style={[styles.message, { backgroundColor: colors.successBg }]}><Text style={[styles.small, { color: colors.textPrimary }]}>{notice}</Text></View> : null}

      <View testID="house-scan-entry" style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
        <Text style={[styles.heading, { color: colors.textPrimary }]}>Scansiona casa</Text>
        {launch.mode === 'native' ? <>
          {!availability ? <ActivityIndicator color={colors.accent} /> : availability.supported ? <>
            <Text style={[styles.small, { color: colors.textSecondary }]}>Inquadra una stanza alla volta seguendo le indicazioni. Potrai controllare le quote prima di usarle per mobili o lavori.</Text>
            <Action label={busy === 'capture' ? 'Scansione in corso…' : busy === 'save' ? 'Salvataggio…' : 'Avvia scansione'} icon="scan-outline"
              testID="house-start-scan" disabled={!!busy || !!pending} onPress={() => void startCapture()} />
            {availability.camera_permission === 'denied' || availability.camera_permission === 'restricted' ?
              <Action label="Apri Impostazioni fotocamera" quiet onPress={() => { void Linking.openSettings().catch(e => setError(errorText(e))); }} /> : null}
          </> : <Text testID="house-native-unavailable" style={[styles.small, { color: colors.textSecondary }]}>{nativeMessage}</Text>}
        </> : launch.mode === 'iphone-web' ? <>
          <Text style={[styles.small, { color: colors.textSecondary }]}>Puoi partire da qui. La scansione si apre in ORA per iPhone, che può usare il sensore LiDAR. Safari conserva e mostra il risultato dopo il salvataggio.</Text>
          <Text style={[styles.caption, { color: colors.textSecondary }]}>Nell’app iPhone accedi allo stesso account: {accountEmail}.</Text>
          {!launch.releaseReady ? <Text testID="house-ios-release-pending" style={[styles.small, { color: colors.textSecondary }]}>La scansione richiede ORA per iPhone. L’installazione non è ancora disponibile.</Text> : null}
          {launch.releaseReady ? <Action label="Apri scanner in ORA" icon="scan-outline" testID="house-open-native" onPress={() => void openNative()} /> :
            <Pressable testID="house-installed-confirm" accessibilityRole="button" accessibilityState={{ expanded: installedConfirmed }}
              style={styles.textAction} onPress={() => setInstalledConfirmed(previous => !previous)}>
              <Text style={[styles.buttonText, { color: colors.accent }]}>{installedConfirmed ? 'Nascondi apertura app' : 'Ho già installato ORA'}</Text>
            </Pressable>}
          {!launch.releaseReady && installedConfirmed ? <>
            <Text style={[styles.caption, { color: colors.textSecondary }]}>Per chi ha già una versione di prova di ORA con la scansione casa.</Text>
            <Action label="Apri ORA su iPhone" testID="house-open-native" onPress={() => void openNative()} />
          </> : null}
          {launch.releaseReady && launch.installUrl ? <Action label="Installa ORA per iPhone" quiet icon="download-outline" testID="house-install-native"
            onPress={() => { void Linking.openURL(launch.installUrl!).catch(e => setError(errorText(e))); }} /> : null}
          {launchAttempted ? <Text testID="house-launch-fallback" accessibilityLiveRegion="polite" style={[styles.caption, { color: colors.textSecondary }]}>Se l’app non si apre, serve una versione installata con la scansione casa. Dopo aver salvato, torna qui e premi Aggiorna.</Text> : null}
        </> : <Text style={[styles.small, { color: colors.textSecondary }]}>Puoi consultare qui le piante del tuo account. Per acquisire una stanza, apri ORA su un iPhone o iPad con LiDAR.</Text>}
      </View>

      {pending ? <View testID="house-pending-save" style={[styles.card, { borderColor: colors.warning, backgroundColor: colors.warningBg }]}>
        <Text style={[styles.heading, { color: colors.textPrimary }]}>Scansione da salvare</Text>
        <Text style={[styles.small, { color: colors.textSecondary }]}>{pending.capture.rooms.length} {pending.capture.rooms.length === 1 ? 'stanza acquisita' : 'stanze acquisite'}. Resta su questa schermata fino al salvataggio: chiuderla o cambiare pagina elimina il rilievo non salvato.</Text>
        <Action label={busy === 'save' ? 'Salvataggio…' : 'Riprova salvataggio'} testID="house-retry-save" disabled={!!busy} onPress={() => void retrySave()} />
      </View> : null}

      <View style={styles.sectionHeader}>
        <Text style={[styles.heading, { color: colors.textPrimary }]}>Piante salvate</Text>
        {loading ? <ActivityIndicator color={colors.accent} /> : <Text style={[styles.caption, { color: colors.textTertiary }]}>{items.length}</Text>}
      </View>
      {!loading && !items.length ? <View testID="house-empty" style={[styles.empty, { borderColor: colors.border }]}>
        <Ionicons name="map-outline" size={36} color={colors.textTertiary} />
        <Text style={[styles.body, { color: colors.textPrimary }]}>La prima pianta inizia da una stanza.</Text>
        <Text style={[styles.small, { color: colors.textSecondary }]}>Dopo la scansione troverai qui le pareti, le aperture e le misure. Potrai dare un nome alle stanze e verificare le quote.</Text>
      </View> : null}
      <View style={styles.savedList}>
        {items.map(item => <Pressable key={item.id} testID={`house-saved-${item.id}`} accessibilityRole="button"
          accessibilityLabel={`${item.title}, ${item.room_count} stanze, apri pianta`} accessibilityState={{ selected: selected?.id === item.id }}
          disabled={!!busy} onPress={() => void openScan(item.id)}
          style={[styles.saved, { backgroundColor: selected?.id === item.id ? colors.accentMuted : colors.surface, borderColor: selected?.id === item.id ? colors.accent : colors.border }]}>
          <View style={{ flex: 1 }}><Text style={[styles.savedTitle, { color: colors.textPrimary }]}>{item.title}</Text>
            <Text style={[styles.caption, { color: colors.textSecondary }]}>{item.room_count} {item.room_count === 1 ? 'stanza' : 'stanze'} · {dateLabel(item.captured_at)}</Text>
            <Text style={[styles.caption, { color: colors.textTertiary }]}>{item.verified_wall_count} {item.verified_wall_count === 1 ? 'quota verificata' : 'quote verificate'}</Text></View>
          <Ionicons name="chevron-forward" size={20} color={colors.textSecondary} />
        </Pressable>)}
      </View>
      {nextOffset !== null ? <Action label={moreLoading ? 'Caricamento…' : 'Carica altre piante'} quiet disabled={moreLoading || !!busy || loading} onPress={() => void loadMore()} /> : null}

      {detailLoading ? <ActivityIndicator testID="house-detail-loading" color={colors.accent} /> : null}
      {selected && room && !detailLoading ? <View testID="house-detail" style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
        <Text style={[styles.heading, { color: colors.textPrimary }]}>{selected.title}</Text>
        <Text style={[styles.caption, { color: colors.textSecondary }]}>Rilievo LiDAR del {dateLabel(selected.captured_at)}</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.roomTabs}>
          {selected.capture.rooms.map(item => <Pressable key={item.id} accessibilityRole="button" accessibilityState={{ selected: item.id === room.id }}
            testID={`house-room-${item.id}`} onPress={() => selectRoom(item.id)}
            style={[styles.roomTab, { backgroundColor: item.id === room.id ? colors.accentMuted : colors.backgroundSecondary, borderColor: item.id === room.id ? colors.accent : colors.border }]}>
            <Text style={[styles.buttonText, { color: item.id === room.id ? colors.accent : colors.textPrimary }]}>{roomName(selected, item)}</Text>
          </Pressable>)}
        </ScrollView>
        <FloorPlan room={room} selectedWallId={wallId} onSelectWall={selectWall} />
        <Text style={[styles.caption, { color: colors.textSecondary }]}>{room.walls.length} pareti · {room.doors.length} porte · {room.windows.length} finestre</Text>
        <View style={styles.editRow}>
          <TextInput testID="house-room-name" accessibilityLabel="Nome della stanza" placeholder={roomName(selected, room)} placeholderTextColor={colors.placeholder}
            value={rename} onChangeText={setRename} maxLength={80} style={[styles.input, { flex: 1, color: colors.textPrimary, borderColor: colors.borderStrong, backgroundColor: colors.backgroundPrimary }]} />
          <Action label="Rinomina" quiet disabled={!!busy || !rename.trim()} onPress={() => {
            const name = rename.trim();
            if (name) void update({ room_labels: [{ room_id: room.id, name }] }, 'Nome della stanza aggiornato.').then(saved => { if (saved) setRename(''); });
          }} />
        </View>

        <Text style={[styles.subheading, { color: colors.textPrimary }]}>Misure delle pareti</Text>
        <View style={styles.wallList}>
          {room.walls.map((item, index) => {
            const value = wallMeasurement(selected, room, item);
            return <Pressable key={item.id} accessibilityRole="button" onPress={() => selectWall(item.id)} testID={`house-wall-${item.id}`}
              accessibilityState={{ selected: wallId === item.id }} style={[styles.wallRow, { backgroundColor: wallId === item.id ? colors.accentMuted : colors.backgroundSecondary }]}>
              <Text style={[styles.small, { color: colors.textPrimary }]}>Parete {index + 1}</Text>
              <View style={{ alignItems: 'flex-end' }}><Text style={[styles.savedTitle, { color: colors.textPrimary }]}>{formatMetres(value.length_m)}</Text>
                <Text style={[styles.caption, { color: value.verified ? colors.success : colors.textSecondary }]}>{value.verified ? 'Verificata da te' : 'Da scansione'}</Text></View>
            </Pressable>;
          })}
        </View>
        {wall && quote ? <View testID="house-wall-inspector" style={[styles.inspector, { borderColor: colors.border }]}>
          <Text style={[styles.subheading, { color: colors.textPrimary }]}>Parete {room.walls.findIndex(item => item.id === wall.id) + 1}</Text>
          <Text style={[styles.small, { color: colors.textSecondary }]}>Scansione: {formatMetres(wall.dimensions.x)} · altezza {formatMetres(wall.dimensions.y)}</Text>
          {quote.verified ? <Text style={[styles.small, { color: colors.success }]}>Misura verificata: {formatMetres(quote.length_m)} · {dateLabel(quote.verified.verified_at)}</Text> : null}
          <Text style={[styles.caption, { color: colors.textSecondary }]}>Se hai controllato questa lunghezza con il metro, inseriscila qui. Il rilievo originale resta conservato.</Text>
          <View style={styles.editRow}>
            <TextInput testID="house-verified-length" accessibilityLabel="Lunghezza verificata in metri" placeholder="Metri, es. 3,42" placeholderTextColor={colors.placeholder}
              keyboardType="decimal-pad" inputMode="decimal" maxLength={8} value={measurement} onChangeText={setMeasurement}
              style={[styles.input, { flex: 1, color: colors.textPrimary, borderColor: colors.borderStrong, backgroundColor: colors.backgroundPrimary }]} />
            <Action label="Salva misura" testID="house-save-measurement" disabled={!!busy || !measurement.trim()} onPress={() => {
              const length = parseMetres(measurement);
              if (length === null) { setError('Inserisci una lunghezza in metri maggiore di zero, ad esempio 3,42.'); return; }
              void update({ wall_measurements: [{ room_id: room.id, wall_id: wall.id, length_m: length }] }, 'Misura verificata salvata.').then(saved => { if (saved) setMeasurement(''); });
            }} />
          </View>
          {quote.verified ? <Action label="Rimuovi verifica" quiet disabled={!!busy} onPress={() => void update({ wall_measurements: [{ room_id: room.id, wall_id: wall.id, length_m: null }] }, 'Verifica rimossa. La quota da scansione è conservata.')} /> : null}
        </View> : null}
        <Text style={[styles.caption, { color: colors.textTertiary }]}>Le quote da scansione vanno controllate per tagli o mobili su misura. Le misure verificate sono annotate senza deformare la pianta.</Text>
        {!deleteConfirm ? <Action label="Elimina questa pianta" quiet disabled={!!busy} onPress={() => setDeleteConfirm(true)} /> : <View style={[styles.message, { backgroundColor: colors.errorBg }]}>
          <Text style={[styles.small, { color: colors.textPrimary }]}>Eliminare “{selected.title}” con tutte le sue stanze e misure?</Text>
          <View style={styles.editRow}><Action label="Elimina pianta" testID="house-confirm-delete" disabled={!!busy} onPress={() => void deleteScan()} /><Action label="Annulla" quiet disabled={!!busy} onPress={() => setDeleteConfirm(false)} /></View>
        </View>}
      </View> : null}
    </ScrollView>
  </SafeAreaView>;
}

function Action({ label, onPress, disabled = false, quiet = false, icon, testID }: {
  label: string; onPress: () => void; disabled?: boolean; quiet?: boolean;
  icon?: keyof typeof Ionicons.glyphMap; testID?: string;
}) {
  const { colors } = useTheme();
  return <Pressable testID={testID} accessibilityRole="button" accessibilityLabel={label} disabled={disabled}
    accessibilityState={{ disabled }} onPress={onPress}
    style={({ pressed }) => [styles.action, { opacity: disabled ? 0.45 : pressed ? 0.75 : 1, backgroundColor: quiet ? 'transparent' : colors.accent }]}>
    {icon ? <Ionicons name={icon} size={20} color={quiet ? colors.accent : colors.onAccent} /> : null}
    <Text style={[styles.buttonText, { color: quiet ? colors.accent : colors.onAccent }]}>{label}</Text>
  </Pressable>;
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  center: { flex: 1, padding: tokens.spacing.xl, alignItems: 'center', justifyContent: 'center', gap: tokens.spacing.lg },
  content: { width: '100%', maxWidth: 960, alignSelf: 'center', paddingHorizontal: tokens.spacing.lg, paddingTop: tokens.spacing.md, gap: tokens.spacing.lg },
  topBar: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  header: { gap: tokens.spacing.sm, paddingBottom: tokens.spacing.sm },
  heroIcon: { width: 56, height: 56, borderRadius: tokens.radius.lg, alignItems: 'center', justifyContent: 'center', marginBottom: tokens.spacing.sm },
  title: { ...tokens.typography.hero },
  heading: { ...tokens.typography.headline },
  subheading: { ...tokens.typography.body, fontWeight: '600' },
  body: { ...tokens.typography.body },
  small: { ...tokens.typography.bodySmall },
  caption: { ...tokens.typography.caption },
  savedTitle: { ...tokens.typography.bodySmall, fontWeight: '600' },
  card: { padding: tokens.spacing.lg, borderRadius: tokens.radius.lg, borderWidth: 1, gap: tokens.spacing.md },
  message: { borderRadius: tokens.radius.md, padding: tokens.spacing.lg, gap: tokens.spacing.md },
  action: { minHeight: tokens.touch.min, paddingHorizontal: tokens.spacing.lg, paddingVertical: tokens.spacing.md, borderRadius: tokens.radius.md, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: tokens.spacing.sm, alignSelf: 'flex-start' },
  textAction: { minHeight: tokens.touch.min, justifyContent: 'center', alignSelf: 'flex-start' },
  buttonText: { ...tokens.typography.button, flexShrink: 1 },
  sectionHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: tokens.spacing.sm },
  empty: { padding: tokens.spacing.xl, borderWidth: 1, borderStyle: 'dashed', borderRadius: tokens.radius.lg, alignItems: 'flex-start', gap: tokens.spacing.md },
  savedList: { gap: tokens.spacing.sm },
  saved: { padding: tokens.spacing.lg, borderRadius: tokens.radius.md, borderWidth: 1, flexDirection: 'row', alignItems: 'center', gap: tokens.spacing.md, minHeight: 84 },
  roomTabs: { flexDirection: 'row', gap: tokens.spacing.sm, paddingVertical: tokens.spacing.xs },
  roomTab: { minHeight: tokens.touch.min, justifyContent: 'center', paddingHorizontal: tokens.spacing.lg, borderWidth: 1, borderRadius: tokens.radius.full },
  editRow: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: tokens.spacing.sm },
  input: { minWidth: 140, minHeight: 48, borderWidth: 1, borderRadius: tokens.radius.md, paddingHorizontal: tokens.spacing.md, paddingVertical: tokens.spacing.sm, ...tokens.typography.bodySmall },
  wallList: { gap: tokens.spacing.sm },
  wallRow: { padding: tokens.spacing.md, borderRadius: tokens.radius.md, minHeight: 64, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: tokens.spacing.md },
  inspector: { borderWidth: 1, borderRadius: tokens.radius.md, padding: tokens.spacing.md, gap: tokens.spacing.md },
});
