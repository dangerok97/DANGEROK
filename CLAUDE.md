# Dangerok - istruzioni permanenti per chi lavora su questo repository

## Regola dell'utente: ogni atto condiviso serve a istruire l'app
Ogni volta che l'utente (militare della Guardia di Finanza, Compagnia di Tarquinia) condivide in chat un atto
(PVOC, PVV, PVC, CNR, invito, scheda Allegato 23, altro) si deve **usare per istruire l'app**, non solo leggerlo:

1. **Estrarre il testo** nello scratchpad (mai nel repository): `.docx` con python-docx, `.doc` con lo script di lettura OLE
   (cp1252/utf-16 dalla piece table), come gia' fatto in precedenza.
2. **Capire il metodo**, non giudicarlo: gli esempi servono per lessico, modus operandi, struttura e ragionamento, NON per
   cercare errori. La Circolare 1/2018 resta la fonte di verita' per fasi e contenuti.
3. **Scrivere una scheda anonimizzata** in `app/knowledge/metodo/<slug>.md` (formato sotto). Senza nomi, codici fiscali, partite
   IVA, indirizzi, numeri di documento, importi o date riferibili a persone reali; i brani di stile sono formule ricorrenti con
   i dati sostituiti da segnaposto tra «» (es. «persona», «ente», «importo»).
4. **Se la struttura dell'atto e' fissa** (formule identiche da un caso all'altro) aggiornare anche i generatori
   deterministici (`app/pvoc.py`, `app/invito_word.py`, modelli in `app/wordtemplates/`) e i formati Word (`app/atti_word.py`),
   verificando con test che il risultato sia identico all'esempio.
5. **Aggiornare** `app/knowledge/playbook_reparto.md` se emerge una regola generale nuova.
6. `pytest` deve restare verde: c'e' un test che impedisce di committare dati personali nei file di conoscenza.
7. Riferire all'utente, in breve, cosa l'app ha imparato e cosa non e' stato possibile (es. formati illeggibili).

## Formato di `app/knowledge/metodo/<slug>.md`
```
---
tipo: precedente            # precedente | spunto
atto: PVOC                  # PVOC | PVV | PVC | CNR | (vuoto per gli spunti generali)
titolo: Titolo senza nomi
tag: parole chiave su fattispecie, tributo, istituto
---
## Scheda
FATTISPECIE / STRUTTURA / RAGIONAMENTO OPERATIVO / COME SI CONSTATA / SPUNTI OPERATIVI / FORMULE E LESSICO
## Brani di stile
Frasi e capoversi tipici, anonimizzati.
```

## Vincoli di riservatezza (dell'utente)
- Gli atti reali non entrano mai nel repository ne' nei test: solo schede anonimizzate e lessico.
- Finche' il Comando non autorizza, l'app si prova solo con dati inventati.
- Chiavi e segreti mai in chat, nel repository o nei log; se l'utente incolla una chiave, dire di ruotarla e non ripeterla.
- Nessun dato personale verso l'AI senza pseudonimizzazione automatica (fail-closed).

## Convenzioni tecniche
- Python 3.11, FastAPI, SQLAlchemy; test con `python -m pytest -q` (devono passare prima di ogni push).
- Branch di sviluppo: `claude/fiscal-verification-automation-yev7yy`. Commit chiari; non aprire PR se non richiesto.
- Il Word degli atti deve essere identico agli esempi del Reparto (A4, Arial, margini, stemma, intestazione).
