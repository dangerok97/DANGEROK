"""Consultazione automatica di fonti normative aperte (ricerca web con domini ufficiali).

Garanzie:
- il quesito e' pseudonimizzato e passa dal filtro (fail-closed): niente dati del caso escono verso la ricerca;
- la ricerca e' limitata ai domini ufficiali elencati;
- ogni fonte consultata viene registrata (URL, data, estratto) e marcata ufficiale/non ufficiale;
- se non si trova una fonte ufficiale, la risposta deve dirlo (nessuna norma "a memoria").
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from urllib.parse import urlparse

from .privacy.pseudonymizer import Pseudonymizer

DOMINI_UFFICIALI = [
    "agenziaentrate.gov.it", "normattiva.it", "gazzettaufficiale.it", "finanze.gov.it", "def.finanze.it",
    "mef.gov.it", "governo.it", "gdf.gov.it", "camera.it", "senato.it", "eur-lex.europa.eu",
    "inps.it", "cortedicassazione.it", "giustiziatributaria.gov.it", "agenziaentrateriscossione.gov.it",
    "mit.gov.it", "enea.it", "gse.it",
]

SYSTEM = """Sei un ricercatore normativo per un ufficio di polizia tributaria italiano. Rispondi a un quesito \
giuridico-tributario consultando SOLO fonti ufficiali reperibili in rete (Agenzia delle Entrate, Normattiva, \
Gazzetta Ufficiale, MEF/Finanze, Governo, Corte di Cassazione, INPS e simili).

Regole:
1. Indica sempre, per ogni affermazione, la fonte (tipo di atto, numero, data) e cita il passaggio rilevante.
2. La disciplina tributaria cambia nel tempo: individua la versione vigente nel PERIODO D'IMPOSTA indicato e segnala
   modifiche successive rilevanti (data e atto).
3. Se le fonti ufficiali sono discordanti, incomplete o non reperite, dillo esplicitamente: non colmare i vuoti.
4. Distingui norma, prassi amministrativa (circolari, risoluzioni, risposte a interpello) e giurisprudenza.
5. Non hai dati sul caso concreto e non devi chiederli: rispondi solo sul quesito generale.
6. Struttura: 'Sintesi', 'Norme e prassi applicabili al periodo', 'Punti dubbi o discordanti', 'Fonti'."""


@dataclass
class Fonte:
    url: str
    titolo: str = ""
    estratto: str = ""
    dominio: str = ""
    ufficiale: bool = False


@dataclass
class Ricerca:
    quesito: str
    periodo: str
    risposta: str
    fonti: list[Fonte] = field(default_factory=list)
    consultata_il: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))

    @property
    def senza_fonti_ufficiali(self) -> bool:
        return not any(f.ufficiale for f in self.fonti)


def e_ufficiale(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in DOMINI_UFFICIALI)


def _get(o, k, d=None):
    return o.get(k, d) if isinstance(o, dict) else getattr(o, k, d)


def _raccogli(content) -> tuple[str, list[Fonte]]:
    testo, fonti, visti = [], [], {}
    for b in content:
        tipo = _get(b, "type", "")
        if tipo == "text":
            testo.append(_get(b, "text", "") or "")
            for c in _get(b, "citations", None) or []:
                url = _get(c, "url", "")
                if url:
                    f = visti.setdefault(url, Fonte(url, _get(c, "title", "") or "", "", urlparse(url).hostname or "",
                                                    e_ufficiale(url)))
                    if not f.estratto:
                        f.estratto = (_get(c, "cited_text", "") or "")[:1200]
        elif tipo == "web_search_tool_result":
            cont = _get(b, "content", None)
            if isinstance(cont, list):
                for r in cont:
                    url = _get(r, "url", "")
                    if url:
                        visti.setdefault(url, Fonte(url, _get(r, "title", "") or "", "", urlparse(url).hostname or "",
                                                    e_ufficiale(url)))
    fonti.extend(visti.values())
    return "".join(testo), fonti


def ricerca_normativa(pseudo: Pseudonymizer, quesito: str, periodo: str, *, client, modello: str,
                      max_continuazioni: int = 5) -> Ricerca:
    """`quesito` deve essere GENERALE (es. 'Trattamento reddituale del credito 110% da sconto in fattura per un
    professionista in regime ordinario'). Viene comunque filtrato e, se contiene dati riconoscibili, bloccato."""
    user = f"PERIODO D'IMPOSTA: {periodo}\nQUESITO: {quesito}"
    user = pseudo.anonimizza_o_blocca(user)
    tools = [
        {"type": "web_search_20260209", "name": "web_search", "max_uses": 8, "allowed_domains": DOMINI_UFFICIALI,
         "user_location": {"type": "approximate", "country": "IT"}},
        {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 8, "allowed_domains": DOMINI_UFFICIALI,
         "citations": {"enabled": True}},
    ]
    messaggi = [{"role": "user", "content": user}]
    content_tot: list = []
    for _ in range(max_continuazioni + 1):
        r = client.messages.create(model=modello, max_tokens=16000, system=SYSTEM, tools=tools,
                                   thinking={"type": "adaptive"}, output_config={"effort": "high"},
                                   messages=messaggi)
        content_tot.extend(r.content)
        if getattr(r, "stop_reason", None) == "pause_turn":
            messaggi = [{"role": "user", "content": user}, {"role": "assistant", "content": list(content_tot)}]
            continue
        break
    testo, fonti = _raccogli(content_tot)
    return Ricerca(quesito=quesito, periodo=periodo, risposta=testo.strip(), fonti=fonti)
