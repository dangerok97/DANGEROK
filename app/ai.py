"""Assistente di redazione. Ogni invio verso l'AI passa dal filtro di pseudonimizzazione (fail-closed)."""
from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass

from .privacy.pseudonymizer import LeakError, Pseudonymizer  # noqa: F401  (LeakError riesportato)

_KNOW = pathlib.Path(__file__).parent / "knowledge"

SYSTEM_BASE = """Sei un assistente che prepara BOZZE di atti della Guardia di Finanza (controlli e verifiche fiscali) \
per il militare che li firmera'. Il militare e' l'autore e resta responsabile del contenuto.

Regole inderogabili:
1. La fonte normativa e' la Circolare 1/2018 (Vol. I-IV): rispetta l'ordine delle fasi e i contenuti obbligatori indicati nel contesto.
2. Imita il lessico e la struttura del Reparto descritti qui sotto e negli esempi forniti.
3. Non inventare mai fatti, importi, date, orari, protocolli, nominativi o esiti. Se un dato manca scrivi [DA COMPILARE: cosa serve].
4. Usa i segnaposto tra parentesi quadre (es. [PERSONA_1]) esattamente come li ricevi; non tentare di ricostruire i dati reali.
5. Se il contesto non consente di redigere il passaggio richiesto, dillo in modo esplicito invece di riempire il vuoto.
6. Rispondi solo con il testo dell'atto (o della sezione), in italiano formale."""


class AIDisattivata(Exception):
    pass


class AIRifiutata(Exception):
    pass


def playbook() -> str:
    p = _KNOW / "playbook_reparto.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


@dataclass
class Bozza:
    testo: str                # gia' con i dati reali ripristinati
    inviato: str              # esattamente cio' che e' uscito (pseudonimizzato)
    token_sconosciuti: list[str]
    modello: str


def costruisci_pseudonimizzatore(dati: dict) -> Pseudonymizer:
    """Popola il filtro con l'anagrafica della pratica (soggetto, rappresentanti, verbalizzanti, terzi)."""
    p = Pseudonymizer()
    s = dati.get("soggetto", {}) or {}
    for pers in s.get("persone", []):
        p.aggiungi_persona(pers)
    for ente in s.get("enti", []):
        p.aggiungi_ente(ente)
    for cf in s.get("codici_fiscali", []):
        p.aggiungi_identificativo(cf, "CF")
    for iva in s.get("partite_iva", []):
        p.aggiungi_identificativo(iva, "PIVA")
    for ind in s.get("indirizzi", []):
        p.aggiungi_identificativo(ind, "INDIRIZZO")
    for m in dati.get("verbalizzanti", []) or []:
        p.aggiungi_persona(m, categoria="MILITARE")
    for t in dati.get("terzi", []) or []:
        (p.aggiungi_ente if t.get("tipo") == "ente" else p.aggiungi_persona)(t["nome"])
    return p


def prepara_richiesta(pseudo: Pseudonymizer, *, istruzione: str, contesto: str, checklist: list[str],
                      esempi: list[str] | None = None) -> tuple[str, str]:
    """Restituisce (system, user) GIA' pseudonimizzati; solleva LeakError se resta qualcosa di riconoscibile."""
    esempi_txt = "\n\n".join(f"--- ESEMPIO DI STILE ---\n{e}" for e in (esempi or []))
    user = (f"COMPITO:\n{istruzione}\n\nCONTENUTI OBBLIGATORI DA VERIFICARE (dalla circolare):\n"
            + "\n".join(f"- {c}" for c in checklist)
            + f"\n\nCONTESTO DELLA PRATICA (dati e appunti dell'operatore):\n{contesto}\n\n{esempi_txt}")
    user_anon = pseudo.anonimizza_o_blocca(user)
    system = SYSTEM_BASE + "\n\nMODO DI OPERARE DEL REPARTO:\n" + playbook()
    return system, user_anon


def _client():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise AIDisattivata("ANTHROPIC_API_KEY non configurata: assistente AI disattivato.")
    import anthropic
    return anthropic.Anthropic()


def genera_bozza(pseudo: Pseudonymizer, *, istruzione: str, contesto: str, checklist: list[str],
                 esempi: list[str] | None = None, modello: str = "claude-opus-5-5", client=None) -> Bozza:
    system, user = prepara_richiesta(pseudo, istruzione=istruzione, contesto=contesto,
                                     checklist=checklist, esempi=esempi)
    client = client or _client()
    risposta = client.beta.messages.create(
        model=modello,
        max_tokens=16000,
        system=system,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": user}],
    )
    if getattr(risposta, "stop_reason", None) == "refusal":
        raise AIRifiutata("Il modello ha rifiutato la richiesta (stop_reason=refusal).")
    testo = "".join(b.text for b in risposta.content if getattr(b, "type", "") == "text")
    ripristinato, ignoti = pseudo.ripristina(testo)
    return Bozza(ripristinato, system + "\n\n" + user, ignoti, getattr(risposta, "model", modello))
