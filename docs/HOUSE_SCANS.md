# Casa: scansione e pianta in ORA

## Funzione implementata

Ingresso VITA → Casa (`/casa`). L'app iOS 17+ verifica il supporto LiDAR con
RoomPlan e chiede la fotocamera solo quando la persona avvia il rilievo.
È possibile acquisire più stanze consecutive, salvare sul proprio account,
consultare la pianta 2D e verificare le lunghezze delle pareti.

Le misure corrette a mano conservano il valore della scansione e la data di
verifica. La correzione di una quota non deforma automaticamente la geometria.
Le dimensioni sono stime, senza promessa di precisione certificata.
Non sono ancora inclusi esportazione CAD, computi, scansione Android o
lettura automatica della pianta da parte del planner generale di ORA.

## App e web mobile

Il sito rileva iPhone/iPad solo per proporre un passaggio esplicito a
`ora://casa?scan=1`. L'app verifica la capacità effettiva del dispositivo.
Se occorre il login, la destinazione viene conservata; il link non contiene
token o altri dati dell'account. La scansione avviene nella build nativa.
Safari/PWA ed Expo Go non contengono il modulo RoomPlan.

Le piante salvate sono visibili accedendo allo stesso account dal web o
dall'app. Il ritorno in primo piano aggiorna l'elenco. Un invio non riuscito
resta riprovabile nella schermata aperta; chiuderla perde il rilievo non
ancora salvato. Non viene dichiarato un backup offline inesistente.

## Dati e API

- `POST /api/house-scans`: `{ title?, capture }`, ritorna `{ scan, created }`.
- `GET /api/house-scans?limit=50&offset=0`: riepiloghi paginati.
- `GET /api/house-scans/{id}`: pianta completa dell'owner autenticato.
- `PATCH /api/house-scans/{id}`: revisione richiesta, titolo, nomi stanze o
  quote verificate; la geometria originale non è modificabile.
- `DELETE /api/house-scans/{id}?revision=N`: eliminazione con revisione.

Lo schema `HouseCapture` v1 contiene stanze, pareti, porte, finestre,
aperture, pavimenti e oggetti; dimensioni in metri e matrici column-major.
Vengono limitati payload a 2 MB, stanze a 50 ed elementi complessivi a 2000.
Il server rifiuta JSON ambiguo, numeri non finiti, matrici non rigide,
identificativi duplicati e riferimenti estranei. Le risposte private sono
`no-store`. L'indice owner + capture_id rende idempotente il retry della
stessa acquisizione senza annullare correzioni successive.

La collezione Mongo `house_scans` è aggiuntiva. Non vengono memorizzati foto
o video dal nuovo flusso. `source=apple_roomplan` è una dichiarazione del
client, esplicitata da `provenance.source_attestation=client_reported`.

## Distribuzione iPhone

1. Collegare un progetto Expo/EAS reale e impostare il suo UUID in
   `EXPO_PUBLIC_EAS_PROJECT_ID`. Non usare un UUID inventato.
2. Accedere all'account Expo e all'account Apple Developer nei loro strumenti
   ufficiali; credenziali, certificati e profili non vanno nel repository.
3. Verificare la disponibilità del bundle identifier attuale
   `com.emergent.oradecisionengine.b7escs` nel team Apple scelto prima di firmare.
4. Creare una build iOS con il profilo EAS appropriato (`preview` per i device
   registrati o `production` per TestFlight). Il profilo `preview` è già
   collegato all'URL del backend cloud corrente; per `production` impostare
   anche questo ambiente e verificare la configurazione di autenticazione
   nativa. Expo Go non basta.
5. Installare la build e provare su iPhone 16 Pro: primo consenso camera,
   annullamento, una stanza, stanze successive, perdita rete/retry,
   apertura dal sito mobile, salvataggio e rilettura con lo stesso account.
6. Solo quando la build è installabile, impostare per il build web
   `EXPO_PUBLIC_IOS_ROOMPLAN_READY=1` e `EXPO_PUBLIC_IOS_INSTALL_URL` a un vero
   link HTTPS TestFlight o App Store. Il sito continua altrimenti a indicare
   che l'installazione non è ancora disponibile.

Chi possiede già una build ORA con il modulo può espandere «Ho già installato
ORA» e aprire l'app anche durante il collaudo. Una vecchia build senza il
modulo mostra esplicitamente la necessità di aggiornarla.

## Verifiche

Il workflow `.github/workflows/house-scans.yml` separa contratti backend/TS,
interfaccia web Chromium/WebKit e compilazione iOS senza firma su macOS.
Il simulatore verifica compilazione e bridge, non un rilievo LiDAR reale.

Verifiche locali completate prima del rilascio:

- TypeScript e lint dei nuovi file: PASS.
- Geometria 2D: cinque casi PASS.
- Adapter nativo opzionale: cinque casi PASS.
- Handoff web e destinazione post-login: PASS.
- API e persistenza simulata: 53 test PASS, senza test saltati; non è una
  prova di salvataggio su Mongo di produzione.
- Compatibilità dipendenze Expo 54: PASS.
- Export web e prebuild iOS/autolinking: PASS.
- Browser Chromium 138, schermo iPhone a 390 px: 5/5 PASS su geometria e
  account sintetici (handoff, quote/rinomina/eliminazione, revisioni,
  ritorno Email e callback Google). Screenshot controllati visivamente.
- Audit della cronologia Git: PASS, nessun pattern di segreto rilevato.

La prima CI remota ha superato contratti, controlli generali e 10/10 prove
Chromium/WebKit. Il job iOS ha richiesto le patch Expo 54.0.37 e
expo-constants 18.0.14 prima di compilare: entrambe sono state allineate,
con nuovo export web e 5/5 prove mobile locali riusciti. Il bridge Swift
esplicita inoltre i callback senza valore di ritorno e i timeout sul main actor.

La seconda esecuzione, sul commit `68013e53`, è conclusa con successo:
contratti, 10/10 prove browser e compilazione dell'app iOS senza firma su
macOS. Il job iOS `119195953835` ha superato controllo dipendenze, prebuild,
autolinking, CocoaPods e `xcodebuild` dello schema `ORA` per iOS Simulator.
Il log completo è conservato nell'artifact del workflow per sette giorni.
Anche CI generale e Loyalty sono PASS sullo stesso commit.

Questa verifica dimostra che l'app e il modulo nativo compilano; non è
un'installazione sul telefono né una scansione LiDAR. Firma Apple e prova
fisica non risultano completate: nessun esito sintetico le sostituisce.

## Rilascio cloud: blocco esterno del 21 ottobre 2026

Il codice della funzione è salvato su `staging/cloud`, commit
`68013e53b0310d982aeba73fd5f3676c71fef600`. La seconda CI ha confermato
53 test API e 10/10 prove Chromium/WebKit. Anche la
[CI generale](https://github.com/dangerok97/DANGEROK/actions/runs/39592280005)
e il [workflow Loyalty](https://github.com/dangerok97/DANGEROK/actions/runs/39592280101)
sono conclusi con successo sullo stesso commit. Il
[workflow Casa](https://github.com/dangerok97/DANGEROK/actions/runs/39592280014)
è interamente PASS, inclusa la compilazione iOS senza firma.

Il rilascio è stato preparato sui servizi esistenti `ora-web` e `ora-backend`
di ORA Staging, ambiente `production`. La patch
`c5eb5e8e-d3fb-41ad-8674-ffc16c3d5007` modifica soltanto la sorgente dei due
servizi, fissata a quel commit; nessuna modifica a volumi, database o segreti.
L'ultima lettura riuscita mostra la patch `STAGED`, senza un nuovo deployment.
Due tentativi di applicarla e il tentativo diretto sul servizio backend
hanno restituito `-32603 Internal error`; successivamente anche le letture
di stato hanno restituito lo stesso errore.

La [pagina ufficiale Railway](https://status.railway.com/) segnala un
incidente grave con dashboard/API/CLI indisponibili e nuove build sospese
in tutte le regioni (aggiornamento 21 ottobre, 09:28 UTC). Il guasto è la
spiegazione supportata per il blocco attuale; non ci sono elementi per
attribuirlo alle credenziali GitHub dell'utente.

Controlli HTTP pubblici durante il blocco: web `/healthz` e backend
`/api/health` rispondono 200, con database disponibile; `/api/house-scans`
risponde ancora 404. Il 200 della route web `/casa` è il fallback della SPA
precedente e non prova la pubblicazione della nuova schermata.

Alla ripresa del servizio, rileggere prima patch e deployment per escludere
un'applicazione tardiva, poi applicare soltanto il rilascio già verificato.
Confermare commit effettivo, salute dei servizi e risposta 401 dell'API Casa
senza sessione. Non dichiarare la funzione online prima di queste verifiche.

## Riferimenti primari

- [Apple RoomPlan](https://developer.apple.com/augmented-reality/roomplan/)
- [Apple: stanze e strutture](https://developer.apple.com/videos/play/wwdc2023/10192/)
- [Apple: iPhone 16 Pro e LiDAR](https://support.apple.com/it-it/121031)
- [Expo: codice nativo personalizzato](https://docs.expo.dev/workflow/customizing/)
