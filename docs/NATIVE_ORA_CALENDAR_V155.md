# Calendario ORA v155 — primo calendario, provider facoltativi

## Richiesta
La persona deve poter usare ORA per gli appuntamenti anche senza Google, Apple o altri calendari. Aggiungere un account esterno deve arricchire il calendario ORA, mai sostituirlo.

## Stato verificato prima dell'intervento
Esisteva già una persistenza locale nel Life Graph (`attributes.kind=home_manual`) con creazione, modifica, rimozione, owner isolation, rilettura dalla chat e idempotenza. Era però esposta principalmente in un form nella Home e in una lista degli impegni dei prossimi sette giorni. L'esperienza comunicava ancora troppo spesso che servisse Google.

## Percorso introdotto
- **Calendario ORA è predefinito**: `/agenda` è una vista del mese navigabile su web e telefono; selezione del giorno, conteggio impegni e `Nuovo evento` usano gli stessi endpoint e documenti locali già esistenti.
- **API del mese**: `GET /api/agenda/month?month=YYYY-MM`; restituisce tutti i giorni, eventi owner-scoped e tipi di origine `ora/google/apple/other`, con fuso locale dell'utente. Nessun token Google/Apple richiesto.
- **Fonti opzionali**: gli eventi dei connector disponibili si sovrappongono nella vista senza cambiare l'identità degli eventi ORA. Una fonte esterna disconnessa non è più mostrata nella vista mensile; l'archivio non viene eliminato.
- **Provenienza e permessi**: la lista indica sempre la fonte. Un nodo Apple o di altra origine di sola lettura può essere consultato, ma non induce cancellazioni o modifiche Google, né mostra una finta promessa di scrittura.
- **Home**: il suggerimento di collegare Google presenta prima il calendario ORA e l'azione di apertura, lasciando la connessione esterna facoltativa.
- **Nessuna copia silenziosa**: creare/modificare/rimuovere un evento ORA agisce sul solo calendario ORA. Collegare Google o Apple **non** attiva per implicito esportazione automatica, sincronizzazione bidirezionale o inviti a terzi.

## Limiti dichiarati
- Google è un connettore già implementato; Apple richiede autorizzazione EventKit su build nativa iOS/iPadOS, non nel browser. Non si promettono connessioni ad altri provider senza connettore dedicato.
- Il mese mostra le date di inizio degli appuntamenti. La proiezione può essere ampliata successivamente per eventi ricorrenti e spans multi-giorno senza scritture distruttive.
- L'aggregazione usa nodi Life Graph normalizzati già importati e applica ownership. Una connessione che non ha ancora sincronizzato eventi non genera appuntamenti fittizi.
- La verifica reale del collegamento Google/Apple su dispositivo resta distinta dai test sintetici.

## Regressioni
`backend/tests/test_ora_native_calendar_v155.py`: account vuoto, evento locale senza OAuth, fonti opzionali, filtro post-disconnessione, evento Apple in sola lettura, isolamento account, mese invalido. `frontend/src/components/calendar/nativeMonth.test.ts`: mesi, anni bisestili, selezione fonte. Pipeline CI TypeScript, unit, iOS export e build Railway.
