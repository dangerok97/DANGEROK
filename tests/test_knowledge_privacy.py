"""Nessun dato personale nei file di conoscenza del repository (schede e brani di stile dei precedenti)."""
import pathlib
import re

import pytest

from app import chat, metodo
from app.privacy import pseudonymizer as ps

FILE = sorted((pathlib.Path(metodo.__file__).parent / "knowledge").rglob("*.md"))
# dati istituzionali pubblici del Reparto, ammessi
AMMESSI = ["via Delle Fiamme Gialle, n. 1", "via delle Fiamme Gialle n. 1", "0766/856028", "vt1120000p@pec.gdf.it"]
# parole che in un atto sono maiuscole ma non sono nomi di persone o enti
OK_MAIUSCOLE = {"amministrazioni", "centrali", "gli", "ufficiali", "utilizzato", "dalla", "riscontri", "materiali", "materiale",
                "comunicazioni", "lipe", "nucleo", "speciale", "relativo", "agli", "obblighi", "differenze", "rispetto",
                "presunzione", "legale", "conclusioni", "sul", "credito", "esterna", "pubblici", "piano", "industria",
                "nazionale", "ispettorato", "processi", "verbali", "liquidazione", "versamento", "imposte", "effettuazione",
                "ritenute", "analitico", "normativo", "situazioni", "rilevanti", "violazioni", "differenza","arco", "argo", "atecо", "ateco", "fatture", "corrispettivi", "verbalizzanti", "parte", "fatto", "scheda", "brani",
                "stile", "fattispecie", "struttura", "ragionamento", "operativo", "spunti", "operativi", "formule", "lessico",
                "controllo", "contabile", "controlli", "sostanziali", "violazioni", "formali", "sostanziali", "sezione",
                "conclusiva", "riscontri", "coerenza", "interna", "analitico", "normativo", "tarquinia", "codice", "attivita",
                "costi", "ricavi", "imposta", "reddito", "impresa", "operazioni", "controllo", "eseguite", "giorno", "riscontro",
                "primo", "enti", "esterni", "territoriale", "indiretto", "presuntivo", "presuntivi", "analitico", "amministratore", "unico", "uffici", "ufficio", "finanziari", "finanziaria", "amministrazione", "societa", "sociale", "ditta", "individuale", "regime", "forfettario", "direttore", "verbale", "ogni", "giornata", "giornate", "successiva", "successive", "ordine", "tuir", "pvc", "pvoc", "pvv", "cnr", "iva", "irpef", "irap", "lgt", "mar", "ten", "cap", "sig",
                "autorità", "autorita", "giudiziaria", "sostituto", "procuratore", "procura", "repubblica", "europea", "tribunale",
                "corte", "cassazione", "agenzia", "entrate", "dogane", "monopoli", "guardia", "finanza", "reparto", "reparti",
                "comandante", "regionale", "comando", "generale", "garante", "contribuente", "statuto", "diritti", "banca", "dati",
                "black", "list", "conto", "corrente", "tax", "report", "commissione", "tributaria", "provinciale", "regionale",
                "direzione", "divisione", "settore", "sezione", "analisi", "strategie", "antifrode", "gruppo", "compagnia", "tenenza",
                "versione", "definitiva", "sulle", "riflessi", "fissa", "persona", "fisica", "evasore", "totale", "comuni", "dirette", "polizia", "economico", "finanziaria", "spa", "srl", "srls", "snc", "sas", "stabilimento", "balneare"}


def _pulito(t: str) -> str:
    for a in AMMESSI:
        t = t.replace(a, " ")
    t = re.sub(r"via (?:delle )?Fiamme Gialle,? n\. ?1", " ", t, flags=re.I)
    # date di atti normativi o di prassi (circolari, risoluzioni, leggi): pubbliche
    return re.sub(r"(?:circolare|risoluzione|legge|sentenza|ordinanza)[^;\n]{0,160}?(?:del|datata) \d{1,2}[/.]\d{1,2}[/.](?:19|20)\d{2}", " ", t, flags=re.I)


@pytest.mark.parametrize("f", FILE, ids=lambda p: p.name)
def test_nessun_dato_personale(f):
    t = _pulito(f.read_text(encoding="utf-8"))
    assert not [m.group(0) for m in ps.RE_CF.finditer(t) if ps.cf_valido(m.group(0))], "codice fiscale"
    assert not re.search(r"\b\d{11}\b", t), "partita IVA / numero a 11 cifre"
    assert not ps.RE_EMAIL.search(t), "indirizzo e-mail"
    assert not [m.group(0) for m in ps.RE_IBAN_CAND.finditer(t) if ps.iban_valido(m.group(0))], "IBAN"
    assert not ps.RE_INDIRIZZO.search(t), "indirizzo"
    assert not ps.RE_TARGA.search(t), "targa"
    assert not re.search(r"\b\d{1,2}[/.]\d{1,2}[/.](?:19|20)\d{2}\b", t), "data completa riferibile a un caso reale (usare «data»)"
    sospetti = [n for n in chat.nomi_sospetti(t) if not all(w.lower() in OK_MAIUSCOLE for w in n.split())]
    assert not sospetti, f"possibili nomi propri: {sospetti}"


METODO = [f for f in FILE if f.parent.name == "metodo"]


@pytest.mark.parametrize("f", METODO, ids=lambda p: p.name)
def test_formato_valido(f):
    v = metodo._leggi_integrato(f)
    assert v and v["titolo"] and v["tag"] and v["scheda"] and v["tipo"] in ("precedente", "spunto")
    assert v["atto"] in ("PVOC", "PVV", "PVC", "CNR", "")


def test_gli_integrati_entrano_nella_selezione():
    voci = metodo.integrati()
    assert voci
    sel = metodo.seleziona(voci, "controllo forfettario reverse charge causa di esclusione", "PVC")
    assert sel and all(v["integrato"] for v in sel)
