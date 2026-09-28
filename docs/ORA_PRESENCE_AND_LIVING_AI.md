# Presenza e AI continua di ORA — stato e progetto, 28 settembre 2026

## Cosa esiste davvero

- Expo SDK 54: `presenceTask.ts` riceve eventi di posizione e geofence;
  `presenceRuntime.ts` chiede i permessi, registra al massimo 18 luoghi e
  riconcilia lo stato all'apertura. La posizione in background funziona solo
  nella build nativa e con permesso appropriato.
- `places/presence.py` decide entrata e uscita tramite due cerchi, due
  osservazioni e permanenza: 180 secondi in ingresso, 300 in uscita. Il server
  conserva le sessioni, le visite e i tempi. Il telefono può perdere eventi;
  per questo l'apertura dell'app acquisisce una nuova posizione.
- `places/service.py` aggrega osservazioni non attribuite in candidati; il
  modello può decidere se chiedere «Che posto è?», ma solo la persona può
  trasformare un candidato in luogo confermato. VITA mostra la domanda.
- `llm/manager.py` supporta già `openai` tra i provider, con preferenza tramite
  `LLM_PROVIDER`; `llm/providers/openai_provider.py` usa una chiave server.
  `conversation_engine/ai_core` contiene già capacità governate per memoria,
  web, calendario, piani e telefonate; `ambient/runtime.py` possiede un worker
  persistente con lease e risveglio su lavori dovuti. Home ha azioni rese da
  dati (`HomeAction`), non richiede codice mobile nuovo per ogni pulsante.

## Correzioni di questa iterazione

1. I task nativi tentano l'invio della coda mentre il sistema li ha svegliati.
   Se la rete non risponde i dati restano in coda; l'apertura dell'app prova di
   nuovo. La consegna è idempotente tramite `event_id` già esistente.
2. Un evento geofence non viene più scambiato per la coordinata del suo centro.
   Viene usata soltanto una posizione reale recente e coerente con il verso
   della transizione. In mancanza, il normale flusso GPS e la riconciliazione
   successiva sono la fonte di verifica. Anche dopo l'invio il server applica
   più campioni, distanza e permanenza.
3. La schermata VITA avvia una sola revisione AI per montaggio quando esistono
   candidati non ancora valutati e la posizione è consentita, poi aggiorna le
   domande. Nessuna identità del posto è dedotta automaticamente.

## Il prodotto richiesto

**Una conoscenza personale verificabile.** A ogni affermazione la memoria
associa fonte, data, livello di certezza e possibilità di correzione. Quando
un'informazione nuova contraddice una vecchia (per esempio un numero attribuito
a due persone), ORA chiede quale tenere; non modifica una conferma precedente
in silenzio. Il modello consulta memoria e documenti pertinenti a ogni
compito: non viene riaddestrato continuamente sul telefono.

**Ricerca esterna al momento giusto.** ORA dispone già di una capacità di
ricerca web. Offerte, traffico, regole e novità hanno una data di controllo,
fonti esibibili e una scadenza del risultato; una pagina esterna è evidenza,
non un'istruzione da eseguire. Ricerche ricorrenti nascono da un obiettivo
attivo e dal consenso, con quote e frequenza limitate.

**Attività quando l'app è chiusa.** I sensori nativi possono svegliare il
telefono, ma non garantiscono letture ininterrotte. Il backend deve possedere
promemoria, code, ritentativi, deduplicazione e motivi di risveglio. Una
telefonata o un intervento su terzi conserva mandato, autorizzazione e prova
dell'esito; il worker non riceve un permesso generale solo perché sta girando.

**Interfaccia che cresce.** Il modello propone una struttura dichiarativa:
`titolo`, `spiegazione`, `evidence_refs`, `action_id`, `parametri`, `scadenza`.
Il server accetta solo `action_id` presenti nel registro delle capacità
autorizzate e solo parametri validati; il frontend rende la proposta con gli
`HomeAction`/componenti già distribuiti. Un nuovo percorso di studio può essere
un piano e una scheda con azioni esistenti. Una funzione che richiede codice
nuovo, permessi OS o un nuovo provider passa da test e rilascio dell'app.
Mai eseguire JavaScript generato dal modello o aprire URL arbitrari come
comandi privilegiati.

## Integrazione OpenAI richiesta

L'account/abbonamento ChatGPT non è una credenziale che ORA possa riutilizzare
automaticamente. La via implementabile è l'API OpenAI sul backend con chiave
server, costo e quota propri. L'adattatore esistente permette una prima
attivazione configurando e verificando `OPENAI_API_KEY`, `OPENAI_MODEL` e
`LLM_PROVIDER=openai`; mantenere il fallback gestito dal Provider Manager.
Per evolvere la conversazione testuale usare Responses API con tool espliciti,
stato della conversazione controllato da ORA e ricerca web quando necessaria.
Per voce naturale usare una sessione Realtime e delegare le azioni al backend
di ORA, che resta responsabile dei permessi. Conservare dati personali e
documenti nella memoria governata di ORA, selezionando soltanto il contesto
necessario al compito.

## Sequenza di rilascio e prove necessarie

1. **Presenza nativa:** test iOS/Android su dispositivi reali, permessi
   While Using/Always, app chiusa o terminata, assenza rete, GPS impreciso,
   geofence sovrapposti, batteria, logout e doppia consegna. Misurare ritardo
   tra evento OS e sessione confermata; non promettere tempo reale assoluto.
2. **OpenAI come motore principale:** controllare chiave, quota, modello e
   configurazione nell'ambiente Railway; test di conversazione con memoria,
   tools e fallback su account sintetico prima del passaggio per tutti. La
   sola presenza del nome `OPENAI_API_KEY` nelle variabili non prova una chiave
   valida né l'utilizzo corrente di OpenAI.
3. **Apprendimento governato:** test su contraddizioni, correzioni, revoca
   posizione, provenienza, cancellazione e prompt injection da fonti aperte.
4. **Schede e pulsanti generati:** registro di azioni, validatore di schema,
   ciclo di vita delle proposte, CTA con etichette reali e test di autorità.
   Nuove esperienze come studio o spostamento si montano su capacità esistenti;
   nuove capacità richiedono release e test.
5. **Continuità:** worker backend con rate limit per utente, scadenza delle
   ricerche, budget per modello e notifiche governate; osservabilità di
   `fonte → decisione → proposta → azione → esito` senza testo personale nei log.

## Confini della verifica attuale

I test locali dimostrano la logica corretta dei callback e il type check. Non
sono disponibili in questo ambiente un dispositivo iOS/Android reale, una
istanza Mongo locale o una verifica del contenuto segreto delle variabili
Railway; nessuna chiamata OpenAI a pagamento o chiamata telefonica reale è
stata eseguita. Il modello OpenAI non è stato commutato nell'ambiente remoto.
