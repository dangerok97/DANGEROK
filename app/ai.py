"""Assistente di redazione. Ogni invio verso l'AI passa dal filtro di pseudonimizzazione (fail-closed)."""
from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass, field

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
6. Rispondi solo con il testo dell'atto (o della sezione), in italiano formale.
7. Dopo OGNI passaggio significativo dell'atto aggiungi, subito dopo, una spiegazione per l'operatore nel formato \
{{SPIEGA: ...}} (su una sola riga, senza andare a capo dentro le graffe). La spiegazione dice PERCHE' hai scritto quel passaggio: \
la fase e il punto della circolare o la norma/fonte da cui deriva, il dato o l'appunto su cui si basa, eventuali cautele o \
verifiche da fare prima della firma. Le spiegazioni sono destinate a essere cancellate dall'operatore: non farle mai \
parte del testo dell'atto e non usarle per introdurre fatti nuovi. Se non sei certo di un riferimento normativo scrivilo nella \
spiegazione ('da verificare').
8. IMPORTI: non scrivere mai in cifre un importo che hai calcolato o ricavato da documenti. Se compare nell'elenco \
IMPORTI TRACCIATI, scrivi {{IMPORTO:id}} (il programma inserisce il valore e il calcolo). Puoi riportare cosi' come sono \
solo gli importi scritti dall'operatore negli appunti. Se ti serve un importo non presente, scrivi \
[DA COMPILARE: importo ...] e non stimarlo.
9. FORMA: non scrivere stemma, intestazione del Reparto ne' numeri di pagina (li mette il programma). Per i verbali inizia \
dal titolo (es. PROCESSO VERBALE DI OPERAZIONI COMPIUTE); i titoletti vanno in MAIUSCOLO su una riga (VERBALIZZANTI, PARTE, FATTO...); \
gli elenchi con "- "; chiudi con la riga "I VERBALIZZANTI    LA PARTE" se l'atto prevede le firme."""


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
    importi_non_tracciati: list[str] = field(default_factory=list)


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
                      esempi: list[str] | None = None, registro=None) -> tuple[str, str]:
    """Restituisce (system, user) GIA' pseudonimizzati; solleva LeakError se resta qualcosa di riconoscibile."""
    esempi_txt = "\n\n".join(f"--- ESEMPIO DI STILE ---\n{e}" for e in (esempi or []))
    importi = (f"IMPORTI TRACCIATI (usa {{{{IMPORTO:id}}}}):\n{registro.elenco_per_prompt()}\n\n"
               if registro is not None and registro.voci else "IMPORTI TRACCIATI: nessuno disponibile.\n\n")
    user = (f"COMPITO:\n{istruzione}\n\n{importi}CONTENUTI OBBLIGATORI DA VERIFICARE (dalla circolare):\n"
            + "\n".join(f"- {c}" for c in checklist)
            + f"\n\nCONTESTO DELLA PRATICA (dati e appunti dell'operatore):\n{contesto}\n\n{esempi_txt}")
    user_anon = pseudo.anonimizza_o_blocca(user)
    system = SYSTEM_BASE + "\n\nMODO DI OPERARE DEL REPARTO:\n" + playbook()
    return system, user_anon


def configurazione() -> dict:
    """Quale servizio AI e' configurato. LLM_PROVIDER = anthropic | gemini | openai_compat (vuoto = automatico)."""
    e = os.environ.get
    prov = (e("LLM_PROVIDER") or "").lower()
    if not prov:
        prov = "anthropic" if e("ANTHROPIC_API_KEY") else "gemini" if e("GEMINI_API_KEY") else "anthropic"
    if prov == "gemini":
        from .llm_compat import GEMINI_MODELLO_PREDEFINITO
        chiave, modello, base = e("GEMINI_API_KEY", ""), e("LLM_MODEL") or GEMINI_MODELLO_PREDEFINITO, None
    elif prov == "openai_compat":
        chiave, modello, base = e("LLM_API_KEY", ""), e("LLM_MODEL", ""), e("LLM_BASE_URL", "")
    else:
        prov, chiave, modello, base = "anthropic", e("ANTHROPIC_API_KEY", ""), e("ANTHROPIC_MODEL") or "claude-opus-5-5", None
    attiva = bool(chiave) and (prov != "openai_compat" or bool(base and modello))
    return {"provider": prov, "attiva": attiva, "modello": modello, "base_url": base, "chiave": chiave,
            "chiave_mascherata": ("…" + chiave[-4:]) if len(chiave) >= 12 else "",
            "ricerca_web": prov in ("anthropic", "gemini"), "gratuito_con_dati_usati": prov in ("gemini",)}


def _client():
    c = configurazione()
    if not c["attiva"]:
        raise AIDisattivata("Assistente AI disattivato: manca la chiave (vedi Impostazioni).")
    if c["provider"] == "anthropic":
        import anthropic
        return anthropic.Anthropic()
    from .llm_compat import GEMINI_BASE_URL, CompatClient
    return CompatClient(c["base_url"] or GEMINI_BASE_URL, c["chiave"], c["modello"])


def genera_bozza(pseudo: Pseudonymizer, *, istruzione: str, contesto: str, checklist: list[str],
                 esempi: list[str] | None = None, modello: str = "claude-opus-5-5", client=None,
                 registro=None) -> Bozza:
    from . import calcoli
    registro = registro if registro is not None else calcoli.Registro()
    system, user = prepara_richiesta(pseudo, istruzione=istruzione, contesto=contesto,
                                     checklist=checklist, esempi=esempi, registro=registro)
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
    corpo = "\n".join(r for r in testo.splitlines() if r.strip() and not r.strip().upper().startswith("PROCESSO VERBALE"))
    if not corpo.strip():
        motivo = " (risposta interrotta: limite di lunghezza raggiunto)" if getattr(risposta, "stop_reason", None) == "max_tokens" else ""
        raise AIRifiutata("Il servizio AI ha restituito un testo vuoto o quasi" + motivo + ". Nulla e' stato salvato: riprova.")
    ripristinato, ignoti = pseudo.ripristina(testo)
    ripristinato = calcoli.risolvi_importi(ripristinato, registro)
    ripristinato, non_tracciati = calcoli.segnala_non_tracciati(ripristinato, registro,
                                                                calcoli.importi_da_testo(contesto))
    return Bozza(ripristinato, system + "\n\n" + user, ignoti, getattr(risposta, "model", modello),
                 non_tracciati)


def chiama_chat(client, modello: str, system: str, messaggi: list[dict], max_tokens: int = 8000, on_delta=None):
    """Un turno di conversazione (system e messaggi gia' pseudonimizzati). Restituisce (testo, stop_reason, modello)."""
    extra = {"on_delta": on_delta} if on_delta and type(client).__name__ == "CompatClient" else {}
    risposta = client.beta.messages.create(
        model=modello, max_tokens=max_tokens, system=system, messages=messaggi,
        thinking={"type": "adaptive"}, output_config={"effort": "medium"},
        betas=["server-side-fallback-2026-07-01"], fallbacks="default", **extra)
    if getattr(risposta, "stop_reason", None) == "refusal":
        raise AIRifiutata("Il modello ha rifiutato la richiesta (stop_reason=refusal).")
    testo = "".join(b.text for b in risposta.content if getattr(b, "type", "") == "text")
    if not testo.strip():
        raise AIRifiutata("Il servizio AI ha restituito una risposta vuota: riprova.")
    return testo, getattr(risposta, "stop_reason", None), getattr(risposta, "model", modello)
