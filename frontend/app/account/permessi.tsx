/**
 * Permessi e accessi — what ORA may use, and how you get in.
 *
 * Two different questions that a settings screen usually runs together. What
 * ORA is allowed to reach is one thing; how this account is opened is another,
 * and signing in with Google says nothing about whether ORA can read a Google
 * calendar. They are separate sections here for that reason.
 *
 * The page shows a control only where pressing it changes a permission.
 * Location is a real stored preference, so it is a choice. Calendar reading is
 * granted by connecting the calendar, so it reports its state and sends you to
 * the place that changes it. Calendar writing asks every time and cannot be
 * pre-authorised, so it is a sentence, not a switch — the absence of a toggle
 * there is the honest part.
 */
import { useCallback, useEffect, useState } from 'react';
import { View } from 'react-native';
import { useRouter } from 'expo-router';

import { api } from '@/src/api/client';
import { humanizeError } from '@/src/utils/errors';
import { haptic } from '@/src/utils/haptic';
import { useInflight } from '@/src/shell';
import {
  AuthMethods,
  BoundaryNote,
  CALENDAR_WRITE_BOUNDARY,
  ChoiceRow,
  DOCUMENT_SCOPE_BOUNDARY,
  InlineError,
  LinkRow,
  PartialNote,
  SettingCard,
  SubpageShell,
  connectedServices,
  connectionLabel,
  useAccount,
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
    detail: 'Serve solo a capire se sei a casa o fuori. Nessun tracciamento continuo.',
  },
];

type PresenceState = {
  supported: boolean;
  reason?: string;
  enabled: boolean;
  background: 'granted' | 'denied' | 'undetermined';
};

export default function PermessiScreen() {
  const router = useRouter();
  const { data, loading, error, reload } = useAccount();
  const [location, setLocation] = useState<LocationMode | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [writeError, setWriteError] = useState<string | null>(null);
  const [presence, setPresence] = useState<PresenceState | null>(null);

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

  const setMode = useCallback((next: LocationMode) => guard(async () => {
    haptic('tap');
    setBusy(`loc_${next}`);
    setWriteError(null);
    try {
      const res = await api.locationSetPreference(next);
      setLocation(res.mode === 'while_using' ? 'while_using' : 'off');
      haptic('success');
    } catch (e: any) {
      haptic('error');
      setWriteError(humanizeError(e));
    } finally {
      setBusy(null);
    }
  }), [guard]);

  const calendars = (snapshot?.services || []).filter((s) => s.id.endsWith('calendar'));
  const calendarConnected = connectedServices(calendars).length > 0;

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
              detail={connectionLabel(s.state)}
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

      {writeError ? <InlineError>{writeError}</InlineError> : null}
    </SubpageShell>
  );
}
