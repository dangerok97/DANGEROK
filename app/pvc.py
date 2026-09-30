"""PVC: parte fissa ricavata dai processi verbali di constatazione del Reparto.

Intestazione, apertura, FATTO (ragione, avvertimenti, art. 12 L. 212/2000, periodi, elenco delle sezioni) e SEZIONE
CONCLUSIVA (6-bis, art. 6 c.1 D.Lgs. 218/97, ravvedimento, 5-quater, misure cautelari, allegati, trasmissione) sono
ripetute identiche dal programma: NON passano dall'AI. All'AI spettano solo le sezioni 1-4 (controllo contabile,
controllo sostanziale, violazioni formali, violazioni sostanziali).
Convenzioni: "- " elenco, "-- " sotto-punto, "+ " capoverso rientrato, ">> " riga centrata in grassetto,
"| a | b | c" riga di tabella (la prima riga e' l'intestazione), **grassetto**.
"""
from __future__ import annotations

CAMPI = ("data", "denominazione", "sede", "luogo", "rappresentante", "nascita", "ivi", "residenza", "documento",
         "qualita", "documenti_richiesti", "cf", "piva", "codice_attivita", "data_inizio", "tributo", "ragione", "dal", "al", "direttore",
         "ufficio", "garanzie", "dichiarazione_parte", "fogli", "allegati", "misure_cautelari")

SEZIONI = ("contabile", "sostanziale", "formali", "sostanziali")

_FACOLTA = (
    "farsi assistere durante le operazioni ispettive da un professionista abilitato alla difesa dinanzi agli organi di "
    "giustizia tributaria;",
    "richiedere che l’esame dei documenti amministrativi e contabili venga effettuato nell’ufficio dei verificatori o "
    "presso il professionista che lo assista o la rappresenta;",
    "richiedere, consultare, esaminare, estrarre copia di ogni documento acquisito al controllo previa adozione di "
    "idonee misure cautelative;",
    "muovere rilievi o formulare osservazioni che devono risultare nel presente p.v.;",
    "rivolgersi al Garante del Contribuente che ha sede in Roma, presso l’Agenzia delle Entrate – Direzione Regionale "
    "per il Lazio, qualora ritenga che i militari operanti abbiano agito con modalità non conformi alla legge;",
    "comunicare all’Ufficio impositore entro 60 giorni dalla notifica del p.v. di constatazione redatto a conclusione "
    "dell’intervento, osservazioni e richieste.")

_RAGIONE_BASE = (
    "ad una autonoma attività informativa della Guardia di Finanza diretta a prevenire, ricercare e reprimere le "
    "violazioni alla normativa tributaria, nell’ambito delle generali funzioni attribuite alla Guardia di Finanza ai "
    "fini della ricerca, prevenzione e repressione e violazioni in materia di entrate dello Stato, delle Regioni, degli "
    "Enti locali e dell’Unione Europea, nonché ai fini dell’acquisizione e del reperimento degli elementi utili ai fini "
    "dell’accertamento delle imposte dovute e per la repressione delle violazioni, dal D.Lgs. n. 68/2001, dalla L. n. "
    "4/29 e dal D.P.R. n. 600/73")


def _v(x, cosa: str) -> str:
    x = (x or "").strip() if isinstance(x, str) else x
    return x if x else f"[DA COMPILARE: {cosa}]"


def _sez(testo: str, cosa: str) -> str:
    t = (testo or "").strip()
    return t if t else f"[DA COMPILARE: {cosa}]"


def costruisci(d: dict, verbalizzanti: list[str], impresa: bool = True, sezioni: dict | None = None) -> str:
    sezioni = sezioni or {}
    g = lambda k, cosa: _v(d.get(k, ""), cosa)          # noqa: E731
    ufficio = g("ufficio", "Ufficio dell’Agenzia delle Entrate competente (es. di Viterbo)")
    L: list[str] = []
    a = L.append
    a("PROCESSO VERBALE DI CONSTATAZIONE")
    a(f"Il giorno {g('data', 'data')}, in Tarquinia (VT), via Delle Fiamme Gialle, n. 1, presso gli uffici del Reparto in "
      "intestazione, i sottoscritti verbalizzanti compilano il presente atto:")
    a("")
    a("VERBALIZZANTI")
    for m in verbalizzanti or ["[DA COMPILARE: grado, nome e cognome dei verbalizzanti]"]:
        a(m)
    a("")
    a("PARTE")
    a("")
    ivi = "ivi residente in" if d.get("ivi") else "residente in"
    if impresa:
        nome = g("denominazione", "denominazione della parte")
        a(f"{nome.upper() if d.get('denominazione') else nome}, con sede legale sita in {g('sede', 'sede legale')} e luogo di "
          f"esercizio in {g('luogo', 'luogo di esercizio')}, in atti rappresentata da: "
          f"{g('rappresentante', 'nome e cognome del rappresentante')}, {g('nascita', 'nato a … (prov.) il …')} e {ivi} "
          f"{g('residenza', 'residenza')}, riconosciuto a mezzo {g('documento', 'documento di identità')}, nella sua "
          f"qualità di {g('qualita', 'qualità, es. titolare dell’omonima ditta')}.")
        a(f"codice fiscale: **{g('cf', 'codice fiscale')}**")
        a(f"partita I.V.A.:\t **{g('piva', 'partita IVA')}**")
        a(f"codice attività: **{g('codice_attivita', 'codice attività')}**")
    else:
        a(f"Sig. {g('rappresentante', 'nome e cognome')}, {g('nascita', 'nato a … (prov.) il …')} e {ivi} "
          f"{g('residenza', 'residenza')}, identificato a mezzo {g('documento', 'documento di identità')}, nella sua "
          f"qualità di {(d.get('qualita') or 'diretto interessato').strip()}.")
        a(f"Codice Fiscale: **{g('cf', 'codice fiscale')}**.")
    a("")
    a(">> FATTO")
    a(f"Il {g('data_inizio', 'data di inizio del controllo')}, è stata intrapresa un’attività di controllo fiscale nei "
      f"confronti della parte in rubrica indicata, ai fini dell'{g('tributo', 'tributo, es. I.V.A.')}, ai sensi e per gli "
      "effetti degli artt. 52 e 63 del D.P.R. 26 ottobre 1972, n. 633, 33 del D.P.R. 29 settembre 1973, n. 600, 2 del "
      "D.Lgs 68/2001, nonché della L. n. 4/1929.")
    ragione = (d.get("ragione") or "").strip()
    a("Le ragioni che hanno determinato la scelta del contribuente, sono da ricondursi " + _RAGIONE_BASE
      + (f", nonché {ragione}" if ragione else "") + ".")
    a("I militari verbalizzanti, come dettagliatamente descritto nel p.v. di operazioni compiute, un esemplare del quale è "
      "stato consegnato alla parte, dopo le presentazioni di rito e l’esibizione dell’ordine di controllo (cfr. all. 1), "
      f"hanno invitato la parte ad esibire {g('documenti_richiesti', 'documenti richiesti alla parte')}.")
    a("- secondo quanto disposto dall’art. 52 - quinto comma - del D.P.R. 26 ottobre 1972, n. 633, i libri, i registri, le "
      "scritture ed i documenti di cui venga rifiutata l'esibizione non potranno essere presi in considerazione, a favore "
      "della parte, ai fini dell'accertamento in sede amministrativa e contenziosa; per rifiuto di esibizione si "
      "intendono anche le dichiarazioni di non possedere libri, registri, documenti e scritture e/o la sottrazione di essi "
      "al controllo;")
    a("- rifiutare l’esibizione o comunque impedire l’ispezione delle scritture contabili e dei documenti la cui tenuta e "
      "conservazione sono obbligatorie per legge o dei quali risulta l'esistenza determina l’applicabilità delle sanzioni "
      "previste dai commi 2, 3 e 4 dell'art. 9 del D.lgs. 18 dicembre 1997, n. 471;")
    a("- ai sensi dell'art. 39 - secondo comma, lettera c) - del D.P.R. 29 settembre 1973, n. 600, e dell'art. 55 - secondo "
      "comma - del D.P.R. 26 ottobre 1972, n. 633, se la ditta non ha tenuto, ha rifiutato di esibire o comunque ha "
      "sottratto all'ispezione una o più delle scritture contabili indicate nell'art. 14 del D.P.R. n. 600/73 e "
      "nell'art. 55 del D.P.R. n. 633/72, ovvero le scritture medesime non sono disponibili per causa di forza maggiore, "
      "l'Amministrazione finanziaria può determinare il reddito d'impresa in via induttiva nei modi e nei termini previsti "
      "dall'art. 39 del D.P.R. n. 600/73 e può procedere all'accertamento induttivo dell'I.V.A. nei modi e nei termini "
      "previsti dallo stesso art. 55 del D.P.R. n. 633/72.")
    a("Ai sensi dell’art. 12 della Legge 27/7/2000 n. 212, concernente l’approvazione dello “Statuto dei diritti del "
      "contribuente”, la parte è stata resa edotta, sin dall’inizio del controllo, delle seguenti facoltà:")
    for t in _FACOLTA:
        a("- " + t)
    a("Parimenti, all’atto dell’avvio dell’attività di controllo, la parte è stata altresì resa edotta che il Reparto "
      "presso cui è possibile ottenere informazioni complete in ordine all’attività svolta è la Compagnia di Tarquinia e "
      f"che il Direttore dell’attività ispettiva è il {g('direttore', 'grado, nome e cognome del Direttore del controllo')}.")
    a("In relazione alle garanzie previste dallo Statuto del Contribuente, la parte ha dichiarato:")
    a(f"“””{(d.get('garanzie') or 'NULLA').strip()}”””.")
    a("Le operazioni ispettive hanno preso in esame i seguenti periodi d’imposta:")
    a(f"- ai fini {g('tributo', 'tributo, es. I.V.A.')}, per il periodo:")
    a(f"-- dall’ {g('dal', 'data iniziale')};")
    a(f"-- al {g('al', 'data finale')}.")
    a("Le procedure seguite nell’esecuzione delle attività ispettive sono state analiticamente descritte nel p.v. di "
      "operazioni compiute quotidianamente redatto.")
    a("Il presente atto, nel quale sono raccolti gli esiti delle predette attività ispettive, è articolato nelle seguenti "
      "sezioni:")
    a("- Controllo contabile, in cui sono sinteticamente riportati gli esiti dei controlli sulla regolare istituzione e "
      "conservazione delle scritture e dei documenti;")
    a("- Controllo sostanziale, suddivisa a sua volta nella sottosezione “riscontri di tipo analitico normativo”, nei cui "
      "ambiti vengono sinteticamente esposte le attività poste in essere al fine di riscontrare il rispetto delle "
      "disposizioni dettate dalle leggi d’imposta, la cui violazione comporta sottrazione di materia imponibile;")
    a("- Violazioni formali, in cui sono compendiate le violazioni riscontrate che non comportano sottrazione di materia "
      "imponibile;")
    a("- Violazioni sostanziali, suddivisa a sua volta in sottosezioni raggruppate per periodo d’imposta esaminato e, per "
      "singolo tributo preso in esame, nell’ambito delle quali sono distintamente compendiate le violazioni riscontrate "
      "la cui commissione comporta sottrazione di materia imponibile;")
    a("- Sezione conclusiva, in cui trovano luogo le annotazioni di chiusura e le dichiarazioni di parte.")
    a("")
    a("1.\tCONTROLLO CONTABILE.")
    a(_sez(sezioni.get("contabile"), "esito dei controlli sulle scritture: registri e libri esaminati, regolarità"))
    a("")
    a("2.\tCONTROLLO SOSTANZIALE.")
    a(_sez(sezioni.get("sostanziale"), "riscontri di coerenza e riscontro analitico normativo con i fatti accertati"))
    a("")
    a("3.\tVIOLAZIONI FORMALI.")
    a(_sez(sezioni.get("formali"), "periodi d’imposta e violazioni formali (o: «Nei periodi d’imposta in esame non si "
                                   "rilevano violazioni di carattere formale.»)"))
    a("")
    a("4.\tVIOLAZIONI SOSTANZIALI.")
    a(_sez(sezioni.get("sostanziali"), "violazioni per periodo d’imposta e tributo, con tabella «Descrizione della "
                                       "violazione constatata | Fonte normativa della violazione»"))
    a("")
    a("5.\tSEZIONE CONCLUSIVA.")
    a("In merito alle operazioni di controllo ed alle sue conclusioni, espresse nel presente atto, la parte, in rubrica "
      "compiutamente generalizzata, dichiara quanto segue:")
    a(f"“”” {_v(d.get('dichiarazione_parte'), 'dichiarazione della parte, testuale')} ”””.")
    a("La documentazione esaminata viene lasciata in custodia alla parte con l’obbligo di conservarla inalterata sino "
      "alla definizione del contesto e, comunque, nel rispetto dei termini previsti dall’art. 22 del D.P.R. n. 600/73, "
      "richiamato anche dall’art. 39 del D.P.R. n. 633/72.")
    a("Resta comunque impregiudicata la facoltà dell’Amministrazione finanziaria di eseguire altre indagini e di "
      "formulare, eventualmente, in base alla sopravvenuta conoscenza di nuovi elementi, ulteriori rilievi fino alla "
      "scadenza dei termini previsti dall’art. 57 del D.P.R. n. 633/72 e dall’art. 43 del D.P.R. n. 600/73.")
    a("Si dà atto che, con riferimento alle violazioni constatate, le sanzioni pecuniarie e le eventuali sanzioni accessorie "
      f"saranno irrogate dall’{ufficio}, competente all’accertamento del tributo cui le stesse violazioni si riferiscono, "
      "mediante notifica di apposito atto di contestazione, ai sensi dell’art. 16 del D. Lgs. n. 472/1997, ovvero con "
      "atto contestuale all’avviso di accertamento o di rettifica a norma del successivo art. 17.")
    a("La parte è stata resa edotta:")
    a("- delle disposizioni contenute nell’articolo 6-bis, secondo cui:")
    a("-- tutti gli atti autonomamente impugnabili dinanzi agli organi della giurisdizione tributaria sono preceduti, a "
      "pena di annullabilità, da un contraddittorio informato ed effettivo;")
    a("-- per consentire il contraddittorio, l’amministrazione finanziaria comunica al contribuente, con modalità idonee a "
      "garantirne la conoscibilità, lo schema di atto, assegnando un termine non inferiore a sessanta giorni per "
      "consentirgli eventuali controdeduzioni ovvero, su richiesta, per accedere ed estrarre copia degli atti del "
      "fascicolo;")
    a(f"- della facoltà di cui all’art. 6, comma 1, del D.lgs. n. 218/1997, di richiedere all’{ufficio} sulla base delle "
      "risultanze dello stesso processo verbale e con apposita istanza, la formulazione di una proposta di accertamento ai "
      "fini dell’eventuale adesione;")
    a("- della facoltà di regolarizzare spontaneamente propri errori e/o omissioni accedendo al ravvedimento operoso che "
      "consente di ricorrere al predetto istituto anche dopo l’inizio di accessi, ispezioni, verifiche e altre attività "
      "amministrative di accertamento di cui l’autore della violazione o i soggetti solidalmente obbligati abbiano avuto "
      "formale conoscenza, nonché di definire le violazioni già constatate, secondo i diversi termini, requisiti ed "
      "effetti previsti dall’art. 13 del D.lgs. 18 dicembre 1997, n. 472.")
    a("+ Al riguardo, in sede di avvio dell’intervento, al contribuente è stato precisato che il pagamento e la "
      "regolarizzazione non limitano né inibiscono l’avvio e la prosecuzione delle attività ispettive né la conseguente "
      "verbalizzazione degli illeciti riscontrati.")
    a("+ Per le rilevate violazioni costituenti reato, sarà interessata, con separata trattazione, la competente Autorità "
      "giudiziaria.")
    a("- della facoltà di prestare adesione al contenuto integrale del verbale ai sensi dell’articolo 5-quater del D.lgs. "
      "n. 218/1997 con riferimento alle constatazioni in esso elevate per violazioni sostanziali e di obblighi contabili "
      "ad esse prodromiche (ossia funzionali all’evasione del tributo cui le violazioni sostanziali si riferiscono) "
      "riferite a [IRPEF ed IRES e relative ritenute e addizionali, IVA, contributi previdenziali, imposte sostitutive, "
      "Irap, Ivie, Ivafe, imposta di registro, ipotecaria/catastale e imposte sulle successioni/donazioni, imposte sulle "
      "assicurazioni, crediti di imposta e agevolativi], relativamente a tutti i periodi d’imposta contenuti nel verbale "
      "stesso.")
    a("+ Tale facoltà è esercitabile entro trenta giorni (30) dalla consegna del verbale, mediante comunicazione "
      "all’Ufficio/agli Uffici dell’Agenzia delle entrate territorialmente competente/i (per annualità) e a questo "
      "Reparto. Il contribuente può optare per l’adesione al processo verbale di constatazione presentando la suddetta "
      "comunicazione senza condizioni oppure condizionandola alla rimozione di errori manifesti, che dovranno essere "
      "puntualmente individuati, quali incongruenze, inesattezze, errori di calcolo, individuabili in maniera evidente e "
      "manifesta nel presente processo verbale, che abbiano inciso in particolare sulla quantificazione degli importi "
      "dovuti. In tale eventualità, questo Reparto può correggere gli errori indicati entro i successivi dieci giorni, "
      "mediante rettifica del presente verbale, informandone immediatamente il contribuente e il/i competente/i "
      "Ufficio/i dell’Agenzia delle entrate.")
    a("+ Entro i sessanta giorni successivi alla comunicazione del contribuente o all’aggiornamento del processo "
      "verbale di constatazione il/i competente/i Ufficio/i dell’Agenzia delle entrate, nel caso in cui ritenga "
      "applicabile la procedura, provvederà all’emanazione di apposito atto di definizione dell’accertamento parziale.")
    a("+ In presenza dell’adesione al processo verbale, le sanzioni si applicano nella misura di un sesto del minimo e le "
      "somme dovute risultanti dall’atto di definizione dell’accertamento parziale devono essere versate nei termini e "
      "con le modalità di cui all'articolo 8 del D.lgs. n. 218/97. Sull’importo delle rate successive alla prima sono "
      "dovuti gli interessi al saggio legale calcolati dal giorno successivo alla data di notifica dell'atto di "
      "definizione.")
    a("Si dà atto che:")
    a("- la parte non ha nulla da eccepire in merito alla condotta ed agire dei militari operanti e di tutti gli "
      "intervenuti firmatari degli atti;")
    a("- le operazioni di cui al presente atto si sono protratte per il tempo strettamente necessario allo svolgimento "
      "delle stesse.")
    misure = (d.get("misure_cautelari") or "").strip()
    if misure:
        a(f"Si dà altresì atto che {misure}")
    else:
        a("Si dà altresì atto che non sussistendo i presupposti previsti dalla circolare del Comando Generale della "
          "Guardia di Finanza – III Reparto Operazioni - Ufficio Tutela Entrate n. 0104496/2010, datata 07.04.2010, non "
          "si ritiene di dover richiedere all’Ufficio competente, ai sensi dell’articolo 22 del D.lgs. 472/97, "
          "l’adozione di eventuali misure cautelari.")
    a("Fanno parte integrante del presente atto gli allegati citati nel medesimo.")
    a(f"Il presente atto, che si compone di nr. {g('fogli', 'numero fogli')} fogli e di n. "
      f"{g('allegati', 'numero allegati')} allegati, viene redatto in due esemplari di cui:")
    a("- uno viene consegnato alla parte;")
    a("- uno viene conservato agli atti del Reparto operante;")
    a("La trasmissione all’Ufficio Territoriale dell’Agenzia delle Entrate Territorialmente competente, avverrà con "
      "procedura telematica.")
    a("Fatto, letto e chiuso in data e luogo come sopra, il presente atto viene confermato e sottoscritto dai soli "
      "verbalizzanti presenti alla chiusura dell’atto e dalla parte.")
    a("I VERBALIZZANTI    LA PARTE")
    return "\n".join(L)


_RE_MARCA = __import__("re").compile(r"^\s*={2,}\s*(CONTABILE|SOSTANZIALE|FORMALI|SOSTANZIALI)\s*={2,}\s*$", __import__("re").M)


def separa_sezioni(testo: str) -> dict:
    """Divide la risposta dell'AI nei quattro blocchi marcati «=== CONTABILE ===» ecc. Vuoto se mancano le marche."""
    parti = _RE_MARCA.split(testo or "")
    return {parti[i].lower(): parti[i + 1].strip() for i in range(1, len(parti) - 1, 2)}
