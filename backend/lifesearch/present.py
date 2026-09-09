"""
I risultati, raggruppati per significato e detti come li direbbe una persona.

    UNA RICERCA CHE RESTITUISCE UN ELENCO PIATTO HA GIA' PERSO.

«Casa» non ha un tipo di risposta: ha una situazione in corso, dei soldi che
ci girano intorno, un appuntamento, forse una carta. Metterli in fila per
punteggio li rende tutti uguali e nessuno utile. Metterli in gruppi con i
nomi che hanno nella vita di chi cerca — situazioni, cose che so, appuntamenti,
documenti, comunicazioni — li rende leggibili in un secondo.

Tre cose che non escono mai di qui: gli id, i punteggi, e il modo in cui una
riga e' stata trovata. Il primo non serve a nessuno, il secondo e' una
misura di noi e non di lui, il terzo e' una scusa travestita da spiegazione.

E una che esce sempre: da dove ORA sa quello che dice. Non «provenance:
bank», ma «l'ho visto quando il conto era collegato» — che e' la stessa cosa
detta a qualcuno.
"""

from __future__ import annotations

from typing import Any, Dict, List

# I gruppi, nell'ordine in cui una persona li vuole. Le situazioni per prime
# perche' sono la cosa a cui tutto il resto appartiene; i movimenti per
# ultimi perche' sono la piu' grezza.
GROUPS = (
    ("situazioni", "SITUAZIONI"),
    ("cose_che_ora_sa", "COSE CHE ORA SA"),
    ("da_chiarire", "DA CHIARIRE"),
    ("appuntamenti", "APPUNTAMENTI"),
    ("comunicazioni", "COMUNICAZIONI"),
    ("documenti", "DOCUMENTI"),
    ("cambiamenti", "COSA È CAMBIATO"),
    ("movimenti", "MOVIMENTI"),
)

# Come si dice, a una persona, da dove viene una cosa.
IN_WORDS = {
    "person": "me l'hai detto tu",
    "confermato da te": "me l'hai confermato tu",
    "calendar": "l'ho letto nel tuo calendario",
    "email": "l'ho letto in una mail",
    "document": "l'ho trovato in un documento",
    "bank": "l'ho visto sul tuo conto",
}


def how_ora_knows(said: str) -> str:
    """
    La provenienza, in italiano.

    Le frasi che arrivano dal modello finanziario sono gia' scritte per una
    persona — «compare regolarmente sul conto», «quando era collegato» — e
    passano intatte. Le altre sono nomi di fonti, e vanno tradotte.
    """
    text = (said or "").strip()
    if not text:
        return ""
    if " " in text:
        return text
    return IN_WORDS.get(text.lower(), text)


def as_sections(found, *, wanted: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    I gruppi non vuoti, con dentro righe pronte da leggere.

    Un gruppo vuoto non compare: una sezione «Documenti» che dice «nessuno»
    e' rumore in una schermata che esiste per togliere rumore.
    """
    sections: List[Dict[str, Any]] = []
    for key, label in GROUPS:
        rows = found.rows.get(key) or []
        if not rows:
            continue
        sections.append({
            "gruppo": label,
            "cosa_c_e": [_clean(row, key, wanted) for row in rows],
        })
    return sections


def _clean(row: Dict[str, Any], group: str, wanted: Dict[str, Any]) -> Dict[str, Any]:
    """Una riga senza niente di tecnico dentro."""
    out: Dict[str, Any] = {"cosa": row.get("cosa") or ""}

    for key in ("quanto", "quando", "dove", "ogni_quanto", "verso",
                "in_una_riga", "prima", "dopo", "invece_di",
                # Perche' questa cosa e' qui, e quante volte la si e' vista.
                # Due frasi, non due numeri.
                "perche_e_qui", "anche_altrove"):
        if row.get(key):
            out[key] = row[key]

    if row.get("stato"):
        # SO · PENSO: la differenza che regge tutto il resto.
        out["stato"] = row["stato"]
    if row.get("come_lo_so"):
        out["come_lo_so"] = how_ora_knows(str(row["come_lo_so"]))
    if row.get("da_chiarire") and group == "situazioni":
        out["da_chiarire"] = row["da_chiarire"]
    if row.get("apri"):
        out["apri"] = row["apri"]
    if group == "movimenti" and row.get("quante_volte"):
        out["quante_volte"] = row["quante_volte"]
    return out


def conflicts_kept(found) -> List[Dict[str, Any]]:
    """
    Due verita' diverse restano due.

        IL CODICE NON SCEGLIE QUALE FONTE DICE IL VERO.

    Quando c'e' una domanda aperta su una cosa che ORA gia' sa, la risposta
    non e' il numero piu' recente: sono i due numeri, con chi li ha detti.
    """
    known = {
        " ".join(str(r.get("cosa") or "").lower().split()): r
        for r in (found.rows.get("cose_che_ora_sa") or [])
    }
    out: List[Dict[str, Any]] = []
    for asking in found.rows.get("da_chiarire") or []:
        name = " ".join(str(asking.get("cosa") or "").lower().split())
        match = known.get(name)
        if not match:
            continue
        out.append({
            "su_cosa": asking.get("cosa"),
            "so": {"quanto": match.get("quanto"),
                   "come_lo_so": how_ora_knows(str(match.get("come_lo_so") or ""))},
            "ho_letto": {"quanto": asking.get("quanto"),
                         "come_lo_so": how_ora_knows(str(asking.get("come_lo_so") or ""))},
            "in_parole": (
                f"Ho due informazioni diverse su «{asking.get('cosa')}»: "
                f"{match.get('quanto')} — {how_ora_knows(str(match.get('come_lo_so') or ''))} — "
                f"e {asking.get('quanto')}, che ho solo letto. Non scelgo io."
            ),
        })
    return out
