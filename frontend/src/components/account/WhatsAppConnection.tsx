/**
 * WhatsApp is an optional transport for this exact ORA account.
 * The connection is proven by a code shown only to the signed-in user and
 * returned through a provider-signed WhatsApp webhook.
 */
import { useCallback, useEffect, useState } from 'react';
import { Linking, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { api, type WhatsAppLinkStatus, type WhatsAppPairing } from '@/src/api/client';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { ActionBtn } from '@/src/components/ui/ActionBtn';
import { SettingCard } from '@/src/components/account';
import { humanizeError } from '@/src/utils/errors';

type RecentWhatsAppAlert = Awaited<ReturnType<typeof api.whatsappNotificationHistory>>['alerts'][number];

function deliveryLabel(item: RecentWhatsAppAlert): string {
  const labels: Record<string, string> = {
    ready: 'In coda per Meta',
    held_template: 'In attesa del modello Meta',
    held_source: 'Verifica della fonte non riuscita',
    sending: 'Invio in corso',
    accepted: 'Accettato da Meta, consegna non confermata',
    sent: 'Inviato da Meta, consegna non confermata',
    delivered: 'Consegnato secondo Meta',
    read: 'Letto secondo Meta',
    failed: 'Meta non ha consegnato il messaggio',
    acceptance_unknown: 'Invio incerto: nessun reinvio automatico',
    cancelled: 'Avviso annullato',
  };
  return labels[item.status] || 'Esito tecnico: ' + String(item.status).slice(0, 30);
}

export function WhatsAppConnection() {
  const { colors } = useTheme();
  const [status, setStatus] = useState<WhatsAppLinkStatus | null>(null);
  const [pairing, setPairing] = useState<WhatsAppPairing | null>(null);
  const [alertHistory, setAlertHistory] = useState<RecentWhatsAppAlert[]>([]);
  const [historyChecked, setHistoryChecked] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [retryNotice, setRetryNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const next = await api.whatsappStatus();
      setStatus(next);
      if (next.linked) {
        setPairing(null);
        try {
          const history = await api.whatsappNotificationHistory();
          setAlertHistory(history.alerts || []);
          setHistoryChecked(true);
          setHistoryError(null);
        } catch {
          setHistoryError('Impossibile leggere le ricevute WhatsApp.');
          setHistoryChecked(false);
        }
      } else {
        setAlertHistory([]);
        setHistoryChecked(false);
        setHistoryError(null);
      }
    } catch (err) {
      setError(humanizeError(err));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const connect = async () => {
    setBusy(true);
    setError(null);
    try {
      const next = await api.whatsappStartLink();
      setPairing(next);
    } catch (err) {
      setError(humanizeError(err));
    } finally {
      setBusy(false);
    }
  };

  const setAlerts = async (enabled: boolean) => {
    setBusy(true);
    setError(null);
    try {
      await api.whatsappSetNotifications(enabled);
      await refresh();
    } catch (err) {
      setError(humanizeError(err));
    } finally {
      setBusy(false);
    }
  };

  const setDetails = async (enabled: boolean) => {
    setBusy(true);
    setError(null);
    try {
      await api.whatsappSetNotificationDetails(enabled);
      await refresh();
    } catch (err) {
      setError(humanizeError(err));
    } finally {
      setBusy(false);
    }
  };

  const retryFailedRecurring = async () => {
    setBusy(true);
    setError(null);
    setRetryNotice(null);
    try {
      await api.whatsappRetryFailedRecurring();
      setRetryNotice('Un solo nuovo tentativo è stato messo in coda. Non è ancora una conferma di consegna.');
      await refresh();
    } catch (err) {
      setError(humanizeError(err));
    } finally {
      setBusy(false);
    }
  };

  const retryAlreadyExists = alertHistory.some(item => item.retry_kind === 'owner_confirmed_failed_once');
  const hasTodayFailedRecurring = alertHistory.some(item =>
    item.source_kind === 'recurring_due'
    && item.status === 'failed'
    && item.kind === 'approved_template'
    && !!item.created_at
    && new Date(item.created_at).toDateString() === new Date().toDateString()
  );
  const canRetryFailedRecurring = !!(
    status?.notifications_enabled
    && status.notifications_detail_enabled
    && hasTodayFailedRecurring
    && !retryAlreadyExists
  );

  const disconnect = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.whatsappDisconnect();
      setPairing(null);
      await refresh();
    } catch (err) {
      setError(humanizeError(err));
    } finally {
      setBusy(false);
    }
  };

  const openWhatsApp = async (linkAccount = false) => {
    const number = pairing?.display_number || status?.display_number;
    if (!number || (linkAccount && !pairing)) return;
    try {
      const url = 'https://wa.me/' + number
        + (linkAccount && pairing
            ? '?text=' + encodeURIComponent('COLLEGA ' + pairing.code)
            : '');
      await Linking.openURL(url);
    } catch (err) {
      setError(humanizeError(err));
    }
  };

  return (
    <SettingCard testID="whatsapp-connection">
      <View style={styles.header}>
        <View style={[styles.icon, { backgroundColor: colors.accentMuted }]}>
          <Ionicons name="chatbubble-ellipses-outline" size={19} color={colors.accent} />
        </View>
        <View style={styles.headerText}>
          <Text style={[styles.title, { color: colors.textPrimary }]}>ORA su WhatsApp</Text>
          <Text style={[styles.subtitle, { color: colors.textSecondary }]}>
            {status?.linked
              ? 'Collegato al numero che termina con ' + (status.phone_last4 || '••••')
              : status?.configured
                ? 'Non collegato'
                : 'In attesa di configurazione Meta'}
          </Text>
        </View>
      </View>

      <Text style={[styles.description, { color: colors.textSecondary }]}>
        Scrivi o parla a ORA anche su WhatsApp: stesso account, stessa memoria,
        calendario e competenze. Puoi inviare testo, vocali, foto, documenti e
        posizioni condivise. Quando servono GPS live, fotocamera in tempo reale
        o permessi del telefono, ORA ti dà il link per completare nell'app.
        Nessun avviso WhatsApp automatico è attivo senza consenso esplicito.
      </Text>

      {status?.linked && status.shared_ai_core && typeof status.shared_capability_count === 'number' ? (
        <Text testID="whatsapp-shared-core" style={[styles.description, { color: colors.textSecondary }]}>
          Motore AI condiviso con l'app: {status.shared_capability_count} competenze nel catalogo unico.
          Le nuove competenze del motore centrale sono visibili anche qui senza un secondo collegamento.
          Quelle che richiedono sensori o interfacce dedicate si completano nell'app ORA.
        </Text>
      ) : null}

      {status?.linked ? (
        <View style={styles.buttons}>
          <Text style={[styles.description, { color: colors.textSecondary }]}>
            Gli avvisi WhatsApp riportano direttamente le informazioni concrete
            che ORA può condividere, quando sono verificate. Per includere
            anche dettagli personali serve la tua autorizzazione separata.
            Fuori dalla finestra WhatsApp di 24 ore occorre un modello Meta
            Utility approvato che supporti il dettaglio del messaggio.
            Puoi disattivare gli avvisi anche scrivendo STOP a ORA.
          </Text>
          {status.notifications_enabled ? (
            <>
              <Text testID="whatsapp-alerts-enabled" style={[styles.description, { color: colors.textSecondary }]}>
                Consenso agli avvisi attivo.
                {status.template_approval_status === 'approved_dynamic'
                  ? ' Modello Meta approvato: fuori dalle 24 ore sono consentiti soltanto i promemoria ricorrenti salvati da te (es. compleanni). Gli altri avvisi restano nell’app ORA.'
                  : status.template_approval_status === 'approved'
                    ? ' Modello Meta statico approvato ma non adatto: per informazioni dirette occorre un modello con {{1}} nel corpo.'
                  : status.template_approval_status === 'pending'
                    ? ' Il modello di messaggio è ancora in revisione da Meta.'
                    : status.template_approval_status === 'rejected' || status.template_approval_status === 'paused'
                      ? ' Il modello di messaggio non è attualmente autorizzato da Meta.'
                      : status.template_approval_status === 'wrong_category'
                        ? ' Il modello Meta deve essere approvato nella categoria Utility per questi avvisi.'
                        : status.template_approval_status === 'requires_parameters'
                          ? ' Il modello Meta deve avere una sola variabile {{1}} nel corpo, senza altri parametri.'
                          : status.template_approval_status === 'wrong_content'
                            ? ' Il contenuto del modello Meta non coincide con il promemoria ricorrente approvato: gli invii sono bloccati.'
                          : status.template_approval_status === 'waba_not_configured'
                            ? ' Il server deve ancora collegare il WhatsApp Business Account usato per verificare i modelli.'
                            : status.template_approval_status === 'unverified'
                              ? ' Non è stato possibile verificare l’approvazione del modello Meta.'
                              : ' Fuori dalle 24 ore serve un modello Meta Utility specifico e approvato per i promemoria ricorrenti. Non è valido per qualsiasi notifica AI.'}
                {status.notification_channel_ready && status.template_approval_status !== 'approved_dynamic'
                  ? ' Per ora il canale può inviare soltanto nella finestra di conversazione attiva.'
                  : ''}
              </Text>
              <Text style={[styles.description, { color: colors.textSecondary }]}>
                {status.notifications_detail_enabled
                  ? 'Dettagli completi abilitati: possono apparire dati privati (email, importi, appuntamenti) su WhatsApp e nelle notifiche del telefono. Meta gestisce il messaggio.'
                  : 'Per leggere anche i dettagli personali direttamente su WhatsApp, puoi attivarli. Attenzione: i messaggi passano attraverso Meta e potrebbero comparire sulla schermata di blocco.'}
              </Text>
              <ActionBtn
                icon={status.notifications_detail_enabled ? 'eye-off-outline' : 'eye-outline'}
                label={status.notifications_detail_enabled ? 'Nascondi dettagli personali' : 'Mostra dettagli personali su WhatsApp'}
                loading={busy}
                disabled={busy}
                onPress={() => void setDetails(!status.notifications_detail_enabled)}
                testID="whatsapp-alerts-details"
              />
              <ActionBtn
                variant="danger"
                icon="notifications-off-outline"
                label="Disattiva avvisi WhatsApp"
                loading={busy}
                disabled={busy}
                onPress={() => void setAlerts(false)}
                testID="whatsapp-alerts-disable"
              />
            </>
          ) : (
            <ActionBtn
              icon="notifications-outline"
              label="Attiva avvisi WhatsApp"
              loading={busy}
              disabled={busy}
              onPress={() => void setAlerts(true)}
              testID="whatsapp-alerts-enable"
            />
          )}
          <View testID="whatsapp-alert-delivery-history" style={[styles.historyPanel, { borderColor: colors.border }]}>
            <Text style={[styles.title, { color: colors.textPrimary }]}>
              Ultimi esiti degli avvisi WhatsApp
            </Text>
            <Text style={[styles.description, { color: colors.textSecondary }]}>
              «Accettato» non significa «consegnato». La consegna è confermata
              soltanto quando Meta invia una ricevuta specifica.
            </Text>
            {historyError ? (
              <Text style={[styles.description, { color: colors.error }]}>{historyError}</Text>
            ) : null}
            {historyChecked && alertHistory.length === 0 ? (
              <Text style={[styles.description, { color: colors.textSecondary }]}>
                Nessun avviso WhatsApp registrato. Un promemoria visibile nella Home
                non significa che sia stato messo in coda per WhatsApp.
              </Text>
            ) : null}
            {alertHistory.slice(0, 5).map((item, index) => (
              <View key={index} style={[styles.historyEntry, { borderColor: colors.border }]}>
                <Text style={[styles.historyStatus, { color: colors.textPrimary }]}>
                  {item.source_kind === 'recurring_due' ? 'Promemoria ricorrente' : 'Avviso ORA'}:
                  {' '}{deliveryLabel(item)}
                </Text>
                {item.created_at ? (
                  <Text style={[styles.description, { color: colors.textSecondary }]}>
                    Registrato: {new Date(item.created_at).toLocaleString('it-IT')}
                  </Text>
                ) : null}
                {item.failure_code ? (
                  <Text style={[styles.description, { color: colors.textSecondary }]}>
                    Codice tecnico: {item.failure_code}
                  </Text>
                ) : null}
              </View>
            ))}
            {retryNotice ? (
              <Text style={[styles.description, { color: colors.textPrimary }]}>{retryNotice}</Text>
            ) : null}
            {canRetryFailedRecurring ? (
              <>
                <Text style={[styles.description, { color: colors.textSecondary }]}>
                  Meta ha segnalato la mancata consegna di un promemoria di oggi.
                  Puoi autorizzare un solo nuovo invio con lo stesso modello approvato.
                  ORA controllerà nuovamente che la ricorrenza e i consensi siano validi.
                  Non ripeterà automaticamente l'invio in caso di errore.
                </Text>
                <ActionBtn
                  icon="refresh-outline"
                  label="Riprova una sola volta il promemoria"
                  loading={busy}
                  disabled={busy}
                  onPress={() => void retryFailedRecurring()}
                  testID="whatsapp-retry-failed-recurring"
                />
              </>
            ) : null}
            <ActionBtn
              icon="refresh-outline"
              label="Aggiorna esiti WhatsApp"
              loading={busy}
              disabled={busy}
              onPress={() => void refresh()}
              testID="whatsapp-alert-history-refresh"
            />
          </View>
          <ActionBtn
            primary
            icon="chatbubble-outline"
            label="Scrivi a ORA su WhatsApp"
            disabled={!status.display_number || busy}
            onPress={() => void openWhatsApp()}
            testID="whatsapp-open-linked"
          />
          <ActionBtn
            variant="danger"
            icon="unlink-outline"
            label="Scollega WhatsApp"
            loading={busy}
            disabled={busy}
            onPress={() => void disconnect()}
            testID="whatsapp-disconnect"
          />
        </View>
      ) : status?.configured ? (
        <>
          {pairing ? (
            <View style={[styles.codeBox, { borderColor: colors.border, backgroundColor: colors.backgroundSecondary }]}>
              <Text style={[styles.description, { color: colors.textSecondary }]}>
                Invia questo testo nella chat WhatsApp con ORA (codice valido per 10 minuti):
              </Text>
              <Text selectable style={[styles.code, { color: colors.textPrimary }]}>
                {'COLLEGA ' + pairing.code}
              </Text>
              {pairing.display_number ? (
                <ActionBtn
                  primary
                  icon="chatbubble-outline"
                  label="Apri WhatsApp"
                  onPress={() => void openWhatsApp(true)}
                  testID="whatsapp-open"
                />
              ) : (
                <Text style={[styles.description, { color: colors.textSecondary }]}>
                  Apri WhatsApp e invia il testo al numero ufficiale di ORA.
                </Text>
              )}
              <ActionBtn icon="refresh-outline" label="Verifica collegamento" onPress={() => void refresh()} />
            </View>
          ) : (
            <View style={styles.buttons}>
              <ActionBtn
                primary
                icon="link-outline"
                label="Collega WhatsApp"
                loading={busy}
                disabled={busy}
                onPress={() => void connect()}
                testID="whatsapp-connect"
              />
            </View>
          )}
        </>
      ) : (
        <Text style={[styles.description, { color: colors.textTertiary }]}>
          L'integrazione non è ancora attiva sul server. Serve collegare il numero
          WhatsApp Business ufficiale nel pannello Meta.
        </Text>
      )}
      {error ? <Text style={{ color: colors.error, fontSize: 12 }}>{error}</Text> : null}
    </SettingCard>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'center', gap: tokens.spacing.md },
  icon: { width: 40, height: 40, borderRadius: tokens.radius.sm, alignItems: 'center', justifyContent: 'center' },
  headerText: { flex: 1, minWidth: 0, gap: 2 },
  title: { fontSize: 16, fontWeight: '650' as any },
  subtitle: { fontSize: 12, lineHeight: 17 },
  description: { fontSize: 13, lineHeight: 19, marginTop: 6 },
  buttons: { flexDirection: 'row', flexWrap: 'wrap', marginTop: 10 },
  historyPanel: { width: '100%', borderWidth: 1, borderRadius: tokens.radius.sm, padding: 12, marginTop: 10, gap: 6 },
  historyEntry: { borderTopWidth: StyleSheet.hairlineWidth, paddingTop: 8, marginTop: 4 },
  historyStatus: { fontSize: 13, fontWeight: '600' },
  codeBox: { borderWidth: StyleSheet.hairlineWidth, borderRadius: tokens.radius.md, padding: 14, gap: 12, marginTop: 8 },
  code: { fontSize: 17, letterSpacing: 1, fontWeight: '700' },
});
