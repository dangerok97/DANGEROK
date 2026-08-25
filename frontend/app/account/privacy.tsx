/**
 * Privacy e dati — what ORA knows, and how you change it.
 *
 * This page deliberately does not try to be a second Vita. Since PX1.5, the
 * place where a person reads and corrects what ORA has understood about their
 * life is Vita itself, and building a rival inspector here would split the
 * same job across two screens and make neither authoritative. What belongs in
 * an account screen is the map: where each kind of knowledge lives, and which
 * lever removes it.
 *
 * There is no export and no account deletion in ORA today. Neither is
 * mentioned — a disabled button, or a line promising one later, is a claim
 * made on the page a person visits precisely to find out what is true.
 */
import { View } from 'react-native';
import { useRouter } from 'expo-router';

import { haptic } from '@/src/utils/haptic';
import {
  BoundaryNote,
  CALENDAR_WRITE_BOUNDARY,
  DOCUMENT_SCOPE_BOUNDARY,
  LinkRow,
  SettingCard,
  SubpageShell,
} from '@/src/components/account';

export default function PrivacyScreen() {
  const router = useRouter();
  const go = (href: string) => () => {
    haptic('tap');
    router.push(href as any);
  };

  return (
    <SubpageShell
      title="Privacy e dati"
      subtitle="Cosa ORA sa di te, e come puoi cambiarlo."
      testID="account-privacy"
    >
      <SettingCard
        title="Cosa ORA sa di te"
        detail="Tutto quello che ORA ha capito della tua vita sta in un posto solo, dove puoi leggerlo e correggerlo."
        testID="privacy-knowledge"
      >
        <View>
          <LinkRow
            label="Vita"
            detail="Gli ambiti della tua vita, e cosa ORA ha capito di ciascuno"
            icon="layers-outline"
            first
            onPress={go('/(tabs)/contesti')}
            testID="privacy-open-vita"
          />
          {/*
            The older memory screen is still the only place that lists durable
            knowledge item by item. It is a detail view of the same material
            Vita presents, so it stays reachable and stops being a destination.
          */}
          <LinkRow
            label="Memoria di ORA"
            detail="L’elenco puntuale di ciò che ORA ricorda"
            icon="sparkles-outline"
            onPress={go('/(tabs)/memoria')}
            testID="privacy-open-memoria"
          />
          <LinkRow
            label="I tuoi documenti"
            detail="I file che hai caricato e cosa ORA ne ha ricavato"
            icon="document-text-outline"
            onPress={go('/(tabs)/documenti')}
            testID="privacy-open-documenti"
          />
        </View>
      </SettingCard>

      <SettingCard
        title="Togliere accesso a ORA"
        detail="Ogni servizio collegato si può scollegare quando vuoi: ORA smette di leggerlo da quel momento."
        testID="privacy-revoke"
      >
        <View>
          <LinkRow
            label="Connessioni e servizi"
            detail="Collega o scollega i servizi"
            icon="link-outline"
            first
            onPress={go('/settings')}
            testID="privacy-open-connections"
          />
          <LinkRow
            label="Permessi e accessi"
            detail="Posizione, calendario e modi di accedere"
            icon="shield-checkmark-outline"
            onPress={go('/account/permessi')}
            testID="privacy-open-permissions"
          />
          <LinkRow
            label="Preferenze ORA"
            detail="Decidi se ORA può leggere i tuoi documenti"
            icon="options-outline"
            onPress={go('/account/preferenze')}
            testID="privacy-open-preferences"
          />
        </View>
      </SettingCard>

      <SettingCard title="Quello che ORA non fa da sola" testID="privacy-boundaries">
        <BoundaryNote>{CALENDAR_WRITE_BOUNDARY}</BoundaryNote>
        <BoundaryNote icon="lock-closed-outline">{DOCUMENT_SCOPE_BOUNDARY}</BoundaryNote>
      </SettingCard>
    </SubpageShell>
  );
}
