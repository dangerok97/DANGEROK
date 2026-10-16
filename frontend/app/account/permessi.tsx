/**
 * Permessi e accessi — what ORA may use, and how you get in.
 *
 * Two different questions that a settings screen usually runs together. What
 * ORA is allowed to reach is one thing; how this account is opened is another,
 * and signing in with Google says nothing about whether ORA can read a Google
 * calendar. They are separate sections here for that reason.
 *
 * The page shows a control only where pressing it changes a real permission.
 * Location and autonomy are stored user choices. Connected sources report their
 * own state. Standing permissions stay separate from the autonomy mode: choosing
 * to let ORA act in the background never invents a capability permission, and
 * granting one capability never widens the others.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';

import { api } from '@/src/api/client';
import { ConnectorOAuthError } from '@/src/connectors/connectorOAuth';
import { connectGoogleSource } from '@/src/connectors/connectorOAuthRuntime';
import { humanizeError } from '@/src/utils/errors';
import { haptic } from '@/src/utils/haptic';
import { useInflight } from '@/src/shell';
import { useTheme } from '@/src/theme/ThemeProvider';
import {
  AuthMethods,
  BoundaryNote,
  CALENDAR_WRITE_BOUNDARY,
  ChoiceRow,
  DOCUMENT_SCOPE_BOUNDARY,
  InlineError,
  LinkRow,
  MAIL_BOUNDARY,
  PartialNote,
  SettingCard,
  SubpageShell,
  connectedServices,
  connectionLabel,
  useAccount,
  type ConnectionState,
  type LocationMode,
} from '@/src/components/account';

const LOCATION_CHOICES: Array<{ id: LocationMode; label: string; detail: string }> = [
  {
    id: 'off',
    label: 'Disattivata',
    detail: 'ORA non sa dove sei.',
  },
  {
    id: 'while_using',
    label: 'Durante l’uso di ORA',
    detail: 'Consenti la posizione sul dispositivo per meteo e luoghi. Viene aggiornata mentre usi ORA.',
  },
];

/*
  Quanto ORA può interrompere.

  Tre parole, non tre soglie: quello che l'utente sceglie viaggia fino al
  giudizio come una frase su di sé, e il modello la pesa insieme a tutto il
  resto. Nessun ramo di codice legge questo valore per decidere se notificare.
*/
const NOTIFICATION_CHOICES: Array<{
  id: 'minimal' | 'balanced' | 'proactive';
  label: string;
  detail: string;
}> = [
  {
    id: 'minimal',
    label: 'Solo quando conta davvero',
    detail: 'ORA ti raggiunge fuori dall’app soltanto se lasciarlo perdere avrebbe conseguenze.',
  },
  {
    id: 'balanced',
    label: 'Equilibrato',
    detail: 'ORA ti avvisa quando è utile, senza esagerare. È così di default.',
  },
  {
    id: 'proactive',
    label: 'Più proattivo',
    detail: 'Preferisci saperlo prima, anche a costo di qualche interruzione in più.',
  },
];

type PresenceState = {
  supported: boolean;
  reason?: string;
  enabled: boolean;
  background: 'granted' | 'denied' | 'undetermined';
};

type ConnectedSourceRow = {
  id: string;
  what: string;
  state: string;
  last_read_at?: string | null;
};


type StandingGrant = {
  id: string;
  capability: string;
  scope?: string | null;
  effect_scope?: string[];
};

type AutonomyMode = 'observe' | 'prepare' | 'act_within_grants';

const AUTONOMY_CHOICES: Array<{ id: AutonomyMode; label: string; detail: string }> = [
  {
    id: 'observe',
    label: 'Osserva e riferisci',
    detail: 'ORA capisce cosa succede, ma non prepara né esegue modifiche da sola.',
  },
  {
    id: 'prepare',
    label: 'Prepara e chiedi',
    detail: 'ORA può preparare ciò che serve. Se non hai già dato un permesso specifico, chiede prima di cambiare qualcosa.',
  },
  {
    id: 'act_within_grants',
    label: 'Agisci entro i permessi che ti do',
    detail: 'ORA può partire anche da sola, ma soltanto per le azioni che hai autorizzato in modo permanente. Tutto il resto continua a chiedere.',
  },
];

const LOCAL_CALENDAR_CREATE_CAPABILITY = 'calendar.local.write';
const LOCAL_CALENDAR_CREATE_SCOPE = 'Aggiungere nuovi impegni personali al calendario ORA.';


/**
 * What to say under a calendar's name.
 *
 * The connector's own word when there is nothing to add, and the connected
 * source's sentence when there is — which is exactly when it matters: a
 * calendar that is connected but has not been read since yesterday looks
 * identical from the connector's side, and is not the same thing at all.
 *
 * «Connesso» plus a recent read is not worth two lines, so it stays one.
 */
function mailboxDetail(source: ConnectedSourceRow): string {
  if (source.state !== 'Connesso') return source.state;
  const read = humanAge(source.last_read_at);
  return read ? `Connesso · letto ${read}` : 'Connesso';
}

function sourceDetail(
  service: { state: ConnectionState },
  connected: ConnectedSourceRow[],
): string {
  const base = connectionLabel(service.state);
  const source = connected.find((c) => /calendar/i.test(c.what));
  if (!source) return base;
  if (source.state !== 'Connesso') return source.state;
  const read = humanAge(source.last_read_at);
  return read ? `${base} · letto ${read}` : base;
}


/** How long ago, in the words somebody would use. Never a timestamp. */
function humanAge(iso?: string | null): string {
  if (!iso) return '';
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return '';
  const minutes = Math.floor((Date.now() - then) / 60000);
  if (minutes < 2) return 'ora';
  if (minutes < 60) return `${minutes} min fa`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return hours === 1 ? "un'ora fa" : `${hours} ore fa`;
  const days = Math.floor(hours / 24);
  return days === 1 ? 'ieri' : `${days} giorni fa`;
}


export default function PermessiScreen() {
  const router = useRouter();
  const { colors } = useTheme();
  const { data, loading, error, reload } = useAccount();
  const [location, setLocation] = useState<LocationMode | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [writeError, setWriteError] = useState<string | null>(null);
  const [presence, setPresence] = useState<PresenceState | null>(null);

  /*
    I permessi permanenti che ORA ha già.

    Letti dal backend con la frase che la persona ha accettato: qui non si
    ricostruisce niente, perché un permesso raccontato dal client è un
    permesso che nessuno ha verificato.
  */
  /*
    Quanto è aggiornato quello che ORA sa da ogni sorgente.

    Una riga sola, e solo quando aggiunge qualcosa: «Connesso» lo dice già il
    connettore, mentre «l'ultima lettura non è riuscita» o «quello che so è
    vecchio» sono cose che nessuno poteva sapere prima e che cambiano quanto
    ci si può fidare di una risposta di ORA.
  */
  const [connected, setConnected] = useState<ConnectedSourceRow[]>([]);
  const [connectingMail, setConnectingMail] = useState(false);
  const mailConnectionActive = useRef(false);

  useEffect(() => {
    let alive = true;
    void api
      .getConnectedSources()
      .then((out) => {
        if (alive) setConnected(out.sources || []);
      })
      .catch(() => {
        /* Silenzioso: la pagina resta utile anche senza questa riga. */
      });
    return () => {
      alive = false;
    };
  }, []);

  const [grants, setGrants] = useState<StandingGrant[]>([]);
  const [autonomyMode, setAutonomyMode] = useState<AutonomyMode | null>(null);
  const [autonomyChosen, setAutonomyChosen] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [revoking, setRevoking] = useState<string | null>(null);
  const [pendingRevocation, setPendingRevocation] = useState<StandingGrant | null>(null);
  const revokeInFlight = useRef(false);

  const loadAutonomy = useCallback(async () => {
    // Failure cannot be treated as the default "prepare" choice: it may hide
    // a mode that the server has already saved. Callers must see the error.
    const out = await api.getAgentAutonomy();
    setAutonomyMode(out.mode);
    setAutonomyChosen(Boolean(out.chosen_by_user));
    setGrants((out.grants || []).filter((g) => g.active !== false));
  }, []);

  useEffect(() => {
    void loadAutonomy().catch((e) => {
      setWriteError(`Non riesco a leggere i permessi di ORA: ${humanizeError(e)}`);
    });
  }, [loadAutonomy]);

  const revokeGrant = useCallback(
    async (capability: string, grantId: string) => {
      // Revocation can only be called by the explicit dialog confirmation,
      // never directly by tapping an active permission in the overview.
      if (revokeInFlight.current || !grantId || pendingRevocation?.id !== grantId) return;
      revokeInFlight.current = true;
      haptic('tap');
      setRevoking(grantId);
      setWriteError(null);
      try {
        const result = await api.revokeAgentAutonomy(capability, grantId);
        if (!result.ok || result.revoked < 1) {
          throw new Error('Il permesso non è stato revocato. Aggiorna la pagina per verificare lo stato.');
        }
        await loadAutonomy();
        setPendingRevocation(null);
        haptic('success');
      } catch (e) {
        haptic('error');
        setWriteError(humanizeError(e));
        // Preserve the dialog on a failed confirmation: do not imply success.
      } finally {
        revokeInFlight.current = false;
        setRevoking(null);
      }
    },
    [pendingRevocation, loadAutonomy],
  );

  // Continuous presence is a second, larger permission. It is read here rather
  // than assumed, because the OS can revoke it from its own settings and an
  // app that keeps claiming to be watching would be lying.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const runtime = await import('@/src/location/presenceRuntime');
      const can = runtime.support();
      const perms = await runtime.permissions();
      const on = await runtime.isEnabled();
      if (!cancelled) {
        setPresence({
          supported: can.supported,
          reason: can.reason,
          enabled: on && perms.background === 'granted',
          background: perms.background,
        });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const togglePresence = useCallback(
    (next: boolean) =>
      guard(async () => {
        setBusy('presence');
        setWriteError(null);
        try {
          const runtime = await import('@/src/location/presenceRuntime');
          if (next) {
            const result = await runtime.enable();
            if (!result.ok) {
              setWriteError(result.reason ?? null);
            }
            const perms = await runtime.permissions();
            setPresence((p) =>
              p ? { ...p, enabled: result.ok, background: perms.background } : p,
            );
          } else {
            // Off means the phone stops watching. Nothing is deleted: what ORA
            // already knows is the person's to keep or erase, separately.
            await runtime.disable();
            setPresence((p) => (p ? { ...p, enabled: false } : p));
          }
        } finally {
          setBusy(null);
        }
      }),
    [],
  );

  const snapshot = data?.snapshot;
  const mode: LocationMode = location ?? snapshot?.location ?? 'off';

  const guard = useInflight();

  const chooseAutonomyMode = useCallback(
    (next: AutonomyMode) =>
      guard(async () => {
        haptic('tap');
        setBusy(`autonomy_${next}`);
        setWriteError(null);
        try {
          const response = await api.setAgentAutonomyMode(next);
          if (!response.ok) throw new Error('ORA non ha confermato la scelta.');
          // The POST response is authoritative for the selected mode. Render
          // it immediately; re-read the grants separately and report any
          // failure instead of silently reverting to "prepare".
          setAutonomyMode(next);
          setAutonomyChosen(true);
          await loadAutonomy();
          haptic('success');
        } catch (e) {
          haptic('error');
          setWriteError(humanizeError(e));
        } finally {
          setBusy(null);
        }
      }),
    [guard, loadAutonomy],
  );

  const calendarCreateGrant = grants.find(
    (grant) =>
      grant.capability === LOCAL_CALENDAR_CREATE_CAPABILITY
      && (grant.effect_scope || []).includes('create'),
  );
  const calendarCreateGranted = Boolean(calendarCreateGrant);

  // One deliberately scoped consent replaces two separate settings steps.
  // No permission for external calendars, messages, payments or cancellations.
  const enableEverydayAutonomy = useCallback(() => {
    if (autonomyMode === null) {
      setWriteError('Prima verifico lo stato dei permessi di ORA.');
      void loadAutonomy().catch((e) => setWriteError(humanizeError(e)));
      return;
    }
    if (autonomyMode === 'act_within_grants' && calendarCreateGranted) {
      setAdvancedOpen(true); // already active: show details, do not toggle off
      return;
    }
    // Switching into act mode also activates OTHER existing grants. Keep
    // that decision in the detailed mode selector, never the simple button.
    if (autonomyMode !== 'act_within_grants' &&
        grants.some((g) => g.capability !== LOCAL_CALENDAR_CREATE_CAPABILITY)) {
      setAdvancedOpen(true);
      setWriteError('Hai altri permessi attivi: verifica la modalità nella sezione Personalizza prima di attivare nuove azioni.');
      return;
    }
    return guard(async () => {
      haptic('tap');
      setBusy('enable_everyday_autonomy');
      setWriteError(null);
      try {
        if (autonomyMode !== 'act_within_grants') {
          const modeResult = await api.setAgentAutonomyMode('act_within_grants');
          if (!modeResult.ok) throw new Error('La modalità autonoma non è stata salvata.');
        }
        if (!calendarCreateGranted) {
          const permission = await api.grantAgentAutonomy(
            LOCAL_CALENDAR_CREATE_CAPABILITY, LOCAL_CALENDAR_CREATE_SCOPE,
          );
          if (!permission.ok || !permission.grant?.id) {
            throw new Error('Il permesso calendario non è stato confermato.');
          }
        }
        await loadAutonomy(); // confirm real server state, no optimistic success
        haptic('success');
      } catch (e) {
        haptic('error');
        setWriteError(`Attivazione incompleta: ${humanizeError(e)}. Puoi riprovare senza ricreare permessi già presenti.`);
        void loadAutonomy().catch(() => undefined);
      } finally {
        setBusy(null);
      }
    });
  }, [autonomyMode, calendarCreateGranted, grants, guard, loadAutonomy]);

  const setMode = useCallback((next: LocationMode) => guard(async () => {
    haptic('tap');
    setBusy(`loc_${next}`);
    setWriteError(null);
    try {
      if (next === 'while_using') {
        const { shareForegroundPosition } = await import('@/src/location/shareForeground');
        await shareForegroundPosition();
        setLocation('while_using');
      } else {
        await api.locationSetPreference('off');
        setLocation('off');
      }
      haptic('success');
    } catch (e: any) {
      haptic('error');
      setWriteError(e instanceof Error ? e.message : humanizeError(e));
    } finally {
      setBusy(null);
    }
  }), [guard]);

  /*
    Le notifiche. Caricate a parte perché non fanno parte dello snapshot dei
    permessi: sono una preferenza, non un accesso concesso a una fonte.
  */
  const [notifications, setNotifications] = useState<{
    level: 'minimal' | 'balanced' | 'proactive';
    quiet: { enabled: boolean; start_hour: number; end_hour: number };
    muted: number;
  } | null>(null);

  useEffect(() => {
    let alive = true;
    void api
      .getNotificationPreferences()
      .then((r) => {
        if (!alive) return;
        setNotifications({
          level: r.preferences.level,
          quiet: r.preferences.quiet_hours,
          muted: r.muted,
        });
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  const chooseLevel = useCallback(
    async (level: 'minimal' | 'balanced' | 'proactive') => {
      void haptic('select');
      const previous = notifications;
      setNotifications((n) => (n ? { ...n, level } : n));
      try {
        await api.setNotificationLevel(level);
      } catch (e) {
        // La verità è del server: se rifiuta, si torna a quello che c'era.
        setNotifications(previous);
        setWriteError(humanizeError(e));
      }
    },
    [notifications],
  );

  const toggleQuietHours = useCallback(
    async (enabled: boolean) => {
      void haptic('select');
      const previous = notifications;
      setNotifications((n) => (n ? { ...n, quiet: { ...n.quiet, enabled } } : n));
      try {
        const r = await api.setQuietHours({ enabled });
        setNotifications((n) =>
          n ? { ...n, quiet: r.preferences.quiet_hours } : n,
        );
      } catch (e) {
        setNotifications(previous);
        setWriteError(humanizeError(e));
      }
    },
    [notifications],
  );

  const calendars = (snapshot?.services || []).filter((s) => s.id.endsWith('calendar'));
  const calendarConnected = connectedServices(calendars).length > 0;
  // Una casella si riconosce da come si presenta al lettore, non da un id
  // interno: `what` è la stessa parola che la persona vede sulla riga.
  const mailboxes = connected.filter((c) => /gmail|mail|email|posta/i.test(c.what));

  /*
    Collegare la posta.

    Porta su Google e basta: e' Google a fare la domanda, ed e' giusto cosi'
    — nessuna schermata di ORA puo' spiegare meglio di quella cosa si sta
    concedendo. Al ritorno la riga si aggiorna da sola, perche' e' la
    sorgente a dire se e' collegata, non questa schermata a ricordarselo.
  */
  const connectMailbox = useCallback(async () => {
    if (mailConnectionActive.current) return;
    mailConnectionActive.current = true;
    haptic('tap');
    setConnectingMail(true);
    setWriteError(null);
    try {
      const result = await connectGoogleSource('gmail', '/account/permessi', {
        start: api.gmailOAuthStart,
        instances: api.gmailInstances,
      });
      if (result.state === 'connected') {
        const sources = await api.getConnectedSources();
        setConnected(sources.sources || []);
        await reload();
      }
    } catch (e: any) {
      setWriteError(e instanceof ConnectorOAuthError ? e.message : humanizeError(e));
    } finally {
      mailConnectionActive.current = false;
      setConnectingMail(false);
    }
  }, [reload]);

  return (
    <SubpageShell
      title="Permessi e accessi"
      subtitle="Cosa ORA può usare, e come entri nel tuo account."
      testID="account-permissions"
    >
      {snapshot?.partial ? (
        <PartialNote>Alcune informazioni non sono disponibili al momento.</PartialNote>
      ) : null}
      {error ? <InlineError>{error}</InlineError> : null}

      <SettingCard
        title="ORA nella tua giornata"
        detail="Non serve configurare tutto. Scegli solo cosa autorizzare e ORA usa le impostazioni già disponibili."
        testID="perm-everyday-autonomy"
      >
        <BoundaryNote>
          Puoi permettere a ORA di aggiungere da sola nel suo calendario gli impegni
          personali già confermati dalle fonti che hai collegato. Non può invitare
          persone, usare Google Calendar per scrivere, cancellare eventi o effettuare pagamenti.
        </BoundaryNote>
        {autonomyMode === null ? (
          <BoundaryNote>Verifico le tue autorizzazioni…</BoundaryNote>
        ) : (
          <ChoiceRow
            label={autonomyMode === 'act_within_grants' && calendarCreateGranted
              ? 'Autonomia per gli impegni attiva'
              : 'Attiva ORA per i miei impegni'}
            detail={autonomyMode === 'act_within_grants' && calendarCreateGranted
              ? 'Attiva · ORA può aggiungere nuovi impegni confermati nel calendario interno.'
              : 'Una scelta: autorizzi solo la creazione di nuovi impegni confermati nel calendario ORA.'}
            selected={autonomyMode === 'act_within_grants' && calendarCreateGranted}
            onPress={() => void enableEverydayAutonomy()}
            busy={busy === 'enable_everyday_autonomy'}
            testID="autonomy-one-step-enable"
          />
        )}
        <BoundaryNote>
          Le notifiche seguono le tue preferenze attuali. Posizione e altre
          integrazioni restano facoltative e richiedono autorizzazioni separate.
        </BoundaryNote>
      </SettingCard>

      <Pressable
        accessibilityRole="button"
        accessibilityState={{ expanded: advancedOpen }}
        testID="autonomy-advanced-toggle"
        onPress={() => { haptic('tap'); setAdvancedOpen((open) => !open); }}
        style={[revokeStyles.advancedToggle, { borderColor: colors.border }]}
      >
        <Text style={{ color: colors.textPrimary, fontWeight: '600' }}>
          {advancedOpen ? 'Nascondi impostazioni avanzate' : 'Personalizza impostazioni (facoltativo)'}
        </Text>
      </Pressable>

      {advancedOpen ? (
        <>
          <SettingCard
            title="Modalità di autonomia"
            detail={autonomyChosen
              ? 'Solo per chi vuole scegliere manualmente la modalità generale di ORA.'
              : 'Di base ORA prepara e chiede. Puoi scegliere una modalità diversa qui.'}
            testID="perm-autonomy-mode"
          >
            {AUTONOMY_CHOICES.map((choice) => (
              <ChoiceRow
                key={choice.id}
                label={choice.label}
                detail={choice.detail}
                selected={(autonomyMode ?? 'prepare') === choice.id}
                onPress={() => void chooseAutonomyMode(choice.id)}
                busy={busy === `autonomy_${choice.id}`}
                testID={`autonomy-mode-${choice.id}`}
              />
            ))}
          </SettingCard>

      <SettingCard title="Posizione" testID="perm-location">
        {LOCATION_CHOICES.map((c) => (
          <ChoiceRow
            key={c.id}
            label={c.label}
            detail={c.detail}
            selected={mode === c.id}
            onPress={() => void setMode(c.id)}
            busy={busy === `loc_${c.id}`}
            testID={`location-mode-${c.id}`}
          />
        ))}
      </SettingCard>

      {/*
        Presence Intelligence is asked for separately and second. "Always" is a
        large thing to request, and requesting it alongside the ordinary
        location choice is how an app gets refused both.
      */}
      <SettingCard
        title="Riconoscimento dei luoghi"
        detail={
          presence && !presence.supported
            ? presence.reason
            : 'Serve perché ORA si accorga di quando arrivi o lasci i tuoi luoghi anche quando l’app è chiusa. Se lo disattivi, ORA continua a funzionare: semplicemente non se ne accorge da sola.'
        }
        testID="perm-presence"
      >
        {presence?.supported ? (
          <>
            <ChoiceRow
              label="Disattivato"
              detail="ORA non osserva nulla quando è chiusa."
              selected={!presence.enabled}
              onPress={() => void togglePresence(false)}
              busy={busy === 'presence'}
              testID="presence-off"
            />
            <ChoiceRow
              label="Attivo anche in background"
              detail="ORA riconosce ingressi e uscite dai tuoi luoghi. Nessun tracciamento continuo: usa le zone che conosce già."
              selected={presence.enabled}
              onPress={() => void togglePresence(true)}
              busy={busy === 'presence'}
              testID="presence-on"
            />
          </>
        ) : null}
      </SettingCard>

      {/*
        Le notifiche vivono qui e non in una schermata loro: sono una cosa che
        ORA può fare, come leggere il calendario o riconoscere i luoghi, e una
        pagina dedicata la farebbe sembrare più importante di quanto sia.
      */}
      <SettingCard
        title="Notifiche"
        detail="Quanto vuoi che ORA ti interrompa quando non sei nell’app. Qualunque cosa scegli, continui a trovare tutto qui dentro."
        testID="perm-notifications"
      >
        {notifications ? (
          <>
            {NOTIFICATION_CHOICES.map((c) => (
              <ChoiceRow
                key={c.id}
                label={c.label}
                detail={c.detail}
                selected={notifications.level === c.id}
                onPress={() => void chooseLevel(c.id)}
                testID={`notification-level-${c.id}`}
              />
            ))}
            <ChoiceRow
              label="Ore di silenzio"
              detail={
                notifications.quiet.enabled
                  ? `ORA non ti interrompe dalle ${notifications.quiet.start_hour}:00 alle ${notifications.quiet.end_hour}:00.`
                  : 'Non c’è una fascia di silenzio: ORA decide da sola se è un buon momento.'
              }
              selected={notifications.quiet.enabled}
              onPress={() => void toggleQuietHours(!notifications.quiet.enabled)}
              testID="notification-quiet-hours"
            />
            {notifications.muted ? (
              <BoundaryNote>
                {notifications.muted === 1
                  ? 'C’è una cosa su cui hai chiesto di non essere avvisato. Resta comunque visibile in ORA.'
                  : `Ci sono ${notifications.muted} cose su cui hai chiesto di non essere avvisato. Restano comunque visibili in ORA.`}
              </BoundaryNote>
            ) : null}
          </>
        ) : null}
      </SettingCard>

      <SettingCard
        title="Calendario"
        detail={
          loading && !snapshot
            ? 'Carico…'
            : calendarConnected
              ? 'ORA legge i tuoi eventi per capire come è fatta la tua giornata.'
              : 'Nessun calendario collegato: ORA non vede i tuoi eventi.'
        }
        testID="perm-calendar"
      >
        <View>
          {calendars.map((s, i) => (
            <LinkRow
              key={s.id}
              label={s.name}
              detail={sourceDetail(s, connected)}
              icon="calendar-outline"
              first={i === 0}
              onPress={() => {
                haptic('tap');
                router.push('/settings' as any);
              }}
              testID={`perm-calendar-${s.id}`}
            />
          ))}
        </View>
        <BoundaryNote>{CALENDAR_WRITE_BOUNDARY}</BoundaryNote>
      </SettingCard>

      {/*
        Cosa ORA può fare da sola.

        Compare solo se c'è qualcosa da mostrare. I permessi contestuali
        continuano a nascere nel momento in cui ORA chiede. Il primo pilot
        sorgente ha anche un opt-in esplicito sopra, perché senza una scelta
        dell'utente un worker in background non deve poter concedersi da solo
        il permesso che gli manca.

        Ogni riga è la frase che la persona ha accettato, non lo scope con cui
        è stata salvata. Chi ha letto la lista ha letto i permessi.
      */}
      <SettingCard
        title="Cose che ORA può fare da sola"
        detail="Qui vedi quali permessi sono attivi. Toccare una riga non revoca nulla: per disattivare serve una conferma."
        testID="perm-autonomy"
      >
        {grants.length ? (
          <View>
            {grants.map((g, i) => (
              <ChoiceRow
                key={g.id}
                label={g.scope || 'Un permesso che hai dato a ORA'}
                detail="Attivo · Tocca per gestire il permesso"
                selected={true}
                busy={revoking === g.id}
                onPress={() => {
                  haptic('tap');
                  setPendingRevocation(g);
                }}
                testID={`perm-autonomy-${i}`}
              />
            ))}
          </View>
        ) : (
          <BoundaryNote>Nessun permesso permanente attivo. Puoi aggiungerne uno nella sezione Autonomia.</BoundaryNote>
        )}
      </SettingCard>

      {/*
        La posta, e soltanto come sorgente.

        Nessun conteggio di non letti, nessun elenco di messaggi, nessuna
        casella dentro ORA. Una riga dice che c'è una casella collegata e da
        quanto è stata letta, perché quelle due cose rispondono alla domanda
        che una persona si fa davvero — «ORA sta leggendo la mia posta?» — e
        un elenco di messaggi risponderebbe a una domanda che nessuno ha
        fatto.

        Qui si collega e si vede se è collegata; il resto — sincronizzare
        adesso, scollegare — sta in Connessioni e servizi insieme al
        calendario, che è dove una persona va a cercarlo. La freccia porta lì,
        e lì la casella c'è: due schermate che dicono cose diverse sulla
        stessa connessione sono peggio di una sola che ne dice poche.
      */}
      <SettingCard
        title="Email"
        detail="ORA legge le comunicazioni collegate per capire quando qualcosa cambia o richiede attenzione."
        testID="perm-email"
      >
        <View>
          {mailboxes.length ? (
            mailboxes.map((m, i) => (
              <LinkRow
                key={m.id}
                label={m.what}
                detail={mailboxDetail(m)}
                icon="mail-outline"
                first={i === 0}
                onPress={() => {
                  haptic('tap');
                  router.push('/settings' as any);
                }}
                testID={`perm-email-${m.id}`}
              />
            ))
          ) : (
            <LinkRow
              label="Google Gmail"
              detail={connectingMail ? 'Ti porto su Google…' : 'Non collegato'}
              icon="mail-outline"
              first
              onPress={connectMailbox}
              testID="perm-email-connect"
            />
          )}
        </View>
        <BoundaryNote icon="lock-closed-outline">{MAIL_BOUNDARY}</BoundaryNote>
      </SettingCard>

      <SettingCard title="Documenti" testID="perm-documents">
        <BoundaryNote icon="lock-closed-outline">{DOCUMENT_SCOPE_BOUNDARY}</BoundaryNote>
      </SettingCard>

      <SettingCard
        title="Come entri in ORA"
        detail="I modi che hai per accedere al tuo account. Accedere con Google o Apple non dà a ORA accesso ai loro servizi."
        testID="perm-access"
      >
        <AuthMethods identities={data?.identities || null} onChanged={() => reload({ silent: true })} />
      </SettingCard>

        </>
      ) : null}
      {writeError ? <InlineError>{writeError}</InlineError> : null}
      <Modal
        visible={Boolean(pendingRevocation)}
        transparent
        animationType="fade"
        onRequestClose={() => { if (!revokeInFlight.current) setPendingRevocation(null); }}
      >
        <View style={revokeStyles.backdrop}>
          <View style={[revokeStyles.dialog, { backgroundColor: colors.surface, borderColor: colors.border }]}>
            <Text style={[revokeStyles.title, { color: colors.textPrimary }]}>
              Vuoi davvero revocare questo permesso?
            </Text>
            <Text style={[revokeStyles.description, { color: colors.textSecondary }]}>
              {pendingRevocation?.scope || 'Permesso di ORA'}.
              {' '}Se lo revochi, ORA non potrà più eseguire queste azioni automaticamente.
            </Text>
            <Pressable
              accessibilityRole="button"
              testID="autonomy-revoke-cancel"
              disabled={Boolean(revoking)}
              onPress={() => setPendingRevocation(null)}
              style={[revokeStyles.action, { borderColor: colors.border }]}
            >
              <Text style={{ color: colors.textPrimary, fontWeight: '600' }}>Annulla · Mantieni attivo</Text>
            </Pressable>
            <Pressable
              accessibilityRole="button"
              testID="autonomy-revoke-confirm"
              disabled={Boolean(revoking)}
              onPress={() => {
                if (pendingRevocation) {
                  void revokeGrant(pendingRevocation.capability, pendingRevocation.id);
                }
              }}
              style={[revokeStyles.action, { backgroundColor: colors.errorBg, borderColor: colors.error }]}
            >
              <Text style={{ color: colors.error, fontWeight: '700' }}>
                {revoking ? 'Revoca in corso…' : 'Conferma revoca del permesso'}
              </Text>
            </Pressable>
          </View>
        </View>
      </Modal>
    </SubpageShell>
  );
}

const revokeStyles = StyleSheet.create({
  advancedToggle: { minHeight: 48, borderWidth: 1, borderRadius: 12, padding: 14, alignItems: 'center', justifyContent: 'center' },
  backdrop: { flex: 1, backgroundColor: 'rgba(0, 0, 0, 0.45)', justifyContent: 'center', padding: 24 },
  dialog: { padding: 22, borderRadius: 18, borderWidth: 1, gap: 16, maxWidth: 470, width: '100%', alignSelf: 'center' },
  title: { fontSize: 19, fontWeight: '700' },
  description: { fontSize: 15, lineHeight: 23 },
  action: { minHeight: 50, borderRadius: 12, borderWidth: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 12 },
});
