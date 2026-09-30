"""Assistente conversazionale per una pratica: raccoglie motivazioni e obiettivi, chiede i documenti necessari e
porta avanti la redazione degli atti (PVOC del primo giorno, giornate successive, PVC) nell'ordine della circolare.

Il modello non modifica nulla da solo: puo' proporre aggiornamenti del fascicolo (blocco <<AZIONI>> in JSON, validato qui)
e proporre la redazione di un atto, che parte solo quando l'operatore preme il pulsante.
"""
from __future__ import annotations

import csv
import io
import json
import re
import zipfile

from . import analisi, calcoli
from . import pvoc as pvoc_mod

MAX_CARATTERI_DOC = 400_000
MAX_DOC_NEL_PROMPT = 60_000         # massimo per documento (le liste e i registri vanno letti quasi per intero)
MAX_TOTALE_DOC = 200_000            # budget complessivo dei documenti nel prompt, ripartito in modo equo
MIN_DOC_NEL_PROMPT = 6_000

INIZIO, FINE = "<<AZIONI>>", "<<FINE>>"

SYSTEM_CHAT = """Sei l'assistente istruttore di un militare della Guardia di Finanza (Compagnia di Tarquinia, Sezione \
Operativa Volante) che conduce un controllo o una verifica fiscale. Conversi con lui come in una chat, in italiano, \
con tono professionale e sintetico. Il militare e' l'autore degli atti e ne resta responsabile.

Il tuo compito, in ordine:
0. INFORMARTI, sempre e da solo. Ogni controllo e' un caso a se' e l'operatore puo' trovarsi davanti fattispecie che non ha \
mai trattato: non contare su precedenti e non affidarti alla memoria per norme, circolari, risposte a interpello, sentenze. \
Appena hai capito di che fattispecie si tratta, e ogni volta che ti serve chiarire un punto (requisiti e cause di esclusione di un \
regime, presupposti di un'agevolazione, regole di fatturazione/registrazione, obblighi dichiarativi, sanzioni, termini, profili \
penali e soglie, orientamenti della Cassazione e delle Corti di giustizia tributaria), emetti una o piu' "ricerche": il programma \
consulta le fonti aperte e ufficiali (Normattiva, Gazzetta Ufficiale, Agenzia delle Entrate con circolari, risoluzioni e risposte \
a interpello, MEF, Corte di Cassazione, Corte costituzionale, Corti di giustizia tributaria, UE) e ti restituisce i risultati nella \
sezione BASE NORMATIVA RACCOLTA del contesto. Scrivi i quesiti in forma GENERALE, senza nomi, importi o dati del caso, e indica il \
periodo d'imposta. Dopo la ricerca ragiona su norma vigente nel periodo, prassi e giurisprudenza prevalente, segnalando gli \
orientamenti contrastanti. Cita solo cio' che e' nella BASE NORMATIVA (indica l'id della ricerca, es. Q2); se una fonte ufficiale \
non e' stata trovata, dillo.
1. CAPIRE il caso: ragioni che hanno portato ad aprire il controllo/verifica, tipologia, soggetto, periodi d'imposta, \
tributi, obiettivo (a cosa si vuole arrivare). Fai poche domande alla volta (al massimo tre), le piu' utili.
2. CHIEDERE i documenti e le informazioni necessari a svolgere gli accertamenti: fatture (di vendita/acquisto), registri IVA, \
libro giornale e libri contabili, dichiarazioni (Redditi, IVA), F24, estratti conto, contratti, documentazione specifica \
della tipologia (es. bonus edilizi: titoli abilitativi, SAL, asseverazioni, comunicazioni di cessione). Tieni traccia di cio' \
che e' stato chiesto e di cio' che e' stato acquisito (elenco "richieste").
3. RACCOGLIERE i dati che servono per gli atti (vedi "DATI DEL PVOC DEL PRIMO GIORNO" nel contesto): chiedili all'operatore, \
non inventarli. Scrivi in "pvoc_primo" solo cio' che l'operatore ti ha detto o che risulta dai documenti.
4. PROPORRE il percorso: le fasi applicabili nell'ordine della Circolare 1/2018 (l'ordine e' vincolante; una fase non e' \
proponibile se le precedenti non sono concluse o dichiarate non applicabili). Quando hai gli elementi, proponi la redazione \
del PVOC del primo giorno, poi delle giornate successive (una attivita' per giornata) e infine del PVC.
5. SEGNALARE irregolarita' e coerenze che emergono dai documenti, con riferimento alla norma; se emergono indizi di reato \
(es. possibile superamento delle soglie del D.Lgs. 74/2000) ricorda l'art. 220 disp. att. c.p.p. e la comunicazione di notizia \
di reato (art. 347 c.p.p.).

6. DEDURRE al posto dell'operatore, e non fermarti alle violazioni banali. Analizza i documenti acquisiti (prospetto e dati \
tracciati calcolati dal programma, estratti dei documenti) e individua irregolarita' e violazioni, fase per fase, nell'ordine \
della circolare. Le violazioni piu' macchinose non saltano all'occhio in un documento solo: emergono dal confronto fra fonti \
indipendenti e da un ragionamento. Applica SEMPRE questo protocollo:
   a) MAPPA: chi sono i soggetti (parte, controparti, rappresentanti, amministratori di fatto), quali periodi, quali tributi, \
quali operazioni e flussi finanziari compaiono nei documenti.
   b) RASSEGNA SISTEMATICA: scorri il CATALOGO DEI RAGIONAMENTI del contesto area per area (e le altre aree elencate in fondo) e, per \
ciascuna area applicabile al caso, chiediti cosa ti aspetteresti di trovare e se nei documenti c'e' il segnale. Non limitarti a cio' \
che l'operatore ti ha indicato come motivo del controllo: ogni controllo puo' rivelare altro.
   c) RICONCILIAZIONE: confronta almeno due fonti indipendenti per ogni grandezza rilevante (fatture/registri/dichiarazioni/F24/banca/\
contratti/terzi). Ogni differenza e' un fatto da spiegare: scrivi le spiegazioni innocenti e quelle violative.
   d) IPOTESI ALTERNATIVE: per ogni anomalia formula piu' ipotesi (incluse quelle favorevoli al contribuente) e indica il documento o \
l'accertamento che le distingue. Non scartare un'ipotesi perche' manca un dato: chiedilo ("richieste") e proponi comunque il riscontro \
con affidabilita' "da_verificare".
   e) EFFETTI A CATENA: da ogni violazione deriva altro (altri tributi, IVA/II.DD./IRAP/riscossione, reato e soglie, autore della \
violazione, sanzione di competenza dell'Ufficio): proponi un riscontro anche per ciascuna conseguenza.
   f) QUANTIFICAZIONE: per ogni violazione individua i dati tracciati o proponi i calcoli che ne danno l'importo; mostra sempre i conti.
   g) CHIUSURA: prima di proporre il PVC verifica per ogni periodo e tributo di aver coperto le aree applicabili e che ogni violazione abbia \
fatto, periodo, norma violata, norma sanzionatoria, autore e importo.
Per ogni violazione che ritieni sussistere (o che potrebbe sussistere) proponi un RISCONTRO: fase in cui va constatata, periodo d'imposta, \
tipo (formale | sostanziale | indizio_reato), descrizione fattuale senza cifre, norma violata, il "ragionamento" (la catena \
fatto -> ipotesi -> norma), le "verifiche" ancora necessarie, gli "effetti" a catena, l'"affidabilita'" (certa | probabile | \
da_verificare) e gli ID dei dati/calcoli tracciati che ne quantificano l'importo. Le violazioni proposte vengono constatate nei PVOC delle \
giornate successive solo dopo la conferma dell'operatore: e' quindi corretto proporre anche quelle da verificare, segnalandolo. \
Se ti serve un importo che non c'e', proponi un CALCOLO tra voci tracciate (somma, differenza, percentuale): lo esegue il programma.
   Quando l'operatore chiede un "riesame sistematico" esegui la rassegna completa del catalogo: per ogni area elenca in breve se si \
applica, cosa hai trovato, cosa manca; proponi i riscontri nuovi e le richieste di documenti che ne derivano.

7. CONCILIARE le fonti aperte con il metodo del Reparto: nel contesto trovi il METODO DEL REPARTO PERTINENTE (precedenti, \
schede di ragionamento, spunti operativi). Ragiona come ragiona il Reparto (quali riscontri fare, in che ordine, come \
constatare) ma fondando ogni violazione sulla base normativa raccolta. Se il caso e' nuovo e la libreria non offre nulla di \
pertinente, procedi con norma e circolare e dillo all'operatore, suggerendo di arricchire la libreria con i suoi precedenti.

Regole inderogabili:
- La Circolare 1/2018 e' la fonte di verita' per le fasi e per i contenuti degli atti; gli esempi del Reparto servono per il lessico.
- Non inventare mai fatti, importi, date, orari, protocolli, nominativi o esiti. Gli importi calcolati si producono solo con i \
calcoli tracciati dell'app: non scrivere cifre calcolate a mente.
- Usa i segnaposto tra parentesi quadre (es. [PERSONA_1], [ENTE_1]) esattamente come li ricevi.
- Se un riferimento normativo non e' certo, scrivilo come "da verificare".
- Non dire di avere redatto un atto: la redazione parte quando l'operatore preme il pulsante che tu proponi.

Alla fine di OGNI risposta puoi aggiungere un solo blocco di aggiornamenti, esattamente in questa forma (JSON valido, \
tutte le chiavi facoltative), che l'operatore non vede:
<<AZIONI>>
{"fascicolo": {"motivazione": "...", "obiettivo": "..."},
 "pvoc_primo": {"campo": "valore"},
 "richieste": [{"voce": "Fatture di acquisto 2023-2025", "stato": "richiesto"}],
 "ricerche": [{"quesito": "domanda generale e senza dati del caso", "periodo": "2023"}],
 "riscontri": [{"fase": "coerenza_interna", "periodo": "2023", "tipo": "sostanziale", "descrizione": "...", "norma": "...", "ragionamento": "fatto -> ipotesi -> norma", "verifiche": ["documento o accertamento che manca"], "effetti": ["conseguenze su altri tributi, reato, autore"], "affidabilita": "certa|probabile|da_verificare", "fonti": ["Q1"], "importi": ["ID1", "ID2"]}],
 "calcoli": [{"tipo": "differenza", "etichetta": "...", "operandi": ["ID1", "ID2"]}],
 "proposte": [{"fase": "avvio", "giornata": "gg/mm/aaaa", "motivo": "perche' ora"}]}
<<FINE>>
- "fascicolo": motivazione e obiettivo riassunti dalle parole dell'operatore (testo formale, senza abbellimenti).
- "pvoc_primo": chiavi ammesse: __CAMPI__.
- "richieste": stato = richiesto | acquisito | non_disponibile. Riporta l'elenco completo aggiornato solo se cambia.
- "ricerche": al massimo 3 per risposta. Dopo averle emesse dai una breve frase di cortesia (es. "Mi informo sulla disciplina \
applicabile"): i risultati ti vengono passati subito e potrai continuare; non inventare l'esito della ricerca.
- "riscontri": solo nuovi riscontri (i gia' presenti sono nel contesto); "importi" = ID di dati/calcoli tracciati esistenti; \
"ragionamento", "verifiche", "effetti" e "affidabilita'" sono facoltativi ma vanno compilati per i riscontri non banali.
- "calcoli": tipo = somma | differenza | percentuale (per la percentuale aggiungi "param": "22"); gli operandi sono ID esistenti; \
l'ID del risultato lo assegna il programma e lo trovi nel contesto alla risposta successiva.
- "proposte": fasi (chiavi dell'elenco fasi del contesto) di cui proponi la redazione ora; "giornata" solo se l'operatore l'ha indicata.
"""


def system() -> str:
    from . import metodo
    return (SYSTEM_CHAT.replace("__CAMPI__", ", ".join(pvoc_mod.CAMPI + ("ivi",)))
            + "\n" + metodo.REGOLA_CONCILIAZIONE)


# ---------------------------------------------------------------- estrazione testo dai documenti
def _txt(el) -> str:
    return (el.text or "").strip() if el is not None else ""


def _fattura_xml(radice) -> tuple[str, list[tuple[str, str]]] | None:
    """Riassume una FatturaPA (una riga per documento). Solo dati necessari ai riscontri."""
    def l(nome, base=None):
        return (base if base is not None else radice).xpath(f".//*[local-name()='{nome}']")
    if not radice.xpath("//*[local-name()='FatturaElettronicaBody']"):
        return None
    righe, nomi = [], []
    cedente = radice.xpath("//*[local-name()='CedentePrestatore']")
    committente = radice.xpath("//*[local-name()='CessionarioCommittente']")

    def anagr(nodo):
        if not nodo:
            return "?"
        n = nodo[0]
        den = _txt(next(iter(l("Denominazione", n)), None))
        if not den:
            den = (_txt(next(iter(l("Nome", n)), None)) + " " + _txt(next(iter(l("Cognome", n)), None))).strip()
        piva = _txt(next(iter(l("IdCodice", n)), None))
        cf = _txt(next(iter(l("CodiceFiscale", n)), None))
        if den:
            nomi.append((den, "ente" if not l("Nome", n) else "persona"))
        return f"{den or '?'} (P.IVA {piva or '-'}, CF {cf or '-'})"
    for body in radice.xpath("//*[local-name()='FatturaElettronicaBody']"):
        gen = l("DatiGeneraliDocumento", body)
        tipo = _txt(next(iter(l("TipoDocumento", body)), None))
        num = _txt(next(iter(l("Numero", body)), None))
        data = _txt(next(iter(l("Data", body)), None))
        tot = _txt(next(iter(l("ImportoTotaleDocumento", body)), None))
        imp = [_txt(x) for x in l("ImponibileImporto", body)]
        iva = [_txt(x) for x in l("Imposta", body)]
        aliq = [_txt(x) for x in l("AliquotaIVA", body)]
        nat = [_txt(x) for x in l("Natura", body)]
        cau = " ".join(_txt(x) for x in l("Causale", body))[:300]
        righe.append(f"Fattura {tipo} n. {num} del {data}; cedente/prestatore {anagr(cedente)}; "
                     f"cessionario/committente {anagr(committente)}; totale {tot or '-'}; imponibile {', '.join(imp) or '-'}; "
                     f"aliquote {', '.join(aliq) or '-'}; imposta {', '.join(iva) or '-'}"
                     + (f"; natura {', '.join(nat)}" if nat else "") + (f"; causale: {cau}" if cau else ""))
        del gen
    return "\n".join(righe), nomi


def fatture_xml(dati: bytes) -> list[dict]:
    """Dati strutturati delle fatture elettroniche (per i riscontri del programma). Lista vuota se non e' una FatturaPA."""
    from lxml import etree
    try:
        radice = etree.fromstring(dati, parser=etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False))
    except etree.XMLSyntaxError:
        return []

    def tutti(base, nome):
        return base.xpath(f".//*[local-name()='{nome}']")

    def primo(base, nome):
        r = tutti(base, nome)
        return _txt(r[0]) if r else ""

    def anagr(nodo):
        if not nodo:
            return {"denominazione": "", "piva": "", "cf": ""}
        n = nodo[0]
        den = primo(n, "Denominazione") or (primo(n, "Nome") + " " + primo(n, "Cognome")).strip()
        return {"denominazione": den, "piva": primo(n, "IdCodice"), "cf": primo(n, "CodiceFiscale")}
    ced = anagr(radice.xpath("//*[local-name()='CedentePrestatore']"))
    com = anagr(radice.xpath("//*[local-name()='CessionarioCommittente']"))

    def num(x):
        try:
            return float(x)
        except ValueError:
            return 0.0
    out = []
    for body in radice.xpath("//*[local-name()='FatturaElettronicaBody']"):
        data = primo(body, "Data")
        riep = [{"aliquota": num(primo(r, "AliquotaIVA")), "imponibile": num(primo(r, "ImponibileImporto")),
                 "imposta": num(primo(r, "Imposta")), "natura": primo(r, "Natura")}
                for r in tutti(body, "DatiRiepilogo")]
        out.append({"numero": primo(body, "Numero"), "data": data, "anno": int(data[:4]) if data[:4].isdigit() else 0,
                    "tipo_doc": primo(body, "TipoDocumento"), "cedente": ced, "cessionario": com,
                    "totale": num(primo(body, "ImportoTotaleDocumento")), "bollo": num(primo(body, "ImportoBollo")),
                    "riepilogo": riep})
    return out


def _metadati_pdf(r) -> str:
    """Riga iniziale con i metadati del PDF (data di creazione/modifica, programma): servono a confrontare la data di un
    documento con quella in cui il file e' stato realmente prodotto."""
    try:
        m = r.metadata or {}
        parti = []
        for k, e in (("/CreationDate", "creato il"), ("/ModDate", "modificato il")):
            v = str(m.get(k) or "")
            if v.startswith("D:") and len(v) >= 10:
                parti.append(f"{e} {v[8:10]}/{v[6:8]}/{v[2:6]}")
        prod = " / ".join(str(m.get(k)) for k in ("/Producer", "/Creator") if m.get(k))
        firma = "con campo di firma digitale" if "/AcroForm" in r.trailer["/Root"] else "senza campo di firma digitale"
        if parti or prod:
            return f"[Metadati del file PDF: {', '.join(parti) or 'date non indicate'}; programma: {prod or 'n.d.'}; {firma}]\n"
    except Exception:                                         # noqa: BLE001
        pass
    return ""


def estrai_testo(nome: str, dati: bytes) -> tuple[str, str, list[tuple[str, str]]]:
    """(tipo, testo, nomi da pseudonimizzare [(nome, persona|ente)]). Solleva ValueError se il formato non e' leggibile."""
    n = nome.lower()
    if n.endswith(".xml") or n.endswith(".p7m") and dati[:5] == b"<?xml":
        from lxml import etree
        try:
            radice = etree.fromstring(dati, parser=etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False))
        except etree.XMLSyntaxError as e:
            raise ValueError(f"XML non valido: {e}") from e
        riassunto = _fattura_xml(radice)
        if riassunto:
            return "xml_fattura", riassunto[0], riassunto[1]
        return "testo", " ".join(radice.itertext())[:MAX_CARATTERI_DOC], []
    if n.endswith(".pdf"):
        try:
            from pypdf import PdfReader
        except ImportError as e:
            raise ValueError("Lettura dei PDF non disponibile su questo server") from e
        r = PdfReader(io.BytesIO(dati))
        t = "\n".join((pg.extract_text() or "") for pg in r.pages)
        if not t.strip():
            raise ValueError("Il PDF non contiene testo selezionabile (e' una scansione): serve l'OCR, non ancora disponibile.")
        return "pdf", (_metadati_pdf(r) + t)[:MAX_CARATTERI_DOC], []
    if n.endswith(".xlsx"):
        from . import crediti
        try:
            righe = crediti.righe_da_xlsx(dati)
        except Exception as e:                                # noqa: BLE001
            raise ValueError("File Excel non leggibile") from e
        testo = "\n".join(" | ".join("" if c is None else str(c).strip() for c in r).rstrip(" |") for r in righe)
        return ("movimenti_crediti" if crediti.movimenti_da_righe(righe) else "xlsx"), testo[:MAX_CARATTERI_DOC], []
    if n.endswith(".docx"):
        import docx
        try:
            d = docx.Document(io.BytesIO(dati))
        except (zipfile.BadZipFile, KeyError) as e:
            raise ValueError("File Word non valido") from e
        parti = [p.text for p in d.paragraphs]
        for t in d.tables:
            parti += ["\t".join(c.text for c in r.cells) for r in t.rows]
        return "docx", "\n".join(parti)[:MAX_CARATTERI_DOC], []
    if n.endswith((".csv", ".tsv", ".txt", ".md")):
        for enc in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                testo = dati.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if n.endswith((".csv", ".tsv")):
            righe = list(csv.reader(io.StringIO(testo), delimiter="\t" if n.endswith(".tsv") else (";" if testo.count(";") > testo.count(",") else ",")))
            return "csv", "\n".join(" | ".join(r) for r in righe)[:MAX_CARATTERI_DOC], []
        return "testo", testo[:MAX_CARATTERI_DOC], []
    raise ValueError("Formato non supportato. Carica XML delle fatture, PDF con testo, Word, Excel (.xlsx), CSV o testo.")


# ---------------------------------------------------------------- base normativa (ricerche automatiche su fonti aperte)
MAX_BASE_NORMATIVA = 22_000


def base_normativa_testo(voci: list[dict], limite: int = MAX_BASE_NORMATIVA) -> str:
    """Le ricerche piu' recenti per prime, nei limiti di spazio."""
    if not voci:
        return "- nessuna ricerca ancora eseguita"
    out, usati = [], 0
    for v in reversed(voci):
        fonti = "; ".join(f"{f.get('titolo') or f.get('dominio')} ({f.get('dominio') or '?'}, "
                          f"{'UFFICIALE' if f.get('ufficiale') else 'non ufficiale'})" for f in v.get("fonti", [])[:12]) or "nessuna fonte"
        blocco = (f"--- {v['id']} | {v['quesito']} | {v['periodo']} | esito: {v.get('esito', 'ok')} ---\n{v.get('sintesi', '')}\n"
                  f"Fonti: {fonti}" + ("\nATTENZIONE: nessuna fonte ufficiale reperita." if v.get("esito", "ok") == "ok"
                                        and not any(f.get("ufficiale") for f in v.get("fonti", [])) else ""))
        if usati + len(blocco) > limite:
            out.append(f"--- {v['id']} | {v['quesito']} (non riportata per limiti di spazio) ---")
            continue
        usati += len(blocco)
        out.append(blocco)
    return "\n".join(out)


_RE_TOKEN = re.compile(r"\[[A-Z_]+_\d+\]")


def quesito_pulito(q: str) -> str:
    """Quesito di ricerca privo di segnaposto e spazi superflui; stringa vuota se sembra contenere nomi propri."""
    q = re.sub(r"\s+", " ", _RE_TOKEN.sub(" ", q or "")).strip()
    return "" if nomi_sospetti(q) else q[:600]


# ---------------------------------------------------------------- contesto per il modello
def quote_documenti(lunghezze: list[int], totale: int = 0, massimo: int = 0, minimo: int = 0) -> list[int]:
    """Caratteri concessi a ciascun documento: ripartizione equa del budget (chi e' piu' corto lascia spazio agli altri)."""
    totale, massimo, minimo = totale or MAX_TOTALE_DOC, massimo or MAX_DOC_NEL_PROMPT, minimo or MIN_DOC_NEL_PROMPT
    quote = [min(n, massimo) for n in lunghezze]
    if sum(quote) <= totale:
        return quote
    ordine = sorted(range(len(quote)), key=lambda i: quote[i])
    restante, n = totale, len(quote)
    out = [0] * len(quote)
    for k, i in enumerate(ordine):
        equa = max(minimo, restante // (n - k))
        out[i] = min(quote[i], equa)
        restante -= out[i]
    return out


def contesto(p_tipo: str, tipologia_nome: str, fasi: list[dict], d: dict, documenti: list[dict], atti: list[dict],
             pvoc_iniziale: dict, prospetto: str = "", voci: str = "", base_normativa: list | None = None,
             metodo: str = "", catalogo: str = "") -> str:
    fasc = d.get("fascicolo", {}) or {}
    sog = d.get("soggetto", {}) or {}
    righe = [f"TIPO DI INTERVENTO: {p_tipo}. TIPOLOGIA: {tipologia_nome}.",
             "SOGGETTO: " + "; ".join((sog.get("persone", []) or []) + (sog.get("enti", []) or [])),
             "IDENTIFICATIVI: " + "; ".join((sog.get("codici_fiscali", []) or []) + (sog.get("partite_iva", []) or [])),
             "VERBALIZZANTI: " + "; ".join(d.get("verbalizzanti", []) or []),
             f"MOTIVAZIONE (fin qui): {fasc.get('motivazione') or 'non ancora indicata'}",
             f"OBIETTIVO (fin qui): {fasc.get('obiettivo') or 'non ancora indicato'}",
             "", "FASI NELL'ORDINE DELLA CIRCOLARE (chiave | titolo | stato | atto):"]
    for f in fasi:
        righe.append(f"- {f['chiave']} | {f['titolo']} | {f['stato']}" + (f" | atto {f['atto']}" if f["atto"] else "")
                     + (" | condizionale" if f["condizionale"] else ""))
    righe += ["", "RICHIESTE DI DOCUMENTI (stato):"]
    rich = fasc.get("richieste") or []
    righe += [f"- {r['voce']}: {r['stato']}" for r in rich] or ["- nessuna ancora"]
    righe += ["", "DATI DEL PVOC DEL PRIMO GIORNO (campo: valore | mancante):"]
    for k in pvoc_mod.CAMPI:
        v = pvoc_iniziale.get(k, "")
        righe.append(f"- {k}: {v if v else 'MANCANTE'}")
    righe += ["", "DOCUMENTI ACQUISITI (testo; se e' stato troncato per limiti di spazio e' indicato):"]
    quote = quote_documenti([len(x["testo"]) for x in documenti])
    for doc, q in zip(documenti, quote):
        estr = doc["testo"][:q]
        nota = f" - TRONCATO ai primi {q} caratteri su {len(doc['testo'])}" if len(doc["testo"]) > q else ""
        righe.append(f"--- {doc['nome']} ({doc['tipo']}, {doc['caratteri']} caratteri{nota}) ---\n{estr}")
    if not documenti:
        righe.append("- nessuno")
    righe += ["", "BASE NORMATIVA RACCOLTA (ricerche su fonti aperte gia' eseguite; id | quesito | periodo):", base_normativa_testo(base_normativa or [])]
    righe += ["", "METODO DEL REPARTO PERTINENTE (precedenti, schede di ragionamento, spunti operativi dalla libreria):",
              metodo or "- nessun precedente o spunto pertinente in libreria"]
    if catalogo:
        righe += ["", "CATALOGO DEI RAGIONAMENTI PER FAR EMERGERE LE VIOLAZIONI (schemi segnale -> ipotesi -> verifiche -> norma -> "
                      "quantificazione -> effetti a catena; le norme vanno verificate con le ricerche):", catalogo]
    if prospetto:
        righe += ["", "PROSPETTO DELLE FATTURE (calcolato dal programma sui file XML caricati):", prospetto]
    righe += ["", "DATI E CALCOLI TRACCIATI DISPONIBILI (id - etichetta: valore):", voci or "- nessuno"]
    righe += ["", "RISCONTRI (id | fase | periodo | tipo | stato | origine): descrizione [norma] [importi]"]
    ris = d.get("riscontri") or []
    righe += [f"- {r['id']} | {r['fase']} | {r['periodo']} | {r['tipo']} | {r['stato']} | {r['origine']}: {r['descrizione']} "
              f"[{r['norma']}] [{', '.join(r['importi'])}]"
              + (f" (da verificare: {'; '.join(r['verifiche'])})" if r.get("verifiche") and r["stato"] == "proposto" else "")
              for r in ris] or ["- nessuno"]
    righe += ["", "ATTI GIA' REDATTI: " + (", ".join(f"{a['tipo']} {a['giornata'] or ''} ({a['fase']})" for a in atti) or "nessuno")]
    return "\n".join(righe)


# ---------------------------------------------------------------- azioni proposte dal modello
_RE_BLOCCO = re.compile(re.escape(INIZIO) + r"(.*?)" + re.escape(FINE), re.S)


def separa_azioni(testo: str) -> tuple[str, dict | None]:
    """(testo da mostrare, azioni). Blocco assente o non valido -> None, mai un errore."""
    m = _RE_BLOCCO.search(testo)
    visibile = _RE_BLOCCO.sub("", testo)
    if INIZIO in visibile:                                        # blocco aperto e mai chiuso
        visibile = visibile.split(INIZIO)[0]
    visibile = visibile.strip()
    if not m:
        return visibile, None
    grezzo = m.group(1).strip()
    grezzo = re.sub(r"^```(?:json)?|```$", "", grezzo).strip()
    try:
        dati = json.loads(grezzo)
    except json.JSONDecodeError:
        return visibile, None
    return visibile, dati if isinstance(dati, dict) else None


def _mappa(o, f):
    if isinstance(o, str):
        return f(o)
    if isinstance(o, list):
        return [_mappa(x, f) for x in o]
    if isinstance(o, dict):
        return {k: _mappa(v, f) for k, v in o.items()}
    return o


def valida_azioni(az: dict | None, restore, fasi_valide: dict[str, str], id_voci: set[str] | frozenset = frozenset(),
                  id_ricerche: set[str] | frozenset = frozenset()) -> dict:
    """Filtra le azioni: solo chiavi note, tipi corretti; i segnaposto tornano dati reali. `fasi_valide`: chiave -> atto."""
    if not az:
        return {}
    grezze = az.get("ricerche")                                   # i quesiti di ricerca restano pseudonimizzati
    az = _mappa(az, lambda s: restore(s)[0])
    if grezze is not None:
        az["ricerche"] = grezze
    out: dict = {}
    fasc = az.get("fascicolo")
    if isinstance(fasc, dict):
        out["fascicolo"] = {k: str(v).strip() for k, v in fasc.items() if k in ("motivazione", "obiettivo") and str(v).strip()}
    pv = az.get("pvoc_primo")
    if isinstance(pv, dict):
        ok = {}
        for k, v in pv.items():
            if k == "ivi":
                ok[k] = bool(v)
            elif k in pvoc_mod.CAMPI and isinstance(v, (str, int, float)) and str(v).strip():
                ok[k] = str(v).strip()
        out["pvoc_primo"] = ok
    ri = az.get("richieste")
    if isinstance(ri, list):
        out["richieste"] = [{"voce": str(r["voce"]).strip()[:200], "stato": r.get("stato") if r.get("stato") in ("richiesto", "acquisito", "non_disponibile") else "richiesto"}
                            for r in ri if isinstance(r, dict) and str(r.get("voce", "")).strip()][:60]
    ric = az.get("ricerche")
    if isinstance(ric, list):
        out["ricerche"] = [{"quesito": str(r["quesito"]).strip(), "periodo": str(r.get("periodo", "") or "").strip()[:40] or "in corso"}
                           for r in ric if isinstance(r, dict) and str(r.get("quesito", "")).strip()][:3]
    rs = az.get("riscontri")
    if isinstance(rs, list):
        out["riscontri"] = []
        for r in rs:
            if not (isinstance(r, dict) and r.get("fase") in fasi_valide and str(r.get("descrizione", "")).strip()):
                continue
            imp = [i for i in (r.get("importi") or []) if isinstance(i, str) and i in id_voci]
            out["riscontri"].append({
                "fase": r["fase"], "periodo": str(r.get("periodo", "") or "").strip()[:40],
                "tipo": r.get("tipo") if r.get("tipo") in ("formale", "sostanziale", "indizio_reato") else "sostanziale",
                "descrizione": str(r["descrizione"]).strip()[:1500], "norma": str(r.get("norma", "") or "da verificare").strip()[:300],
                "ragionamento": str(r.get("ragionamento", "") or "").strip()[:1200],
                "verifiche": [str(x).strip()[:300] for x in (r.get("verifiche") or []) if isinstance(x, str) and x.strip()][:8],
                "effetti": [str(x).strip()[:300] for x in (r.get("effetti") or []) if isinstance(x, str) and x.strip()][:8],
                "affidabilita": r.get("affidabilita") if r.get("affidabilita") in ("certa", "probabile", "da_verificare") else "probabile",
                "fonti": [q for q in (r.get("fonti") or []) if isinstance(q, str) and q in id_ricerche],
                "importi": imp, "origine": "ai"})
        out["riscontri"] = out["riscontri"][:30]
    ca = az.get("calcoli")
    if isinstance(ca, list):
        out["calcoli"] = [{"tipo": c["tipo"], "etichetta": str(c.get("etichetta", "") or "").strip()[:200],
                           "operandi": [str(x) for x in c.get("operandi", []) if isinstance(x, str)],
                           "param": str(c.get("param", "") or "")}
                          for c in ca if isinstance(c, dict) and c.get("tipo") in ("somma", "differenza", "percentuale")
                          and isinstance(c.get("operandi"), list) and str(c.get("etichetta", "")).strip()][:10]
    pr = az.get("proposte")
    if isinstance(pr, list):
        out["proposte"] = [{"fase": r["fase"], "giornata": str(r.get("giornata", "") or "").strip()[:10],
                            "motivo": str(r.get("motivo", "") or "").strip()[:300], "atto": fasi_valide[r["fase"]]}
                           for r in pr if isinstance(r, dict) and r.get("fase") in fasi_valide and fasi_valide[r["fase"]]][:6]
    return out


def applica_azioni(d: dict, az: dict) -> None:
    fasc = d.setdefault("fascicolo", {})
    if "fascicolo" in az:
        fasc.update(az["fascicolo"])
    if "pvoc_primo" in az:
        fasc.setdefault("pvoc_primo", {}).update(az["pvoc_primo"])
    if "richieste" in az:
        fasc["richieste"] = az["richieste"]
    if "proposte" in az:
        fasc["proposte"] = az["proposte"]
    if az.get("riscontri"):
        nuovi = [{**r, "chiave": analisi.chiave_ai(r)} for r in az["riscontri"]]
        d["riscontri"] = analisi.unisci_riscontri(d.get("riscontri", []), nuovi + [
            r for r in d.get("riscontri", []) if r["chiave"] not in {n["chiave"] for n in nuovi}])
    for c in az.get("calcoli", []):
        cfg = d.setdefault("calcoli", {"dati": [], "calcoli": []})
        nuovo = {"id": f"C{len(cfg['calcoli']) + 1}", **c}
        try:
            calcoli.registro_da_dati({"dati": cfg["dati"], "calcoli": cfg["calcoli"] + [nuovo]})
        except Exception:                                     # operandi inesistenti o operazione non valida: si scarta
            continue
        cfg["calcoli"].append(nuovo)


# ---------------------------------------------------------------- nomi non in anagrafica (controllo in piu' sul testo libero)
_PAROLA = r"[A-ZÀ-Ý][a-zà-ÿ'’]{2,}|[A-ZÀ-Ý]{3,}"
_RE_NOME = re.compile(rf"\b(?:{_PAROLA})(?:\s+(?:{_PAROLA})){{1,3}}\b")
_NON_NOME = {"guardia", "finanza", "compagnia", "tarquinia", "sezione", "operativa", "volante", "agenzia", "entrate",
             "legge", "decreto", "circolare", "codice", "civile", "penale", "procedura", "statuto", "contribuente",
             "reparto", "comando", "garante", "regione", "lazio", "roma", "italia", "repubblica", "imposta", "valore",
             "aggiunto", "redditi", "persone", "fisiche", "societa", "società", "regime", "forfettario", "superbonus",
             "ecobonus", "sismabonus", "bonus", "edilizi", "quadro", "modello", "processo", "verbale", "operazioni",
             "compiute", "verifica", "controllo", "constatazione", "invito", "presentarsi", "ordine", "accesso",
             "direttore", "comandante", "tenente", "maresciallo", "capitano", "brigadiere", "luogotenente", "vice",
             "ordinario", "dpr", "dlgs", "art", "artt", "comma", "iva", "irpef", "irap", "ires", "cnr", "pvoc", "pvv",
             "pvc", "fatture", "registri", "libro", "giornale", "dichiarazione", "dichiarazioni", "cassetto", "fiscale",
             "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre",
             "corte", "cassazione", "costituzionale", "giustizia", "tributaria", "tributario", "sezioni", "unite",
             "sentenza", "ordinanza", "risoluzione", "interpello", "risposta", "ministero", "economia", "finanze",
             "unione", "europea", "gazzetta", "ufficiale", "normattiva", "sezione", "civile", "penale", "commissione",
             "novembre", "dicembre", "del", "della", "delle", "dei", "degli", "per", "con", "che", "non", "sono", "come"}


def nomi_sospetti(testo_anonimo: str) -> list[str]:
    """Sequenze di 2-4 parole maiuscole non riconosciute (possibili nomi di persone/enti fuori dall'anagrafica)."""
    pulito = re.sub(r"\[[A-Z_]+_\d+\]", " ", testo_anonimo)
    out = []
    for m in _RE_NOME.finditer(pulito):
        parole = m.group(0).split()
        if all(w.lower() not in _NON_NOME for w in parole):
            out.append(m.group(0))
    return sorted(set(out))
