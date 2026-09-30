"""Metodo del Reparto: precedenti (ripuliti), schede di ragionamento, spunti operativi e stile di scrittura.

L'AI deve produrre PVOC e PVC come sintesi di due fonti:
  1. la base normativa raccolta dalle fonti aperte (norme, prassi dell'Agenzia delle Entrate, giurisprudenza);
  2. il metodo del Reparto: come si ragiona, cosa si riscontra e in che ordine, come si constata e come si scrive.
Qui si prepara la seconda fonte. Gli atti precedenti entrano solo dopo la ripulitura dai dati personali (segnaposto
generici senza numero, per non confonderli con quelli della pratica in corso) e dopo la conferma dei nomi dubbi.
"""
from __future__ import annotations

import pathlib

import re

from . import chat
from .privacy.pseudonymizer import TOKEN_RE, Pseudonymizer

GENERICI = {"PERSONA": "«persona»", "MILITARE": "«militare»", "ENTE": "«ente»", "CF": "«codice fiscale»",
            "PIVA": "«partita IVA»", "EMAIL": "«e-mail»", "IBAN": "«IBAN»", "TEL": "«telefono»", "TARGA": "«targa»",
            "DOC": "«documento»", "NASCITA": "«data e luogo di nascita»", "INDIRIZZO": "«indirizzo»"}

REGOLA_CONCILIAZIONE = """SINTESI DELLE DUE FONTI (regola per PVOC, PVC e riscontri):
- FONTE 1, BASE NORMATIVA RACCOLTA (norme, prassi AdE, giurisprudenza trovate sulle fonti aperte): dice COSA e' violato e \
con quale fondamento; ogni affermazione giuridica deve poggiare qui.
- FONTE 2, METODO DEL REPARTO (precedenti, schede di ragionamento, spunti operativi, esempi di stile): dice COME si accerta, \
in che ordine si compiono i riscontri, come si constata la violazione e con quali formule si scrive.
- Concilia: applica il ragionamento operativo del Reparto ai fatti del caso, usando la norma e la prassi trovate; scrivi con il \
lessico e la struttura del Reparto. Non copiare fatti, nomi, importi o date dai precedenti: servono solo per metodo e stile. \
I segnaposto tra «» dei precedenti («persona», «ente», ...) non vanno mai riprodotti: nell'atto usa i segnaposto del caso \
(es. [PERSONA_1]) oppure [DA COMPILARE: ...].
- Se metodo del Reparto e fonti aperte divergono (prassi superata da una circolare o da una sentenza piu' recenti, norma \
modificata nel periodo d'imposta), segui la fonte normativa gerarchicamente superiore o piu' recente e segnala la divergenza \
nella spiegazione {{SPIEGA: ...}} con [DA COMPILARE: confermare con il Comando]. Se manca uno dei due riferimenti, dillo.
- In ogni passaggio significativo la spiegazione {{SPIEGA: ...}} indica da quale precedente o spunto del Reparto deriva il \
modo di procedere (titolo) e da quale fonte aperta deriva il fondamento giuridico (id Q).
"""

PROMPT_SCHEDA = """Sei un assistente che analizza un atto gia' redatto da un Reparto della Guardia di Finanza (testo gia' ripulito \
da dati personali: i segnaposto tra «» sostituiscono nomi e identificativi) per descriverne il METODO. NON giudicare la \
correttezza giuridica dell'atto e non cercare errori: serve solo a imparare come lavora il Reparto.
Rispondi in italiano, in testo semplice, con queste sezioni:
FATTISPECIE: di cosa tratta (tributo, istituto, tipo di controllo), in una riga.
STRUTTURA: le sezioni dell'atto nell'ordine in cui compaiono.
RAGIONAMENTO OPERATIVO: come si arriva alle violazioni: quali documenti si esaminano, quali riscontri e confronti si fanno e in che \
ordine, come si quantifica.
COME SI CONSTATA: lo schema con cui una violazione viene descritta (fatto accertato, periodo, norma richiamata, importo).
SPUNTI OPERATIVI: indicazioni pratiche ricavabili (cosa chiedere alla parte, cosa riscontrare in banca dati, cautele).
FORMULE E LESSICO: fino a 8 frasi tipiche riportate alla lettera (senza dati personali).
Sii concreto e sintetico (massimo 450 parole). Non inventare nulla che non sia nel testo."""


# ---------------------------------------------------------------- ripulitura dei precedenti
def ripulisci(testo: str) -> tuple[str, list[str]]:
    """(testo con segnaposto generici, nomi dubbi da far classificare all'operatore)."""
    anon = Pseudonymizer().anonimizza(testo)
    anon = TOKEN_RE.sub(lambda m: GENERICI.get(m.group(1), "«dato»"), anon)
    return anon, chat.nomi_sospetti(anon)


def applica_nomi(testo: str, scelte: dict[str, str]) -> str:
    for nome, tipo in sorted(scelte.items(), key=lambda kv: -len(kv[0])):
        if tipo in ("persona", "ente"):
            testo = re.sub(r"(?<![A-Za-zÀ-ÿ])" + re.escape(nome).replace(r"\ ", r"\s+") + r"(?![A-Za-zÀ-ÿ])",
                           "«persona»" if tipo == "persona" else "«ente»", testo, flags=re.I)
    return testo


def distilla(client, modello: str, atto: str, testo: str) -> str:
    """Scheda di ragionamento ricavata dall'atto ripulito (passa dal filtro fail-closed prima di uscire)."""
    from . import ai as ai_mod
    p = Pseudonymizer()
    messaggio = p.anonimizza_o_blocca(f"Tipo di atto: {atto or 'non indicato'}.\n\nTESTO DELL'ATTO:\n{testo[:30000]}")
    risposta, _, _ = ai_mod.chiama_chat(client, modello, PROMPT_SCHEDA, [{"role": "user", "content": messaggio}], max_tokens=3000)
    return risposta.strip()


# ---------------------------------------------------------------- scelta di cio' che serve al caso
_STOP = set("""della delle degli dello nella nelle negli nello sono stato stati essere questo questa questi queste quindi
dalla dalle dagli anche come dove quando ogni tutti tutte alla alle agli allo sulla sulle sugli sullo nonche' presso
parte verbale atto controllo verifica fase giorno giornata""".split())


def parole(testo: str) -> set[str]:
    return {w for w in re.findall(r"[a-zàèéìòù0-9]{4,}", (testo or "").lower()) if w not in _STOP}


def seleziona(voci: list[dict], interrogazione: str, atto: str = "", max_spunti: int = 4, max_precedenti: int = 2) -> list[dict]:
    """Le voci piu' pertinenti al caso: sovrapposizione di parole con titolo, tag e scheda/testo, con un bonus per l'atto."""
    q = parole(interrogazione)
    punteggi = []
    for v in voci:
        if v["stato"] != "pronto":
            continue
        corpo = parole(" ".join([v["titolo"], v["tag"], v.get("scheda", ""), v["testo"][:4000]]))
        tag = parole(v["tag"] + " " + v["titolo"])
        s = len(q & corpo) + 3 * len(q & tag)
        if s == 0:
            continue                                            # senza alcuna pertinenza testuale non entra, qualunque sia il bonus
        if atto and v["atto"] == atto:
            s += 2
        if v["tipo"] == "spunto" and not v["atto"]:
            s += 1
        if s > 0:
            punteggi.append((s, v))
    punteggi.sort(key=lambda x: -x[0])
    spunti = [v for _, v in punteggi if v["tipo"] == "spunto"][:max_spunti]
    prec = [v for _, v in punteggi if v["tipo"] == "precedente"][:max_precedenti]
    return spunti + prec


def metodo_testo(sel: list[dict], limite: int = 9000) -> str:
    if not sel:
        return "- nessun precedente o spunto del Reparto pertinente in libreria"
    out, usati = [], 0
    for v in sel:
        corpo = v["testo"] if v["tipo"] == "spunto" else (v.get("scheda") or "(scheda di ragionamento non ancora estratta)")
        blocco = f"--- {'SPUNTO OPERATIVO' if v['tipo'] == 'spunto' else 'PRECEDENTE ' + v['atto']}: {v['titolo']} [{v['tag']}] ---\n{corpo}"
        if usati + len(blocco) > limite:
            blocco = blocco[:max(0, limite - usati)]
        if not blocco:
            break
        usati += len(blocco)
        out.append(blocco)
    return "\n".join(out)


def esempi_di_stile(voci: list[dict], interrogazione: str, atto: str, n: int = 2, max_caratteri: int = 3500) -> list[str]:
    """Brani dei precedenti dello stesso tipo di atto piu' pertinenti al caso (per imitare struttura e lessico)."""
    q = parole(interrogazione)
    cand = [v for v in voci if v["tipo"] == "precedente" and v["stato"] == "pronto" and v["atto"] == atto]
    cand.sort(key=lambda v: -len(q & parole(v["titolo"] + " " + v["tag"] + " " + v.get("scheda", "") + " " + v["testo"][:4000])))
    out = []
    for v in cand[:n]:
        par = [p.strip() for p in v["testo"].split("\n") if len(p.strip()) > 40]
        ordine = sorted(range(len(par)), key=lambda i: -len(q & parole(par[i])))
        scelti, tot = [], 0
        for i in ordine:
            if tot + len(par[i]) > max_caratteri:
                continue
            scelti.append(i)
            tot += len(par[i])
        inizio = par[:3]                                        # l'apertura dell'atto dà il tono e la formula iniziale
        brani = inizio + [par[i] for i in sorted(scelti) if par[i] not in inizio]
        out.append(f"{v['titolo']} ({v['atto']}; dati personali sostituiti da segnaposto «...»)\n" + "\n".join(brani)[:max_caratteri + 800])
    return out


# ---------------------------------------------------------------- conoscenza integrata nel programma (file del repository)
import pathlib  # noqa: E402

CARTELLA_METODO = pathlib.Path(__file__).parent / "knowledge" / "metodo"


def _leggi_integrato(path: pathlib.Path) -> dict | None:
    """File `.md` con intestazione `---` (tipo, atto, titolo, tag) e sezioni `## Scheda` e `## Brani di stile`."""
    t = path.read_text(encoding="utf-8")
    m = re.match(r"---\n(.*?)\n---\n(.*)", t, re.S)
    if not m:
        return None
    meta = {k.strip(): v.strip() for k, _, v in (r.partition(":") for r in m.group(1).splitlines() if ":" in r)}
    corpo = m.group(2)
    parti = re.split(r"^## ", corpo, flags=re.M)
    sez = {p.split("\n", 1)[0].strip().lower(): (p.split("\n", 1)[1].strip() if "\n" in p else "") for p in parti if p.strip()}
    return {"id": f"b:{path.stem}", "tipo": meta.get("tipo", "precedente"), "atto": meta.get("atto", ""), "stato": "pronto",
            "titolo": meta.get("titolo", path.stem), "tag": meta.get("tag", ""), "testo": sez.get("brani di stile", sez.get("testo", "")),
            "scheda": sez.get("scheda", ""), "sospetti": [], "integrato": True}


def integrati() -> list[dict]:
    if not CARTELLA_METODO.exists():
        return []
    out = []
    for p in sorted(CARTELLA_METODO.glob("*.md")):
        v = _leggi_integrato(p)
        if v:
            out.append(v)
    return out


# ---------------------------------------------------------------- catalogo dei ragionamenti sulle violazioni
CATALOGO = pathlib.Path(__file__).parent / "knowledge" / "catalogo_violazioni.md"


def catalogo_sezioni() -> list[dict]:
    """[{'titolo','aree','tag','testo'}] dal file del catalogo (una sezione per «## [area] titolo»)."""
    if not CATALOGO.exists():
        return []
    out = []
    for blocco in re.split(r"^## ", CATALOGO.read_text(encoding="utf-8"), flags=re.M)[1:]:
        riga, _, corpo = blocco.partition("\n")
        m = re.match(r"\[([^\]]+)\]\s*(.*)", riga.strip())
        area, titolo = (m.group(1), m.group(2)) if m else ("", riga.strip())
        tag = re.search(r"^TAG:\s*(.*)$", corpo, re.M)
        out.append({"titolo": titolo, "area": area, "tag": tag.group(1) if tag else "", "testo": corpo.strip()})
    return out


def catalogo_testo(caso: str, limite: int = 11000) -> str:
    """Le sezioni trasversali sempre, poi le piu' pertinenti al caso per sovrapposizione di parole (come `seleziona`)."""
    sez = catalogo_sezioni()
    if not sez:
        return "- catalogo non disponibile"
    q = parole(caso)
    fisse = [x for x in sez if x["area"] == "trasversale" or x["area"] == "chiusura"]
    altre = []
    for x in sez:
        if x in fisse:
            continue
        pt = len(q & parole(x["tag"] + " " + x["titolo"])) * 3 + len(q & parole(x["testo"]))
        altre.append((pt, x))
    altre.sort(key=lambda t: -t[0])
    scelte = [x for pt, x in altre if pt > 0][:8]
    rimaste = [x["titolo"] for pt, x in altre if x not in scelte]
    blocchi, usati = [], 0
    for x in fisse[:3] + scelte + fisse[3:]:
        b = f"--- {x['titolo']} ---\n{x['testo']}"
        if usati + len(b) > limite:
            continue
        usati += len(b)
        blocchi.append(b)
    if rimaste:
        blocchi.append("ALTRE AREE DEL CATALOGO NON APPROFONDITE QUI (valuta comunque se si applicano): " + "; ".join(rimaste))
    return "\n".join(blocchi)
