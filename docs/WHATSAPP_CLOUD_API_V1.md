# ORA su WhatsApp — Cloud API V1 (12 ottobre 2026)

## Stato reale

Integrazione sviluppata in un branch. Finché non sono configurate le credenziali Meta
su Railway, NON è attiva: l'app mostrerà «In attesa di configurazione Meta».
Nessun invio fittizio è previsto.

V1 supporta messaggi di testo WhatsApp, risposte contestuali e collegamento alla
stessa identità, allo stesso AI Core e alla stessa memoria ORA. Non include
ancora vocali/foto su WhatsApp, notifiche proattive, template, chiamate WhatsApp,
lettura di chat private o sincronizzazione di intere conversazioni dell'utente.
Azioni che richiedono sensori del dispositivo rimandano all'app.

## Attivazione con Meta

1. In https://developers.facebook.com/apps/ prepara una app con WhatsApp Business
   Cloud API, portfolio business, account WhatsApp Business e numero dedicato a ORA.
2. Da Meta ricava App Secret, access token server-side e Phone Number ID.
3. Inserisci come segreti nel servizio Railway ora-backend (mai nel codice):
   WHATSAPP_APP_SECRET, WHATSAPP_VERIFY_TOKEN (segregato, creato da ORA e usato
   anche nel webhook Meta), WHATSAPP_ACCESS_TOKEN, WHATSAPP_PHONE_NUMBER_ID,
   WHATSAPP_DATA_KEY (chiave Fernet indipendente).
   Opzionali: WHATSAPP_GRAPH_VERSION=v26.0, WHATSAPP_DISPLAY_NUMBER (cifre con
   prefisso internazionale; permette il pulsante Apri WhatsApp nell'app).
4. Imposta il callback su Meta sul dominio API backend, NON sul frontend:
   https://ora-backend-production-aa56.up.railway.app/api/whatsapp/webhook
   Per la verifica usa WHATSAPP_VERIFY_TOKEN, poi sottoscrivi il campo messages.
5. In ORA vai in Connessioni e servizi → ORA su WhatsApp → Collega WhatsApp.
   Il codice monouso dura 10 minuti. Invialo al numero ufficiale ORA come testo:
   COLLEGA <codice mostrato>. La firma Meta e il codice autenticano l'associazione.
6. Prova un invio reale, un secondo turno nella stessa sessione, accesso
   alle memorie/competenze, revoca e retry usando prima un numero test Meta.

Per generare WHATSAPP_DATA_KEY:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

## Architettura e sicurezza

- GET webhook verifica una challenge Meta; POST verifica X-Hub-Signature-256
  con App Secret, confronta l'ID del numero destinatario e respinge gli eventi
  non firmati senza elaborarli.
- Ogni utente genera un codice in sessione autenticata ORA, poi lo invia dalla
  chat WhatsApp effettivamente posseduta. Il codice viene conservato come HMAC
  ed è consumato una volta; i tentativi di pairing sono limitati.
- Il telefono è cifrato con Fernet e ricercabile tramite HMAC segreto.
  I testi in coda sono cifrati e poi cancellati dopo la consegna, con deduplica
  per ID messaggio Meta; codici TTL 10 min, ricevute TTL 7 giorni.
- Inbox persistente Mongo e worker con recupero al riavvio, lease, ritentativi
  e trasporto HTTP verso la Graph API. Dopo che la risposta è stata preparata,
  un ritentativo di rete non ricalcola l'AI.
- I messaggi passano all'AICoreOrchestrator esistente con lo stesso user_id;
  WhatsApp conserva una sua sessione conversazionale ma riutilizza i dati
  e le memorie personali dell'account.
- La revoca resta possibile anche quando Meta non è configurata o offline.
- Nel caso estremo di crash tra risposta positiva di Meta e scrittura
  delivered nel DB può verificarsi una duplicazione; la semantica non è
  end-to-end exactly once.
- Per invio proattivo sono ancora necessari opt-in/opt-out, messaggi modello
  approvati dove richiesti, rispetto della finestra WhatsApp e dei costi.
- Il trasferimento dei messaggi avviene anche attraverso Meta: predisporre
  informative privacy/trasparenza prima dell'apertura su larga scala.
- In UE l'accesso per assistenti di terze parti è oggetto di misure della
  Commissione (9 giugno 2026). Verificare le policy Meta al momento dell'attivazione.

## Verifica tecnica

Da backend esegui: python -m pytest -q tests/test_whatsapp_cloud_bridge_v1.py

La CI controlla firma, challenge, account isolation, deduplica, risposte
dirette all'AI Core e revoca. Non sostituisce il test live con numero e token
Meta reali. Un account ancora non attivato mostra configured=false su
GET /api/whatsapp/status.

## Abilitazione anticipata della verifica webhook (12 ottobre 2026)

La challenge GET del webhook e' indipendente dall'access token e dall'App Secret:
con la sola variabile WHATSAPP_VERIFY_TOKEN gia' impostata, Meta puo' eseguire
«Verifica e salva» e riceve il valore challenge come prova di possesso dell'URL.
Questo NON abilita il traffico in ingresso: i POST richiedono ancora una firma
Meta valida, l'App Secret, l'access token e un Phone Number ID coerente.
Non disattivare la verifica X-Hub-Signature-256 per far passare i test.


## Aggiornamento audit 13 ottobre 2026 — prevale su limitazioni V1 obsolete

La sezione «Stato reale» sopra documenta la prima V1, **non** lo stato corrente del codice. Sul ramo `staging/cloud` sono ora presenti `whatsapp/media.py`, `whatsapp/parity.py`, `whatsapp/handoff.py`, `whatsapp/alerts.py` e il worker separato degli avvisi. Il bridge gestisce nel codice messaggi di testo, immagini, documenti, vocali trascritti, pin e risposte interattive. Sono implementati anche consenso/revoca per notifiche proattive e controllo dell'approvazione dei template Meta; la riuscita della consegna non è certificata dal solo codice.

**Parità applicativa:** WhatsApp e app usano `AICoreOrchestrator` e il catalogo `ToolRegistry` condivisi. Una nuova skill registrata nell'AI Core non deve essere duplicata nel bridge. Questo garantisce la stessa *scoperta delle capacità*, non la riuscita di tutte le azioni: accesso ai sensori, permessi sul dispositivo, conferme e UI richiedono un collegamento autenticato all'app. Non inventare che WhatsApp abbia GPS live o autorizzazioni del telefono.

**Gate prima di dichiarare l'integrazione completa:** CI sulla revisione corrente; collaudo su numero reale di collegamento, isolamento tra utenti, conversazione multipla, memoria, foto, PDF, vocali, pin e navigazione; operazioni calendario con audit e autorizzazione; prova di opt-in/STOP, template UTILITY Meta APPROVED, ricevute di consegna; simulazione di webhook duplicato, errore rete, cambio account e retry senza doppie azioni. Un manifesto di skill o risposta HTTP 200 del webhook non sostituisce queste prove.

**Vincolo di compatibilità:** mantenere intatta la telefonia Vonage. WhatsApp non sostituisce l'app ORA né costituisce un secondo motore conversazionale.


## 13 ottobre 2026 — avvisi WhatsApp che dicono cosa è successo

Il testo «ORA ha un aggiornamento importante per te. Apri ORA per i dettagli»
era il fallback generico per piani non ordinari o privi di un testo pubblico
concreto. Quel comportamento non soddisfa il requisito di avviso utilizzabile.

### Nuovo comportamento nel backend
- L'avviso usa solo il titolo e il corpo già decisi/verificati dal motore
  canonico `DeliveryService` (nessun secondo motore AI né nuova ricerca
  quando si invia). Se non contengono una **informazione concreta**,
  l'avviso generico non viene emesso. Niente importi, orari, valutazioni o
  collegamenti inventati.
- Un piano **personale** può usare una sintesi pubblica esplicitamente
  dichiarata sicura per la schermata di blocco. Per un piano classificato
  **privato**, la notifica completa richiede sempre il secondo consenso;
  un testo generico o un campo pubblico generato dal modello non è sufficiente.
- In ORA → Connessioni e servizi → WhatsApp, la persona può abilitare
  **Mostra dettagli personali su WhatsApp** dopo aver già attivato gli avvisi.
  È un secondo consenso, **inizialmente disattivato**: consente anche
  `words.title` e `words.body`, che possono includere informazioni riservate.
  Questi contenuti transitano attraverso Meta e possono apparire sulla
  schermata di blocco del dispositivo. Non si deduce tale consenso dal
  semplice collegamento del telefono, dal consenso agli avvisi o da un
  messaggio ambiguo del modello.
- La disattivazione del secondo consenso torna immediatamente alla
  versione pubblica quando consentita; i piani privati senza consenso sono
  bloccati. Il worker rilegge la preferenza prima di ogni invio invece
  di riprodurre una vecchia copia privata accodata. STOP e la
  disattivazione totale degli avvisi azzerano anche il consenso ai dettagli.
- Se la fonte non è più attiva, è muta o non è verificabile, il messaggio
  non viene inviato. Restano deduplicazione, scadenza, isolamento account,
  ricevute firmate e gestione conservativa degli esiti Meta incerti.

### Fuori dalla finestra di WhatsApp
Nelle 24 ore dall'ultimo messaggio autentico la Cloud API può accettare
un testo libero. Fuori finestra un testo libero non è consentito. Per
trasmettere **il contenuto effettivo dell'avviso** serve creare e ottenere
approvazione in WhatsApp Manager per un **template Utility** in italiano
con un singolo placeholder posizionale nel BODY. Esempio da sottoporre
alla revisione di Meta:

```
Nome: ora_avviso_contenuto
Categoria: UTILITY
Lingua: it
Corpo: ORA ti aggiorna: {{1}}
```

Il modello deve essere effettivamente `APPROVED` nel WhatsApp Business
Account della stessa `WHATSAPP_WABA_ID`, con nessun'altra variabile e senza
header multimediale obbligatorio. Il backend verifica in lettura l'oggetto
reale Meta (non solo il nome impostato in Railway). Variabili server:
`WHATSAPP_ALERT_TEMPLATE_NAME=ora_avviso_contenuto` e
`WHATSAPP_ALERT_TEMPLATE_LANGUAGE=it` (oltre al WABA ID esistente).
**Non impostare il nome finché il modello non risulta approvato.**
L'approvazione dipende da Meta e dal contenuto; un template Utility generico
non è necessariamente ammesso per ogni tipo di messaggio AI.

I vecchi template *statici* restano riconosciuti ma non autorizzano più
l'uscita di avvisi vuoti/generici fuori finestra: lo stato visibile spiega
la necessità del template con il dettaglio. Senza approvazione, l'avviso
fuori finestra non parte: viene segnalato come in attesa nel percorso tecnico.
La chiamata di invio HTTP accettata da Meta **non certifica consegna**.

### Accettazione
Verificare su un account e un telefono reale:
1. Avviso ordinario con argomento/novità direttamente nel testo WhatsApp.
2. Avviso classificato privato con solo contenuto pubblico; opt-in dettagli
   attivato => contenuto espanso; revoca => nessun contenuto privato.
3. Avviso con solo parole generiche => nessun messaggio inutile.
4. Invio fuori finestra solo con template Utility `APPROVED` e
   `{{1}}` al posto giusto; statici, parametri extra e template
   non approvati sono respinti.
5. Rilettura della fonte, cambio account, coda, STOP, retry e ricevute
   senza doppie notifiche o divulgazione dopo revoca.

Sono **test funzionali sul codice** finché il test reale WhatsApp/Meta non
viene eseguito; nessuna chiamata Meta con token reali è effettuata dai test.
