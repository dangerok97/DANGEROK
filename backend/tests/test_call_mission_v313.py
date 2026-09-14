"""
Una telefonata sola, con dentro solo quello che serve per farla.

    ORA SA TUTTO. CHI TELEFONA SA UNA COSA.

Il fascicolo dello Sprint 3 portava in linea le situazioni aperte della
persona — fino a quattro, con i loro titoli. Serviva a capire di cosa si
parlasse, ed era ragionevole finché a parlare era ORA stessa. Non lo è più
quando a parlare è un modello che vive fuori: un elenco di cose aperte nella
vita di qualcuno non serve a spostare un appuntamento dal dentista.

Queste prove tengono ferme tre cose che, se cedono, trasformano un esecutore
in un secondo assistente:

    quello che non serve non parte;
    quello che non è autorizzato non si accetta;
    quello che si è detto non tocca il mondo finché ORA non lo valida.
"""

from __future__ import annotations

import json
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


def _missione():
    from telephone.mission import CallMissionPacket, MissionFact

    return CallMissionPacket(
        mission_id="mis_prova",
        mission_type="reschedule",
        goal="Spostare l'appuntamento di oggi dalle 16:00 alle 18:00",
        counterparty="Studio Dentistico Bianchi",
        on_behalf_of="Francesco",
        local_datetime="2026-09-14T09:00:00+02:00",
        timezone="Europe/Rome",
        subject="appuntamento dal dentista di oggi",
        current_state={"when": "2026-09-14T16:00:00+02:00"},
        desired_state={"when": "2026-09-14T18:00:00+02:00"},
        allowed_negotiation=[
            "confermare le 18:00 di oggi",
            "accettare il primo orario libero dopo le 18:00 di oggi",
        ],
        forbidden_actions=["accettare una data diversa da oggi"],
        known_facts=[
            MissionFact(
                field="nome_paziente", value="Francesco Cefalà",
                sensitivity="identity",
                why_it_is_here="senza il nome non trovano la prenotazione",
            ),
        ],
        allowed_on_demand_fields=["data_di_nascita"],
        say_this_first="Buongiorno, sono ORA, l'assistente AI di Francesco.",
    )


# ---------------------------------------------------------------------------
# Quello che non serve non parte
# ---------------------------------------------------------------------------

def test_the_phone_number_never_travels_with_the_mission():
    """
    §29: chi parla non ha il numero, e non è una dimenticanza.

        CHI COMPONE È IL TRASPORTO. CHI PARLA NON NE HA BISOGNO.

    Un dato che non serve a chi lo riceve non gli si dà, anche quando è
    innocuo — perché «innocuo» è un giudizio che invecchia male.
    """
    from telephone.mission import CallMissionPacket

    assert "contact" not in CallMissionPacket.model_fields
    assert "phone" not in CallMissionPacket.model_fields
    assert "to_number" not in CallMissionPacket.model_fields

    detto = _missione().for_the_model()
    for cifre in ("+39", "3774714389", "339", "02 "):
        assert cifre not in detto, f"un numero è finito nel pacchetto: {cifre}"


def test_the_packet_carries_the_mission_not_the_person():
    """
    §29: nel pacchetto non entra la vita di nessuno.

    Il fascicolo precedente ci metteva dentro le situazioni aperte. Qui i
    fatti sono un elenco chiuso, e ognuno porta scritto perché è lì: un fatto
    senza motivo è un fatto che prima o poi qualcuno manda perché «tanto
    c'era».
    """
    packet = _missione()
    for fatto in packet.known_facts:
        assert fatto.why_it_is_here.strip(), (
            f"«{fatto.field}» è nel pacchetto senza un motivo scritto"
        )

    detto = json.loads(packet.for_the_model())
    assert set(detto.get("known_facts") or {}) == {"nome_paziente"}
    # E il motivo resta a chi costruisce, non viaggia con chi parla.
    assert "why_it_is_here" not in packet.for_the_model()


def test_the_packet_stays_small():
    """
    §29: piccolo, e si vede.

    Il prompt di ORA pesa 18.811 token e costa due secondi e mezzo a leggerlo.
    Una voce al telefono deve rispondere in uno e mezzo.
    """
    detto = _missione().for_the_model()
    # Quattro caratteri per token è la regola spannometrica di Google, e qui
    # basta: il conto vero lo fa `countTokens`, e su questo pacchetto dice 498.
    assert len(detto) < 4000, f"il pacchetto pesa {len(detto)} caratteri"
    assert '": "' not in detto, "serializzato largo invece che stretto"


def test_empty_fields_do_not_travel():
    """§29: un campo vuoto occupa posto e non dice niente."""
    detto = json.loads(_missione().for_the_model())
    assert "soft_preferences" not in detto
    assert "hard_constraints" not in detto
    assert all(v not in (None, "", [], {}) for v in detto.values())


# ---------------------------------------------------------------------------
# Quello che non è autorizzato non esce
# ---------------------------------------------------------------------------

def test_only_the_allowed_fields_can_be_asked_for():
    """
    §29: l'elenco di cosa si può chiedere è chiuso, e il valore non è dentro.

        NEL PACCHETTO C'È IL NOME DEL CAMPO, MAI IL SUO VALORE.

    Il valore esce solo se qualcuno lo chiede **durante** la chiamata e ORA
    decide di consegnarlo. Metterlo nel pacchetto «per comodità» vorrebbe dire
    averlo già dato.
    """
    packet = _missione()
    assert packet.may_release("data_di_nascita")
    assert packet.may_release("DATA_DI_NASCITA")
    for vietato in ("codice_fiscale", "iban", "indirizzo", "", "  "):
        assert not packet.may_release(vietato), vietato

    detto = _missione().for_the_model()
    assert "data_di_nascita" in detto          # il nome del campo, sì
    assert "1990" not in detto                 # il valore, no


def test_what_is_already_known_is_not_asked_again():
    """§29: quello che sta nel pacchetto non si va a richiedere."""
    packet = _missione()
    assert packet.already_knows("nome_paziente") == "Francesco Cefalà"
    assert packet.already_knows("Nome_Paziente") == "Francesco Cefalà"
    assert packet.already_knows("codice_fiscale") is None


# ---------------------------------------------------------------------------
# Quello che si è detto non tocca il mondo da solo
# ---------------------------------------------------------------------------

def test_only_a_confirmed_success_can_move_anything():
    """
    §29: un resoconto non è un comando.

        CHI HA PARLATO NON SCRIVE NIENTE NEL MONDO.

    «Parziale» e «serve l'utente» sono esiti legittimi, non permessi. Un
    modello che aggiorna un calendario da solo è un modello che può sbagliare
    appuntamento a nome di qualcuno.
    """
    from telephone.mission import CallMissionOutcome

    fatto = CallMissionOutcome(
        mission_id="mis_prova", status="success",
        confirmed_changes={"new_time": "18:00"},
    )
    assert fatto.is_actionable()

    for non_si_tocca in (
        CallMissionOutcome(mission_id="m", status="success"),          # niente da scrivere
        CallMissionOutcome(mission_id="m", status="partial",
                           confirmed_changes={"new_time": "18:00"}),
        CallMissionOutcome(mission_id="m", status="needs_user",
                           confirmed_changes={"new_time": "11:00"}),
        CallMissionOutcome(mission_id="m", status="failed",
                           confirmed_changes={"new_time": "18:00"}),
    ):
        assert not non_si_tocca.is_actionable(), non_si_tocca.status


def test_the_outcome_of_the_dentist_mission_looks_like_this():
    """§29: e l'esito ha la forma che il backend sa validare."""
    from telephone.mission import CallMissionOutcome

    esito = CallMissionOutcome(
        mission_id="mis_prova",
        status="success",
        confirmed_changes={
            "appointment_date": "2026-09-14",
            "old_time": "16:00",
            "new_time": "18:00",
        },
        counterparty_statements=[
            {"kind": "availability", "fact": "18:00 disponibile", "turn": 3},
            {"kind": "confirmation", "fact": "spostato alle 18:00", "turn": 4},
        ],
        followup_required=False,
    )
    assert esito.is_actionable()
    d = esito.model_dump()
    assert d["confirmed_changes"]["new_time"] == "18:00"
    assert d["user_confirmation_needed"] == ""
    # E non c'è nessun posto dove infilare l'audio o il ragionamento.
    for mai in ("audio", "pcm", "reasoning", "transcript_raw"):
        assert mai not in d


def test_a_mission_outside_the_scope_comes_back_to_a_person():
    """
    §29: domani alle undici nessuno l'ha autorizzato.

    È il caso che decide se questo disegno tiene: la controparte propone una
    cosa ragionevole che però non sta nel mandato. L'esito non è un successo
    più piccolo — è una domanda.
    """
    from telephone.mission import CallMissionOutcome

    esito = CallMissionOutcome(
        mission_id="mis_prova",
        status="needs_user",
        rejected_changes=["domani alle 11:00"],
        counterparty_statements=[
            {"kind": "refusal", "fact": "oggi dopo le 18 al completo", "turn": 3},
        ],
        user_confirmation_needed=(
            "Lo studio propone domani alle 11. Va bene o preferisci altro?"
        ),
        followup_required=True,
    )
    assert not esito.is_actionable()
    assert esito.user_confirmation_needed
    assert not esito.confirmed_changes, "ha confermato qualcosa che non poteva"


# ---------------------------------------------------------------------------
# E il runtime classico non si accorge di niente
# ---------------------------------------------------------------------------

def test_the_classic_runtime_does_not_know_about_missions():
    """
    §29: il PoC vive accanto, non dentro.

    Nessun file del runtime telefonico esistente importa la missione: se un
    giorno lo facesse, avremmo due modi di fare la stessa telefonata.
    """
    import ast
    from pathlib import Path

    qui = Path(_BACKEND) / "telephone"
    # `runtime.py` sceglie fra i due ed e il suo mestiere; `live.py` e il
    # runtime a missione; `introduction.py` e il contratto dell'apertura.
    # `history.py` non è un runtime: è il livello che racconta com'è
    # andata, e leggere un esito di missione è il suo mestiere.
    #
    #     E NEMMENO `binding.py` E `application.py` SONO RUNTIME.
    #
    # Sono il livello che viene dopo: uno lega la missione all'oggetto che
    # dovrà cambiare, l'altro prende l'esito validato e lo applica. Leggere
    # una missione è letteralmente tutto quello che fanno — vietarglielo
    # vorrebbe dire tenerli in piedi copiando altrove il nome della missione,
    # che è il modo in cui nascono due verità invece di una.
    suoi = {"mission.py", "live.py", "runtime.py", "introduction.py",
            "history.py", "binding.py", "application.py"}
    for path in sorted(qui.glob("*.py")):
        if path.name in suoi:
            continue
        albero = ast.parse(path.read_text(encoding="utf-8"))
        for nodo in ast.walk(albero):
            if isinstance(nodo, ast.ImportFrom) and (nodo.module or "").endswith(
                "mission"
            ):
                raise AssertionError(f"{path.name} importa la missione")
