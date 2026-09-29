"""Piano operativo SUGGERITO dall'app in base al profilo del caso.

Due livelli:
1. regole deterministiche, leggibili e testate (qui sotto): dicono quali fasi e riscontri sono consigliati e perche';
2. raffinamento dell'AI (facoltativo, pseudonimizzato): puo' motivare eccezioni e proporre riscontri specifici,
   senza mai cambiare l'ORDINE delle fasi, che resta quello della Circolare 1/2018.
Il piano e' un suggerimento: l'operatore decide.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict

from .privacy.pseudonymizer import Pseudonymizer
from .workflow import fasi_per

CONSIGLIATA, OPZIONALE, NON_PERTINENTE = "consigliata", "opzionale", "non_pertinente"

FORME = ("impresa", "professionista", "privato", "ente")
REGIMI = ("ordinario", "semplificato", "forfettario", "non_noto")
MODALITA = ("reparto", "accesso")
DOCUMENTI = ("fatture_attive", "fatture_passive", "registri_iva", "dichiarazioni_redditi", "dichiarazione_iva",
             "f24", "estratti_conto", "certificazioni_uniche", "contratti", "banche_dati")


@dataclass
class Suggerimento:
    chiave: str
    esito: str
    motivo: str
    origine: str = "regola"       # regola | ai


def profilo_predefinito() -> dict:
    return {"forma": "impresa", "regime": "non_noto", "modalita": "reparto", "documenti": [],
            "ragione": "", "tributi": ["IIDD", "IVA"]}


def suggerisci_fasi(tipo: str, profilo: dict) -> list[Suggerimento]:
    p = {**profilo_predefinito(), **(profilo or {})}
    forma, regime, modalita = p["forma"], p["regime"], p["modalita"]
    docs = set(p["documenti"])
    tributi = set(p["tributi"])
    ragione = (p.get("ragione") or "").lower()
    out: dict[str, Suggerimento] = {}

    def s(chiave, esito, motivo):
        out[chiave] = Suggerimento(chiave, esito, motivo)

    # invito: solo se si opera presso il Reparto
    s("invito", CONSIGLIATA if modalita == "reparto" else NON_PERTINENTE,
      "Intervento presso il Reparto: si convoca il soggetto e si indica la documentazione da recare."
      if modalita == "reparto" else "Intervento con accesso: l'ordine di accesso sostituisce l'invito.")

    # controllo contabile
    if forma == "privato":
        s("controllo_contabile", NON_PERTINENTE, "Soggetto privato non imprenditore: nessuna contabilita' obbligatoria.")
    elif regime == "forfettario":
        s("controllo_contabile", CONSIGLIATA,
          "Regime forfettario: verificare i pochi adempimenti residui (numerazione e conservazione delle fatture "
          "di acquisto e delle bollette doganali, certificazione dei corrispettivi) e la permanenza dei requisiti.")
    else:
        s("controllo_contabile", CONSIGLIATA,
          "Verificare regolare istituzione, formazione, tenuta e conservazione di scritture e registri obbligatori "
          "per il regime dichiarato.")

    # riscontro materiale
    if modalita == "accesso" and forma in ("impresa", "professionista", "ente"):
        s("riscontro_materiale", CONSIGLIATA,
          "Accesso presso il luogo di esercizio: possibili rilevamento del personale, cespiti, inventario, cassa.")
    else:
        s("riscontro_materiale", NON_PERTINENTE if modalita == "reparto" else OPZIONALE,
          "Nessuna presenza sul luogo di esercizio: il riscontro materiale non e' di norma eseguibile.")

    # coerenza interna
    if {"fatture_attive", "registri_iva"} & docs or "dichiarazioni_redditi" in docs:
        s("coerenza_interna", CONSIGLIATA,
          "Riconciliare fatture emesse/registri/liquidazioni con quanto esposto nelle dichiarazioni.")
    else:
        s("coerenza_interna", OPZIONALE,
          "Mancano ancora documenti e dichiarazioni da riconciliare: acquisirli per poter eseguire il riscontro.")

    # coerenza esterna
    if "banche_dati" in docs or "fatture_passive" in docs or "contratti" in docs or "questionari" in ragione:
        s("coerenza_esterna", CONSIGLIATA,
          "Sono identificabili controparti (fornitori/clienti/cedenti): valutare questionari o controlli incrociati.")
    else:
        s("coerenza_esterna", OPZIONALE, "Valutare controlli presso terzi se emergono controparti rilevanti.")

    # indiretto-presuntivo
    if "estratti_conto" in docs or "indagini" in ragione or "presunt" in ragione:
        s("indiretto_presuntivo", CONSIGLIATA,
          "Dati finanziari disponibili o rilievi di natura presuntiva: prevedere il contraddittorio prima dell'utilizzo.")
    else:
        s("indiretto_presuntivo", OPZIONALE,
          "Utile se emergono incongruenze non spiegate dalla documentazione (es. ricostruzioni, indagini finanziarie).")

    # analitico-normativo
    s("analitico_normativo", CONSIGLIATA,
      "Verificare la corretta applicazione della norma al caso (regime, agevolazioni, trattamento dei componenti).")

    # versamenti
    if ("IVA" in tributi and regime != "forfettario") or (forma == "impresa" and regime == "ordinario"):
        s("versamenti", CONSIGLIATA, "Verificare liquidazioni periodiche, versamenti IVA e ritenute (F24).")
    elif regime == "forfettario":
        s("versamenti", CONSIGLIATA, "Verificare i versamenti dell'imposta sostitutiva e dei contributi (F24).")
    else:
        s("versamenti", OPZIONALE, "Verificare i versamenti se dai dati risultano imposte o ritenute dovute.")

    # riscontro materiale/versamenti fuori dalle fasi lineari eventuali; contraddittorio e conclusione sempre
    s("contraddittorio", CONSIGLIATA, "Fase obbligatoria del percorso.")
    s("conclusione_pvc", CONSIGLIATA, "Fase obbligatoria del percorso.")

    # ordine e completezza rispetto alle fasi del tipo di intervento
    risultato = []
    for f in fasi_per(tipo):
        if f.chiave in out:
            risultato.append(out[f.chiave])
        elif f.condizionale:
            risultato.append(Suggerimento(f.chiave, OPZIONALE, "Si attiva solo se ricorre la condizione prevista."))
        else:
            risultato.append(Suggerimento(f.chiave, CONSIGLIATA, "Fase prevista dal percorso."))
    return risultato


def promemoria_documenti(tipo_soggetto_profilo: dict) -> list[str]:
    """Documenti da acquisire per rendere eseguibili i riscontri che ancora non lo sono."""
    p = {**profilo_predefinito(), **(tipo_soggetto_profilo or {})}
    mancanti = []
    if "dichiarazioni_redditi" not in p["documenti"]:
        mancanti.append("Dichiarazioni dei redditi dei periodi controllati (originarie ed eventuali integrative)")
    if p["regime"] != "forfettario" and "IVA" in p["tributi"] and "dichiarazione_iva" not in p["documenti"]:
        mancanti.append("Dichiarazioni IVA e liquidazioni periodiche")
    if "fatture_attive" not in p["documenti"]:
        mancanti.append("Fatture emesse (XML FatturaPA se possibile) e relativi incassi")
    if "f24" not in p["documenti"]:
        mancanti.append("Modelli F24 e ricevute dei versamenti")
    return mancanti


# ------------------------------------------------------------------ raffinamento AI
PROMPT_RAFFINA = """Hai il profilo di un caso di controllo/verifica fiscale e un piano di fasi suggerito da regole \
deterministiche. Rivedilo alla luce di 'ragione dell'intervento' e del profilo: per ogni fase puoi confermare o \
modificare l'esito (consigliata / opzionale / non_pertinente) e scrivere un motivo concreto e sintetico. Non aggiungere \
ne' togliere fasi, non cambiare l'ordine, non inventare fatti. Rispondi SOLO con JSON: una lista di oggetti \
{"chiave": "...", "esito": "...", "motivo": "..."} limitata alle fasi che modifichi o che vuoi motivare meglio."""


def raffina_con_ai(pseudo: Pseudonymizer, tipo: str, profilo: dict, piano: list[Suggerimento], *,
                   client, modello: str) -> list[Suggerimento]:
    user = json.dumps({"tipo": tipo, "profilo": profilo, "piano": [asdict(x) for x in piano]}, ensure_ascii=False)
    user = pseudo.anonimizza_o_blocca(user)
    r = client.beta.messages.create(
        model=modello, max_tokens=8000, system=PROMPT_RAFFINA, thinking={"type": "adaptive"},
        output_config={"effort": "medium"}, betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        messages=[{"role": "user", "content": user}])
    if getattr(r, "stop_reason", None) == "refusal":
        return piano
    testo = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
    m = re.search(r"\[.*\]", testo, re.S)
    if not m:
        return piano
    try:
        mods = json.loads(m.group(0))
    except ValueError:
        return piano
    valide = {x.chiave for x in piano}
    per_chiave = {x.chiave: x for x in piano}
    for mod in mods if isinstance(mods, list) else []:
        k, e, mot = mod.get("chiave"), mod.get("esito"), (mod.get("motivo") or "").strip()
        if k in valide and e in (CONSIGLIATA, OPZIONALE, NON_PERTINENTE) and mot:
            # le fasi obbligatorie non possono diventare non pertinenti
            fase = next(f for f in fasi_per(tipo) if f.chiave == k)
            if e == NON_PERTINENTE and not fase.facoltativa:
                continue
            per_chiave[k] = Suggerimento(k, e, mot, origine="ai")
    return [per_chiave[x.chiave] for x in piano]
