# Catalogo Vision 75 — collaudo del candidato

Richiesta: espandere il catalogo oltre le 25 famiglie, preservando camera, flash,
zoom, schema fissato e percorsi già approvati. Pacchetto: 75 famiglie e 347 gruppi
principali; 50 famiglie e 223 gruppi sono nuovi. Non sono 75 modelli di marca
verificati né 75 percorsi didattici: i percorsi controllati restano 25.

## Controlli eseguiti prima del candidato finale

- Preflight: 75 nomi canonici univoci, 50 aggiunte, alias coerenti. Fingerprint
  canonico dei 25 manifest storici identico a quello registrato prima dell'edit.
- Workflow Vision `38211826294`, job catalogo: 208 test PASS su MongoDB temporaneo
  reale. Copre inserimento da un catalogo con 25 voci, riuso fra utenti senza
  generazione, promozione controllata e conservazione di versioni/private/ritirati.
- TypeScript, test di geometria e build web del primo candidato superati;
  la sua verifica browser completa è separata e non presunta qui.
- Ispezione locale dei renderer: individuato clipping prospettico su alcuni
  gruppi larghi. Corretto il calcolo di adattamento nel renderer, senza modificare
  le geometrie salvate: il massimo ingrandimento prospettico viene incluso nel
  limite di scala sia per l'insieme sia per il componente focalizzato.
- Esecuzione locale conclusiva: **231 controlli Node PASS**, inclusi tutti i
  75 schemi e ogni componente in primo piano su tre dimensioni e tre rotazioni.
  Lo zoom richiesto dall'utente può intenzionalmente ingrandire oltre il bordo.

## Candidato da verificare prima del rilascio

Correzione grafica integrata in `31de66c2522581b8e903afc1b490ad6f20fcf10b`.
Il successivo commit di questo rapporto avvia i gate remoti sullo stesso codice.
Occorre leggere tutti gli esiti finali: Vision, CI generale, Situation e Mobile.
Occorre ispezionare screenshot del build esportato, non soltanto la geometria
locale. Merge e pubblicazione backend/web non sono dichiarati completati in
questo rapporto preliminare: saranno registrati nella PR #213 con SHA e stato
terminale Railway.

## Limiti delle evidenze

I controlli del catalogo usano un database temporaneo. Le prove browser usano
l'app compilata con il sistema di autenticazione/camera del solo harness CI.
Non costituiscono una prova sul sensore o sul flash fisico di un iPhone, né una
nuova scansione autenticata dell'account dell'utente in produzione.

Le primitive e i gruppi sono schematici, anche per oggetti con forme complesse.
Una verifica geometrica non dimostra la correttezza degli interni nascosti.
Le 50 aggiunte non ricevono un percorso animato inventato. Le fonti presenti
supportano principi generali o esempi costruttivi, non certificazioni del modello
fotografato. Nessuna fotografia personale è nel pacchetto condiviso.

Nessuna nuova dipendenza runtime o modifica ai controlli della fotocamera.
Strumenti di preparazione isolati sul ramo QA e non distribuiti.
