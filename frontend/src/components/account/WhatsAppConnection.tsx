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

export function WhatsAppConnection() {
  const { colors } = useTheme();
  const [status, setStatus] = useState<WhatsAppLinkStatus | null>(null);
  const [pairing, setPairing] = useState<WhatsAppPairing | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const next = await api.whatsappStatus();
      setStatus(next);
      if (next.linked) setPairing(null);
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
                  ? ' Modello Meta con dettagli approvato: gli avvisi concreti sono abilitati anche oltre 24 ore.'
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
                          : status.template_approval_status === 'waba_not_configured'
                            ? ' Il server deve ancora collegare il WhatsApp Business Account usato per verificare i modelli.'
                            : status.template_approval_status === 'unverified'
                              ? ' Non è stato possibile verificare l’approvazione del modello Meta.'
                              : ' Fuori dalle 24 ore serve un modello Utility con dettaglio approvato da Meta.'}
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
  codeBox: { borderWidth: StyleSheet.hairlineWidth, borderRadius: tokens.radius.md, padding: 14, gap: 12, marginTop: 8 },
  code: { fontSize: 17, letterSpacing: 1, fontWeight: '700' },
});
