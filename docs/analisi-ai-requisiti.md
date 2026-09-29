# L'AI come analista di controllo: requisiti (da un esempio d'uso dell'utente, anonimizzato)

L'AI non si limita a redigere: **ragiona sul caso**, come un collega che lavora insieme all'operatore. Oltre alla
Circolare 1/2018 deve applicare la normativa e la prassi sostanziale (imposte dirette, IVA, bonus edilizi, regimi).

## Comportamenti attesi (dall'esempio: professionista con Superbonus e sconto in fattura del 100%)
1. **Acquisizione a lotti, senza conclusioni premature**: riceve un primo gruppo di fatture, le censisce e dichiara
   esplicitamente cosa manca ("non faccio il totale finche' non arrivano le altre 4").
2. **Estrazione dai documenti**: per ogni fattura numero, data, cessionario, regime fiscale (es. RF01 ordinario /
   RF19 forfettario), tipo di operazione (es. sconto art. 121), imponibile, cassa previdenziale (con tipo cassa TCxx e
   aliquota), IVA, totale.
3. **Conteggi complessivi con quadratura**: totali per imponibile/cassa/IVA/documento, riconciliati al centesimo con
   i totali documento; credito d'imposta (es. 110% dello sconto), maggiorazione (es. 10%), importo che concorre al reddito.
4. **Individuare la dichiarazione giusta**: distinguere originaria e integrativa, scegliere quella di riferimento e
   registrare la scelta come *assunzione da confermare*; identificare il quadro corretto in base al regime (RE ordinario,
   LM forfettario, ecc.).
5. **Confronto numerico rigo per rigo**: dichiarato -> dovuto -> differenza; dire se una componente e' gia' compresa in un
   altro rigo o risulta omessa, e cosa serve per stabilirlo (es. elenco completo delle fatture attive dell'anno con
   incassi: criterio di cassa).
6. **Chiedere il documento successivo** in modo mirato (quale, per quale anno, quale quadro).
7. **Notare anomalie** nei dati (es. tipo cassa previdenziale incoerente con l'albo del professionista) e segnalarle
   senza affermare che siano errori.

## Regole di progetto che ne derivano
- **I numeri li calcola il codice, non l'AI**: la tabella sotto va rifatta in modo deterministico, per fattura e in centesimi,
  con la politica di arrotondamento esplicitata e la riconciliazione ai totali documento. Esempio del perche': in
  quell'esempio 86.432,12 + 4.321,61 = 90.753,73, ma l'imponibile IVA riportato e' 90.753,72 (differenza di 1 centesimo
  tipica dell'arrotondamento per singola fattura).
- **Ogni affermazione normativa cita una fonte** della base normativa locale (versionata, verificata dall'operatore):
  norma, circolare, risposta a interpello, prassi di categoria. Nessuna affermazione "a memoria": senza fonte va marcata
  *non verificata*.
- **Nessun documento grezzo verso l'AI**: le fatture (XML FatturaPA o PDF) e le dichiarazioni si leggono in locale;
  all'AI arrivano solo campi strutturati e testi gia' pseudonimizzati (vedi `app/privacy`).
- **Ragionamento visibile e tracciabile**: assunzioni, calcoli, fonti e dubbi restano registrati nella pratica e
  confluiscono, dopo revisione, nei prospetti allegati (es. "cfr. all. N") e nelle "situazioni rilevanti" del PVOC/PVV.
- Il regime del soggetto (ordinario / forfettario / altro) si ricava dai documenti e guida quali controlli applicare.
