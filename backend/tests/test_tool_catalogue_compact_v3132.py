"""
Il catalogo degli strumenti, scritto più corto senza perdere niente.

    QUELLO CHE IL MODELLO DEVE SAPERE NON CAMBIA. CAMBIA QUANTO PESA.

Il catalogo viaggia in ogni chiamata al modello, a ogni passo di ragionamento,
su ogni canale. Misurato su una telefonata: trentanove strumenti, 30.818
caratteri, il settantanove per cento del payload — e il modello ci metteva
1,3 secondi soltanto a rileggerli.

Qui si verifica la cosa che rende sicuro accorciarli: che non manchi niente
di quello che serve a **scegliere** uno strumento e a **chiamarlo**. Se un
giorno questa resa perdesse un argomento, un valore ammesso o una riga di
descrizione, queste prove cadono — prima che lo scopra una persona al
telefono a cui ORA ha risposto con lo strumento sbagliato.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

HERE = Path(_BACKEND)


def _catalogue():
    import deps
    from conversation_engine.ai_core.tools.registry import ToolRegistry

    return ToolRegistry(deps.db).list_public()


def test_nothing_a_model_needs_to_choose_a_tool_is_lost():
    """
    §19: ogni nome, ogni argomento, ogni vincolo sopravvive.

    Non è un confronto di lunghezza: è strumento per strumento, argomento per
    argomento. Un catalogo più corto che ha perso il nome di un parametro non
    è più corto, è rotto.
    """
    from conversation_engine.ai_core.tools.compact import as_one_line

    tools = _catalogue()
    assert tools, "nessuno strumento: la prova non proverebbe niente"

    for tool in tools:
        riga = as_one_line(tool)
        nome = tool.get("capability") or tool.get("name")

        assert nome in riga, f"manca il nome dello strumento: {nome}"

        # La descrizione dello strumento — dove stanno scritti i vincoli veri,
        # tipo «mai per spostare qualcosa che esiste già».
        detto = (tool.get("description") or "").strip()
        if detto:
            assert detto in riga, f"la descrizione di {nome} è stata tagliata"

        schema = tool.get("input_schema") or {}
        proprieta = schema.get("properties") or {}
        obbligatori = set(schema.get("required") or [])

        for arg, spec in proprieta.items():
            assert arg in riga, f"{nome}: manca l'argomento {arg}"

            if not isinstance(spec, dict):
                continue

            # Obbligatorio o no: sbagliarlo significa chiamate rifiutate.
            marchio = f"{arg}?:" in riga
            if arg in obbligatori:
                assert not marchio, f"{nome}.{arg} è obbligatorio e sembra opzionale"
            else:
                assert marchio, f"{nome}.{arg} è opzionale e sembra obbligatorio"

            # I valori ammessi: senza, il modello li inventa.
            for valore in (spec.get("enum") or []):
                assert str(valore) in riga, (
                    f"{nome}.{arg}: manca il valore ammesso {valore}"
                )

            # E la descrizione di un parametro non è decorazione: è dove sta
            # scritto che un formato è ISO 8601.
            nota = (spec.get("description") or "").strip()
            if nota:
                assert nota in riga, f"{nome}.{arg}: persa la nota «{nota[:40]}»"


def test_the_compact_catalogue_is_actually_smaller():
    """
    §19: e pesa davvero meno, se no non serviva a niente.

    Il numero è il motivo per cui questo file esiste. Se la resa compatta
    smettesse di essere più corta, sarebbe solo un altro formato da mantenere.
    """
    from conversation_engine.ai_core.tools.compact import compact_catalogue

    tools = _catalogue()
    prima = len(json.dumps(tools, ensure_ascii=False))
    dopo = len(json.dumps(compact_catalogue(tools), ensure_ascii=False))

    assert dopo < prima * 0.75, (
        f"il catalogo compatto pesa {dopo} contro {prima}: non basta"
    )
    # E ogni strumento è ancora lì: accorciare non è perderne per strada.
    assert len(compact_catalogue(tools)) == len(tools)


def test_the_payload_carries_the_compact_form():
    """
    §19: ed è quella che parte davvero verso il modello.

    Una resa più corta calcolata e non spedita è lavoro buttato: qui si
    guarda il payload vero.
    """
    from conversation_engine.ai_core.prompt import build_user_payload

    tools = _catalogue()
    payload = json.loads(
        build_user_payload(
            user_message="che giorno è oggi?",
            recent_turns=[], active_goal=None, context_facts=[],
            tools=tools, observations=[],
        )
    )
    catalogo = payload.get("available_tools")
    assert isinstance(catalogo, list) and catalogo
    assert all(isinstance(r, str) for r in catalogo), (
        "nel payload ci sono ancora gli oggetti interi"
    )
    # Tutti gli strumenti sono nominati.
    intero = "\n".join(catalogo)
    for tool in tools:
        assert (tool.get("capability") or "") in intero
