"""Proposta di compilazione della sezione C dell'Allegato 23 (le sezioni A e B arrivano dalla banca dati).

L'AI usa solo i dati della pratica e delle sezioni A/B. Non inventa fatti: un campo non ricavabile resta
[DA COMPILARE: ...]. Non sovrascrive mai un campo che l'operatore ha gia' scritto.
"""
from __future__ import annotations

import json
import re

from .privacy.pseudonymizer import Pseudonymizer
from .schede import Campo

PROMPT = """Aiuti un militare a completare la SEZIONE C della 'Scheda di preparazione e autorizzazione del controllo' \
(Allegato 23 del Vol. IV della Circolare 1/2018 GdF). Le sezioni A e B sono gia' compilate dalla banca dati e ti vengono \
fornite come contesto. Per ciascun campo C indicato scrivi una proposta di testo nel lessico del Reparto: formale, sintetico, \
alla terza persona.

Regole:
1. Usa SOLO le informazioni fornite (sezioni A e B, profilo del caso, ragione dell'intervento, appunti). Non inventare fatti, \
   date, importi, precedenti, sopralluoghi o consultazioni di banche dati che non risultano.
2. Se un campo non e' ricavabile, il testo deve essere '[DA COMPILARE: cosa serve]'.
3. C1 (risultanze agli atti) e C2 (accertamenti svolti) descrivono attivita' e fonti reali: compilali solo con cio' che e' \
   documentato nel contesto; altrimenti [DA COMPILARE].
4. C3 (ragioni giustificative): precisa se il controllo e' d'iniziativa o a richiesta di altri e la fonte di innesco, solo se \
   indicata. C4: atto di gestione o necessita' ricognitiva, arco temporale e tributi. C5: luogo di esecuzione. C6: metodologia \
   ispettiva prevista, coerente con le fasi della circolare (controllo contabile, riscontri di coerenza interna/esterna, \
   indiretto-presuntivo, analitico-normativo, versamenti) e con il profilo, senza promettere attivita' non pertinenti.
5. Usa i segnaposto tra parentesi quadre (es. [PERSONA_1]) esattamente come li ricevi.
6. Per ogni campo aggiungi una 'spiegazione' per l'operatore: da quale dato del contesto o punto della circolare deriva il \
   testo e cosa verificare prima della firma.

Rispondi SOLO con un oggetto JSON: {"C1": {"testo": "...", "spiegazione": "..."}, "C2": {...}, ...} limitato ai campi richiesti."""


def proponi_sezione_c(pseudo: Pseudonymizer, *, valori: dict, profilo: dict, appunti: str, campi: list[Campo],
                      client, modello: str) -> dict[str, dict]:
    richiesti = [c for c in campi if c.codice.startswith("C")]
    contesto = {
        "sezioni_A_B_dalla_banca_dati": {k: v for k, v in valori.items() if k[0] in "AB" and (v or "").strip()},
        "profilo": profilo,
        "appunti_operatore": appunti,
        "campi_richiesti": [{"codice": c.codice, "titolo": c.etichetta, "indicazioni": c.aiuto} for c in richiesti],
    }
    user = pseudo.anonimizza_o_blocca(json.dumps(contesto, ensure_ascii=False))
    r = client.beta.messages.create(
        model=modello, max_tokens=12000, system=PROMPT, thinking={"type": "adaptive"},
        output_config={"effort": "high"}, betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        messages=[{"role": "user", "content": user}])
    if getattr(r, "stop_reason", None) == "refusal":
        raise RuntimeError("Il modello ha rifiutato la richiesta.")
    testo = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
    m = re.search(r"\{.*\}", testo, re.S)
    try:
        dati = json.loads(m.group(0)) if m else {}
    except ValueError:
        dati = {}
    out: dict[str, dict] = {}
    for c in richiesti:
        voce = dati.get(c.codice) if isinstance(dati, dict) else None
        t = (voce or {}).get("testo", "") if isinstance(voce, dict) else ""
        sp = (voce or {}).get("spiegazione", "") if isinstance(voce, dict) else ""
        t = t.strip() or f"[DA COMPILARE: proposta non disponibile per {c.codice}]"
        out[c.codice] = {"testo": pseudo.ripristina(t)[0], "spiegazione": pseudo.ripristina(sp.strip())[0]}
    return out
