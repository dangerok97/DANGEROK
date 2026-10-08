# ORA — Verifica multi-skill del cervello AI · Fase 1

Data: 8 ottobre 2026.

## Scopo

L'AI deve scegliere e usare più skill necessarie, attendere un risultato
osservato prima di segnarle riuscite, fermarsi onestamente a un errore e
riprendere un piano già iniziato dopo un chiarimento.

## Scenari obbligatori nel test di integrazione

1. **Successo di due strumenti:** il primo controllo legge il calendario,
   il secondo legge il percorso, il modello risponde dopo entrambi; non
   è autorizzata una conclusione anticipata.
2. **Secondo strumento fallito:** il calendario ha risposto, il percorso no;
   il piano non è completo e la risposta deve dichiarare il blocco.
3. **Continuità su due turni:** dopo il primo strumento, ORA domanda un
   dettaglio mancante e conserva riferimento al piano e outcome osservati;
   il turno successivo riprende con la seconda skill, senza ripetere
   quella già conclusa.

## Ambito della prova

Il test esegue il vero loop cognitivo, il registro di capacità, lo stato di
sessione e il meccanismo di persistenza dei piani. Le decisioni del modello
AI e le risposte dei provider sono script controllati; non sono prove di
routing dal modello live, del servizio Mapbox o di Google Calendar collegato.
Nessun dato personale, chiamata o scrittura esterna.

File: backend/tests/test_phase1_multiskill_lifecycle_v119.py.
CI: job Backend (compileall + pytest), blocco Calendar command target.

## Condizioni ancora aperte

La Fase 1 resta aperta fino a prova con modello e provider veri di:
- scelta autonoma della catena di skill su richieste non preparate;
- ripresa dopo errori transitori, riavvii e conferme utente;
- verifica dell'effetto finale oltre al successo tecnico degli adapter;
- uso sicuro delle fonti, rispetto dell'autorità e report leggibile.

Lo sviluppo automatico orario resta disattivato: il proprietario decide
quando lavorare e quando fermare il progetto.
