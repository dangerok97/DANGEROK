import React from 'react';

import { PublicLegalPage, type LegalSection } from '@/src/components/legal/PublicLegalPage';

const sections: LegalSection[] = [
  {
    title: '1. Uso del servizio',
    paragraphs: [
      'ORA è un assistente personale digitale. Puoi usarla per ricevere informazioni, organizzare attività, collegare servizi compatibili e delegare controlli o preparazioni supportate dall’app.',
      'Usando ORA accetti di utilizzare il servizio in modo lecito e di non tentare di accedere a dati, account o funzioni che non ti appartengono o per cui non hai autorizzazione.',
    ],
  },
  {
    title: '2. Account e servizi collegati',
    paragraphs: [
      'Se colleghi servizi esterni, sei responsabile di utilizzare account che sei autorizzato a collegare. Le autorizzazioni concesse a ORA possono essere revocate secondo le impostazioni del servizio e dell’app.',
      'Le condizioni dei servizi esterni continuano ad applicarsi alle attività svolte su tali piattaforme.',
    ],
  },
  {
    title: '3. Intelligenza artificiale e accuratezza',
    paragraphs: [
      'ORA utilizza sistemi di intelligenza artificiale e fonti collegate per produrre risposte e valutazioni. Questi sistemi possono sbagliare, essere incompleti o non disporre di dati aggiornati.',
      'Quando una conclusione dipende da informazioni esterne, ORA dovrebbe distinguere ciò che è osservato, stimato o non verificato. Per decisioni importanti resta opportuno verificare le informazioni rilevanti.',
    ],
  },
  {
    title: '4. Automazioni e azioni',
    paragraphs: [
      'ORA può programmare controlli e, quando una funzione lo consente, preparare o eseguire azioni. Le azioni con effetti esterni possono richiedere un’autorizzazione specifica o una conferma.',
      'Una programmazione non equivale a un risultato: ORA deve considerare conclusa un’attività solo quando dispone di evidenza sufficiente dell’esito.',
    ],
  },
  {
    title: '5. Funzioni non garantite',
    paragraphs: [
      'La disponibilità di connettori, provider esterni, dati in tempo reale e funzioni di terze parti può cambiare o interrompersi. ORA non garantisce la disponibilità continua di servizi esterni né può sostituirsi alle loro condizioni operative.',
    ],
  },
  {
    title: '6. Responsabilità dell’utente',
    paragraphs: [
      'Sei responsabile delle informazioni che inserisci e delle decisioni che prendi sulla base del servizio. Non utilizzare ORA come unico strumento per emergenze, sicurezza personale o decisioni professionali che richiedono verifica specialistica.',
    ],
  },
  {
    title: '7. Sospensione e modifiche',
    paragraphs: [
      'Le funzioni possono essere modificate, sospese o aggiornate per motivi tecnici, di sicurezza o di prodotto. Quando possibile, ORA deve rappresentare in modo chiaro quando una connessione o una funzione non è disponibile.',
    ],
  },
  {
    title: '8. Privacy',
    paragraphs: [
      'Il trattamento dei dati personali è descritto nell’Informativa sulla privacy pubblicata da ORA. Le autorizzazioni dei servizi collegati restano separate dall’accettazione di questi termini.',
    ],
  },
  {
    title: '9. Aggiornamenti dei termini',
    paragraphs: [
      'Questi termini possono essere aggiornati quando cambiano il servizio o le relative condizioni operative. La data di ultimo aggiornamento è indicata in alto.',
    ],
  },
];

export default function TermsPage() {
  return (
    <PublicLegalPage
      title="Termini di servizio"
      subtitle="Le condizioni essenziali per utilizzare ORA e le sue funzioni collegate."
      updated="7 ottobre 2026"
      sections={sections}
    />
  );
}
