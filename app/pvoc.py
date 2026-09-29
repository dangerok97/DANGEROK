"""PVOC del primo giorno: testo fisso e struttura ricavati dal p.v. di operazioni compiute del Reparto.

Le formule (Statuto del contribuente, art. 6-bis, ravvedimento, avvertimenti art. 52 c.5, ecc.) sono quelle degli atti
del Reparto e NON passano dall'AI: il programma le ripete identiche e inserisce solo i dati del caso.
I dati mancanti diventano [DA COMPILARE: ...]. Le note {{SPIEGA: ...}} dicono da dove viene ogni blocco.
Convenzioni del testo: "- " punto elenco, "-- " sotto-punto, "+ " capoverso rientrato, **grassetto**.
"""
from __future__ import annotations

CAMPI = ("data", "titolo", "denominazione", "luogo", "rappresentante", "nascita", "ivi", "residenza", "documento",
         "qualita", "cf", "piva", "codice_attivita", "data_invito", "ora_presentazione", "ragione", "tributo", "dal",
         "al", "direttore", "assistente", "garanzie", "delega", "documenti", "dichiarazione_finale", "ora_fine",
         "fogli", "allegati")


def _v(x, cosa: str) -> str:
    x = (x or "").strip() if isinstance(x, str) else x
    return x if x else f"[DA COMPILARE: {cosa}]"


def primo_giorno(d: dict, verbalizzanti: list[str], impresa: bool = True) -> str:
    g = lambda k, cosa: _v(d.get(k, ""), cosa)          # noqa: E731
    parte_nome = g("denominazione", "denominazione della parte")
    titolo = (d.get("titolo") or "Il Sig.").strip()
    assistente = (d.get("assistente") or "").strip()
    docs = [x.strip() for x in (d.get("documenti") or "").splitlines() if x.strip()]
    prefisso = "D.I. " if impresa else ""
    ivi = "ivi residente in" if d.get("ivi") else "residente in"
    L = []
    a = L.append
    a("PROCESSO VERBALE DI OPERAZIONI COMPIUTE")
    a(f"Il giorno {g('data', 'data')} in Tarquinia, presso gli uffici del Reparto in intestazione, viene compilato il "
      "presente atto. {{SPIEGA: Apertura del p.v. del primo giorno (Circolare 1/2018, Vol. II, P. III, cap. 4 §4, con "
      "rinvio al cap. 3 §3): data e luogo; la formula è quella usata dal Reparto.}}")
    a("")
    a("VERBALIZZANTI")
    for m in verbalizzanti or ["[DA COMPILARE: grado, nome e cognome dei verbalizzanti]"]:
        a(m)
    a("")
    a("PARTE")
    a("")
    a(f"{prefisso}“{parte_nome.upper() if d.get('denominazione') else parte_nome}”, con luogo di esercizio in {g('luogo', 'luogo di esercizio')}, in atti "
      f"rappresentata da: {g('rappresentante', 'nome e cognome del rappresentante')}, "
      f"{g('nascita', 'nato a … (prov.) il …')} e {ivi} {g('residenza', 'residenza')}, riconosciuto a mezzo "
      f"{g('documento', 'documento di identità: tipo, numero, ente e data di rilascio')}, nella sua qualità di "
      f"{g('qualita', 'qualità (es. titolare dell’omonima ditta)')}. {{{{SPIEGA: Identificazione della parte e di chi la "
      "rappresenta: i dati anagrafici e del documento vanno riportati dal documento esibito, non sono ricavabili "
      "dall'AI.}}")
    a(f"codice fiscale: **{g('cf', 'codice fiscale')}**")
    a(f"partita I.V.A.:\t **{g('piva', 'partita IVA')}**")
    a(f"codice attività: **{g('codice_attivita', 'codice attività')}**")
    a("")
    a("FATTO")
    a("")
    a(f"Si premette che in data {g('data_invito', 'data di notifica dell’invito')} è stato notificato alla parte un "
      "biglietto d’invito a presentarsi in data odierna, al fine di avviare un controllo ai fini delle imposte sui "
      "redditi, dell’I.V.A. e degli altri tributi, ai sensi e per gli effetti degli artt. 52 e 63 del D.P.R. 26 ottobre "
      "1972, n. 633, 33 del D.P.R. 29 settembre 1973, n. 600, art. 2 del D.Lgs 68/2001, nonché della L. n. 4/1929. "
      "{{SPIEGA: Richiama l'invito a presentarsi già predisposto (All. 14 del Vol. IV); le norme sono le stesse "
      "dell'invito.}}")
    a("")
    a(f"{titolo} {g('rappresentante', 'nome e cognome')} alle ore {g('ora_presentazione', 'ora di presentazione')}, si "
      "è presentato in data odierna, pertanto i verbalizzanti gli hanno notificato l’ordine di apertura del controllo, "
      "mediante consegna di una copia dello stesso (vgs. allegato n.1).")
    a("La parte, quindi, veniva resa edotta, ai sensi delle disposizioni di cui alla Legge 27 luglio 2000, n. 212 "
      "(Statuto dei Diritti del Contribuente): {{SPIEGA: Informativa dei diritti obbligatoria il primo giorno "
      "(art. 12 L. 212/2000; art. 7 c. 2 lett. a; art. 6-bis). Testo fisso del Reparto.}}")
    a(f"- che l’attività ispettiva è avviata d’iniziativa ed è volta al controllo della parte, in quanto "
      f"{g('ragione', 'ragione del controllo: riscontri già in possesso del Reparto')}; {{{{SPIEGA: Le ragioni vengono "
      "dalla scheda di preparazione (Allegato 23) e dai riscontri del Reparto: le scrive l'operatore.}}")
    a("+ nonché ai fini dell’acquisizione e del reperimento degli elementi utili ai fini dell’accertamento delle "
      "imposte dovute e per la repressione delle violazioni, dal D.Lgs. n. 68/2001, dalla L. n. 4/29 e dal D.P.R. "
      "n. 600/73;")
    a("- della facoltà di:")
    for t in ("farsi assistere da un professionista abilitato alla difesa innanzi agli organi di giustizia tributaria "
              "nonché di farsi assistere ovvero rappresentare da un procuratore generale o speciale;",
              "richiedere che l’esame dei documenti amministrativo-contabili venga effettuato presso gli uffici dei "
              "verificatori o presso il professionista che la assiste o la rappresenta;",
              "muovere rilievi e/o formulare osservazioni, dei quali sarà dato atto nell’apposito p.v. di verifica;",
              "rivolgersi al Garante del contribuente che ha sede in Roma, presso l’Agenzia delle Entrate – Direzione "
              "Regionale per il Lazio nei casi in cui ritenga che i verificatori stiano procedendo con modalità non "
              "conformi alla legge;",
              "richiedere, consultare, esaminare, estrarre copia di ogni documento acquisito ai fini della verifica, "
              "previa adozione di idonee misure cautelative;",
              "esercitare ogni altro diritto riconosciuto al contribuente dalla normativa vigente, richiedendo "
              "all’occorrenza ogni utile informazione al riguardo al capo pattuglia ed al direttore della verifica;"):
        a("-- " + t)
    a("- delle disposizioni contenute nell’articolo 6-bis, secondo cui:")
    a("-- tutti gli atti autonomamente impugnabili dinanzi agli organi della giurisdizione tributaria sono preceduti, "
      "a pena di annullabilità, da un contraddittorio informato ed effettivo;")
    a("-- per consentire il contraddittorio, l’amministrazione finanziaria comunica al contribuente, con modalità "
      "idonee a garantirne la conoscibilità, lo schema di atto, assegnando un termine non inferiore a sessanta giorni "
      "per consentirgli eventuali controdeduzioni ovvero, su richiesta, per accedere ed estrarre copia degli atti del "
      "fascicolo;")
    a("- che la permanenza dei verificatori presso la sede non può superare i 30 giorni lavorativi, prorogabili per "
      "ulteriori 30 giorni nei casi di particolare complessità dell’indagine e motivati dal Comandante del Reparto. "
      "Gli operatori possono ritornare presso la sede del contribuente decorso tale periodo, per esaminare le "
      "osservazioni e le richieste eventualmente presentate dal contribuente dopo la conclusione delle operazioni di "
      "verifica ovvero, previo assenso motivato del Comandante del Reparto, per specifiche ragioni;")
    a("- che il Reparto operante presso cui è possibile ottenere informazioni complete in ordine all’attività ispettiva "
      f"è la Compagnia di Tarquinia e che il Direttore dell’attività di controllo è il "
      f"{g('direttore', 'grado, nome e cognome del Direttore del controllo')}. {{{{SPIEGA: Indicazione del Reparto e del "
      "Direttore del controllo prevista dall'art. 7 c. 2 lett. a L. 212/2000 (Vol. II, P. III, cap. 4 §3).}}")
    a("L’attività ispettiva riguarderà l’esecuzione di un controllo fiscale:")
    a(f"- ai fini {g('tributo', 'tributo, es. I.V.A.')}, per il periodo:")
    a(f"-- dall’ {g('dal', 'data iniziale del periodo')};")
    a(f"-- al {g('al', 'data finale del periodo')}.")
    a("")
    a("In relazione alle succitate garanzie previste dallo Statuto dei Diritti del Contribuente, la parte dichiara: "
      f"“{g('garanzie', 'dichiarazione della parte, testuale')}”. {{{{SPIEGA: La dichiarazione va trascritta "
      "testualmente come resa dalla parte.}}")
    if assistente:
        a(f"Si dà atto che per le operazioni di cui al presente atto è presente {assistente} quale assistente di "
          "fiducia della parte.")
    a("Gli operanti, inoltre, hanno reso edotta la parte che ha facoltà di:")
    a("- assistere ovvero farsi rappresentare anche nelle successive fasi dell’attività ispettiva;")
    a("- avvalersi della possibilità di regolarizzare spontaneamente propri errori e/o omissioni accedendo al "
      "ravvedimento operoso che consente di ricorrere al predetto istituto anche dopo l’inizio di accessi, ispezioni, "
      "verifiche e altre attività amministrative di accertamento di cui l’autore della violazione o i soggetti "
      "solidalmente obbligati abbiano avuto formale conoscenza, nonché di definire le violazioni già constatate, "
      "secondo i diversi termini, requisiti ed effetti previsti dall’art. 13 del D.Lgs. 18 dicembre 1997, n. 472. "
      "{{SPIEGA: Ravvedimento operoso: informativa richiesta dal Vol. II, P. III, cap. 3 (art. 13 D.Lgs. 472/97).}}")
    a("+ Al riguardo, al contribuente è stato precisato che il pagamento e la regolarizzazione non limitano né "
      "inibiscono l’avvio e la prosecuzione delle attività ispettive né la conseguente verbalizzazione degli illeciti "
      "riscontrati;")
    a("- richiedere, al termine delle operazioni ispettive, al competente Ufficio finanziario, ai sensi dell’art. 6, "
      "comma 1, del D.Lgs. n. 218/97, con apposita istanza in carta libera, la formulazione della proposta di "
      "accertamento, ai fini dell’eventuale definizione (c.d. “accertamento con adesione”).")
    a("I militari anzidetti facevano, altresì, rilevare che:")
    a("- secondo quanto disposto dall’art. 52 - quinto comma - del D.P.R. 26 ottobre 1972, n. 633, i libri, i "
      "registri, le scritture ed i documenti di cui venga rifiutata l'esibizione non potranno essere presi in "
      "considerazione, a favore della parte, ai fini dell'accertamento in sede amministrativa e contenziosa; per "
      "rifiuto di esibizione si intendono anche le dichiarazioni di non possedere libri, registri, documenti e "
      "scritture e/o la sottrazione di essi al controllo;")
    a("- rifiutare l’esibizione o comunque impedire l’ispezione delle scritture contabili e dei documenti la cui "
      "tenuta e conservazione sono obbligatorie per legge o dei quali risulta l'esistenza determina l’applicabilità "
      "delle sanzioni previste dai commi 2, 3 e 4 dell'art. 9 del D.Lgs. 18 dicembre 1997, n. 471;")
    soggetto = "l’impresa individuale" if impresa else "il contribuente"
    a("- ai sensi dell'art. 39 - secondo comma - lettera c), del D.P.R. 29 settembre 1973, n. 600, e dell'art. 55 - "
      f"secondo comma - del D.P.R. 26 ottobre 1972, n. 633, {soggetto} non ha tenuto, ha rifiutato di esibire o "
      "comunque ha sottratto all'ispezione una o più delle scritture contabili indicate nell'art. 14 del D.P.R. "
      "n. 600/73 e nell'art. 55 del D.P.R. n. 633/72, ovvero le scritture medesime non sono disponibili per causa di "
      "forza maggiore, l'Amministrazione finanziaria può determinare il reddito d'impresa in via induttiva nei modi e "
      "nei termini previsti dall'art. 39 del D.P.R. n. 600/73 e può procedere all'accertamento induttivo dell'I.V.A. "
      "nei modi e nei termini previsti dallo stesso art. 55 del D.P.R. n. 633/72. {{SPIEGA: Avvertimenti sulle "
      "conseguenze del rifiuto di esibizione: testo fisso del Reparto.}}")
    if assistente:
        a("")
        a("In relazione a quanto sopra evidenziato la parte dichiara: "
          f"“{g('delega', 'eventuale delega all’assistente, testuale')}”.")
    a("")
    a("La parte veniva, quindi, invitata ad esibire tutta la documentazione fiscale afferente l’attività esercitata; "
      "aderendo all’invito, esibiva quanto segue:")
    for x in docs or ["[DA COMPILARE: elenco dei documenti esibiti, uno per riga, con numeri e date]"]:
        a("- " + x)
    a("Tutta la documentazione esibita viene conservata presso questo Reparto per la successiva disamina.")
    a("La parte, in merito all’attività svolta dai verbalizzanti, ha inteso spontaneamente dichiarare:")
    a(f"“{g('dichiarazione_finale', 'dichiarazione finale della parte, testuale (o: nulla da dichiarare)')}”.")
    a("Si dà atto che:")
    for t in ("le operazioni di servizio si sono protratte per il tempo strettamente necessario allo svolgimento delle "
              "stesse;",
              "non sono stati arrecati danni a persone e/o cose mobili e/o immobili;",
              "nulla è stato asportato al di fuori di quanto sopra elencato;",
              "non ha nulla da lamentare e/o eccepire in merito alla condotta ed all’agire di tutti gli intervenuti nel "
              "presente processo verbale."):
        a("- " + t)
    a(f"Le operazioni di controllo, come sopra descritte, sono terminate alle ore {g('ora_fine', 'ora di chiusura')} "
      "di oggi stesso.")
    a(f"Il presente atto, che si compone di n. {g('fogli', 'numero fogli')} fogli e n. "
      f"{g('allegati', 'numero allegati')} allegato/i, viene redatto in due esemplari, uno dei quali è consegnato alla "
      "parte.")
    a("Fatto, letto e chiuso in data e luogo come sopra, viene confermato e sottoscritto.")
    a("I VERBALIZZANTI    LA PERSONA DI FIDUCIA    LA PARTE" if assistente else "I VERBALIZZANTI    LA PARTE")
    return "\n".join(L)
