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
