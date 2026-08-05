# Google Calendar — Privacy

## Principio

ORA sincronizza su Google **solo** i campi necessari per un appuntamento utilizzabile. Il testo completo del documento, referti, allegati e dati sanitari dettagliati **non** vengono inviati.

## Cosa viene inviato (v1)

- Titolo (per documenti medici: fisso `Visita specialistica`)
- Descrizione minima (max ~240 caratteri non medici; per medical: blurb generico)
- Data/ora inizio e fine + timezone
- Luogo (se presente)
- Link Maps (se presente)
- Priorità / urgenza come riga breve
- Riferimento ID documento ORA (non il contenuto)
- Proprietà privata: `ora_event_id`, `ora_document_id`, `ora_candidate_id`

## Cosa non viene inviato

- Testo estratto / OCR completo
- Referti e dettagli clinici
- Codici fiscali / identificativi sensibili nel body Google
- Allegati
- Note utente interne non necessarie
- Token OAuth (restano solo nel vault backend)

## Conferma utente

La sync Google avviene solo se l’utente sceglie **ORA + Google Calendar** dopo la conferma del candidato evento. **Salva solo in ORA** non chiama Google.

## Token

- Access/refresh token cifrati nel vault (`TOKEN_VAULT_KEY` / `OAUTH_TOKEN_ENCRYPTION_KEY`)
- Mai restituiti al frontend
- Mai stampati nei log
- Revoca: Disconnetti in Impostazioni + possibilità di revoca lato Google

## Login vs Calendar

Il login Google all’account ORA **non** richiede scope calendario. L’autorizzazione Calendar è un flusso esplicito separato.
