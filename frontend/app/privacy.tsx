import React from 'react';

import { PublicLegalPage, type LegalSection } from '@/src/components/legal/PublicLegalPage';

const sections: LegalSection[] = [
  {
    title: '1. Chi è ORA e a cosa serve',
    paragraphs: [
      'ORA è un assistente personale digitale che può aiutarti a organizzare informazioni, impegni e attività e, quando abiliti servizi collegati, a usare quei dati per offrirti risposte, promemoria, controlli e suggerimenti pertinenti.',
      'Questa informativa descrive in modo sintetico quali dati possono essere trattati nell’app e con quali finalità.',
    ],
  },
  {
    title: '2. Dati che puoi fornire direttamente',
    paragraphs: [
      'Quando usi ORA puoi inserire messaggi, preferenze, informazioni del profilo, luoghi, impegni, documenti e altri contenuti necessari alle funzioni che scegli di utilizzare.',
      'ORA tratta questi contenuti per rispondere alle tue richieste e per mantenere la continuità delle funzioni che hai attivato.',
    ],
  },
  {
    title: '3. Servizi collegati',
    paragraphs: [
      'Puoi scegliere di collegare servizi esterni. La connessione è facoltativa e può essere revocata.',
    ],
    bullets: [
      'Google Calendar: ORA può leggere gli eventi autorizzati e, solo quando previsto e consentito, creare o modificare eventi.',
      'Gmail: ORA può leggere le comunicazioni autorizzate per capire quando qualcosa cambia o richiede attenzione. Il contenuto completo di un messaggio viene letto solo quando necessario per una funzione autorizzata.',
      'Posizione del dispositivo: se autorizzata, può essere usata per presenza, luoghi, spostamenti e contesto. ORA non deve inventare una posizione quando non è disponibile.',
      'Servizi bancari collegati: se abilitati, ORA può leggere i dati consentiti dal relativo connettore. Le operazioni che muovono denaro richiedono controlli e autorizzazioni separati.',
    ],
  },
  {
    title: '4. Come usiamo i dati',
    paragraphs: [
      'I dati sono usati per fornire le funzioni richieste, sincronizzare i servizi collegati, mantenere il contesto necessario, rilevare cambiamenti utili, eseguire controlli programmati e migliorare la continuità delle risposte.',
      'ORA può usare modelli di intelligenza artificiale per interpretare richieste e informazioni. Le azioni che producono effetti nel mondo reale sono soggette alle autorizzazioni previste dall’app.',
    ],
  },
  {
    title: '5. Dati sensibili e minimizzazione',
    paragraphs: [
      'ORA cerca di usare solo i dati necessari alla funzione in corso. Quando possibile conserva riferimenti, metadati o sintesi invece di copie integrali di contenuti esterni.',
      'Le credenziali e i token OAuth dei servizi collegati non devono essere mostrati nell’interfaccia e sono gestiti separatamente dai normali dati applicativi.',
    ],
  },
  {
    title: '6. Conservazione e controllo',
    paragraphs: [
      'La durata di conservazione dipende dal tipo di dato e dalla funzione. Le informazioni temporanee possono essere rimosse o concluse quando non servono più; i dati di account e le informazioni persistenti restano finché necessari al servizio o finché non vengono eliminati secondo le funzioni disponibili.',
      'Scollegare un servizio impedisce nuove letture da quel servizio, ma non equivale automaticamente alla cancellazione di informazioni già elaborate o salvate in ORA.',
    ],
  },
  {
    title: '7. Sicurezza',
    paragraphs: [
      'Applichiamo controlli di accesso, separazione per utente e misure tecniche per limitare l’accesso ai dati collegati. Nessun sistema è completamente privo di rischio, ma ORA è progettata per evitare accessi tra account diversi e per non esporre token o credenziali nelle normali superfici utente.',
    ],
  },
  {
    title: '8. Le tue scelte',
    paragraphs: [
      'Puoi revocare connessioni esterne dalle impostazioni disponibili nell’app. Puoi inoltre interrompere l’uso di ORA e richiedere la gestione o cancellazione dei dati attraverso i canali di assistenza indicati nell’app e nella schermata di consenso OAuth.',
    ],
  },
  {
    title: '9. Modifiche a questa informativa',
    paragraphs: [
      'Questa informativa può essere aggiornata quando cambiano le funzioni o i servizi collegati. La data di ultimo aggiornamento è indicata in alto.',
    ],
  },
];

export default function PrivacyPage() {
  return (
    <PublicLegalPage
      title="Informativa sulla privacy"
      subtitle="Come ORA tratta i dati necessari per offrirti assistenza, automazioni e connessioni ai servizi che scegli di collegare."
      updated="7 ottobre 2026"
      sections={sections}
    />
  );
}
