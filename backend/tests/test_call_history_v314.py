"""
Com'è andata, raccontato a chi ha chiesto la telefonata.

    QUESTA NON È UNA CONSOLE. È IL RESOCONTO DI UNA COMMISSIONE.

Dall'altra parte non c'è chi ha scritto il runtime: c'è qualcuno che voleva
sapere se l'appuntamento è stato spostato. Queste prove tengono ferme le
quattro cose che rendono un resoconto un resoconto:

    si dice in italiano, non in stati interni;
    non si dichiara fatto quello che nessuno ha confermato;
    «ha risposto» e «ce l'ha fatta» restano due fatti distinti;
    e dell'audio non resta niente, come non è mai restato.
"""

from __future__ import annotations

import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


def _una_chiamata(**cambia):
    from telephone.models import Mandate, PhoneCall

    campi = dict(
        owner_id="u1",
        to_number="+393000000000",
        calling_whom="Studio Dentistico Bianchi",
        session_ref="s1",
        mandate=Mandate(
            why_calling="spostare il mio appuntamento dal dentista di oggi "
                        "dalle 16 alle 18",
            may_agree_to=["confermare le 18:00 di oggi"],
            must_bring_back=["lo studio conferma il nuovo orario"],
        ),
        authorised_at="2026-09-14T08:00:00+00:00",
        started_at="2026-09-14T08:00:10+00:00",
        ended_at="2026-09-14T08:01:02+00:00",
        state="ended",
        how_it_ended="they_hung_up",
        provider_ref="uuid-vonage",
    )
    campi.update(cambia)
    return PhoneCall(**campi)


def _riuscita(**esito):
    """I numeri di una telefonata condotta dal runtime a missione."""
    base = {
        "runtime": "gemini_live",
        "outcome": {
            "mission_id": "mis_1",
            "status": "success",
            "confirmed_changes": {
                "appointment_date": "2026-09-14",
                "old_time": "16:00",
                "new_time": "18:00",
            },
        },
    }
    base["outcome"].update(esito)
    return base


# ---------------------------------------------------------------------------
# §22.A · riuscita
# ---------------------------------------------------------------------------

def test_a_call_that_worked_says_what_was_moved_and_when():
    """
    §22.A / §12: il riassunto nasce dall'esito validato, non da chi ha parlato.

        «APPUNTAMENTO SPOSTATO ALLE 18:00» — NON «mission_status=success».
    """
    from telephone.history import as_a_card

    scheda = as_a_card(_una_chiamata(metrics=_riuscita()))

    assert scheda["presentation_status"] == "completata"
    assert scheda["status_label"] == "Completata"
    assert scheda["outcome_summary"] == "Appuntamento spostato alle 18:00."
    assert scheda["duration_seconds"] == 52
    assert scheda["needs_decision"] is False


def test_the_card_says_nothing_technical():
    """
    §2/§25: in elenco non compare niente che riguardi come è fatta ORA.

    Chi legge voleva sapere se l'appuntamento è stato spostato. Il nome del
    modello, l'identificativo dell'operatore e i token non rispondono a quella
    domanda, e occupano il posto di quello che risponde.
    """
    import json

    from telephone.history import as_a_card

    scheda = as_a_card(_una_chiamata(
        metrics={**_riuscita(), "tokens": {"total": 3039},
                 "tool_calls": 2, "beat_credits_produced": 2390},
        provider_ref="924ae85e-6fa0-494a-983f-2f6033c695d5",
    ))
    detto = json.dumps(scheda, ensure_ascii=False).lower()
    for tecnicismo in ("gemini", "vonage", "924ae85e", "token", "mission_status",
                       "tool_call", "credit", "kore", "playback"):
        assert tecnicismo not in detto, tecnicismo


# ---------------------------------------------------------------------------
# §22.B · serve una decisione
# ---------------------------------------------------------------------------

def test_a_call_that_needs_a_person_says_so_and_why():
    """
    §13: «serve una tua decisione» è uno stato a sé, non un fallimento più
    piccolo.

    E porta con sé la ragione, perché una decisione senza il motivo non è una
    decisione: è una domanda a cui manca la metà.
    """
    from telephone.history import as_a_card, in_full

    chiamata = _una_chiamata(metrics={"outcome": {
        "mission_id": "mis_1",
        "status": "needs_user",
        "user_confirmation_needed": (
            "Lo studio non ha disponibilità oggi. Propone domani alle 11:00."
        ),
        "followup_required": True,
    }})
    scheda = as_a_card(chiamata)
    assert scheda["presentation_status"] == "serve_una_decisione"
    assert scheda["status_label"] == "Serve una tua decisione"
    assert "domani alle 11:00" in scheda["outcome_summary"]
    assert scheda["needs_decision"] is True

    aperta = in_full(chiamata)
    assert "domani alle 11:00" in aperta["needs_user_reason"]
    assert aperta["failure_reason"] == "", "l'ha raccontata come un fallimento"


# ---------------------------------------------------------------------------
# §22.C/D/§20 · nessuno ha risposto
# ---------------------------------------------------------------------------

def test_a_call_nobody_answered_is_still_in_the_history():
    """
    §20: compare anche se non si è parlato con nessuno.

    Una telefonata a cui non ha risposto nessuno è successa: è la risposta
    alla domanda «hai chiamato?», e nasconderla la lascerebbe senza risposta.
    """
    from telephone.history import as_a_card

    scheda = as_a_card(_una_chiamata(
        state="failed", how_it_ended="no_answer",
        started_at=None, ended_at=None,
    ))
    assert scheda["presentation_status"] == "nessuna_risposta"
    assert scheda["outcome_summary"] == "Non ha risposto."
    assert scheda["duration_seconds"] is None
    assert scheda["transcript_available"] is False


def test_a_busy_line_says_the_line_was_busy():
    """§22.D: e «occupato» si dice occupato."""
    from telephone.history import as_a_card

    scheda = as_a_card(_una_chiamata(state="failed", how_it_ended="busy"))
    assert scheda["presentation_status"] == "occupato"
    assert scheda["outcome_summary"] == "Il numero era occupato."


def test_the_line_result_is_read_before_the_mission_result():
    """
    §19: prima com'è andata la linea, poi com'è andata la missione.

    Se nessuno ha risposto non c'è nessuna missione da raccontare, e dire «non
    riuscita» a una telefonata mai cominciata sposterebbe la colpa sul posto
    sbagliato — dal telefono a ORA.
    """
    from telephone.history import how_it_reads

    # Un esito fallito appiccicato a una chiamata senza risposta: vince la linea.
    chiamata = _una_chiamata(
        state="failed", how_it_ended="no_answer",
        metrics={"outcome": {"mission_id": "m", "status": "failed"}},
    )
    assert how_it_reads(chiamata) == "nessuna_risposta"


# ---------------------------------------------------------------------------
# §22.E · due fatti, non uno
# ---------------------------------------------------------------------------

def test_a_call_that_went_fine_can_still_report_that_nothing_was_done():
    """
    §19: `call_status=ended` e `mission_status=failed` insieme sono validi.

        «HA RISPOSTO, E HA DETTO DI NO» SONO DUE FATTI.

    Tenerli in un campo solo obbligherebbe a scegliere quale dei due
    raccontare, e qualunque scelta sarebbe una bugia per metà.
    """
    from telephone.history import in_full

    aperta = in_full(_una_chiamata(metrics={"outcome": {
        "mission_id": "m", "status": "failed",
        "user_confirmation_needed": "Lo studio non trova la prenotazione.",
    }}))
    assert aperta["call_status"] == "ended"
    assert aperta["how_it_ended"] == "they_hung_up"
    assert aperta["mission_status"] == "failed"
    assert aperta["presentation_status"] == "non_riuscita"
    assert aperta["outcome_summary"] == "Lo studio non trova la prenotazione."


def test_a_call_that_answered_but_left_no_outcome_is_not_called_a_success():
    """
    Ha risposto qualcuno e non sappiamo dire cos'è successo.

        NON È UN SUCCESSO E NON È UN FALLIMENTO.

    Sceglierne uno vorrebbe dire inventare. «Interrotta» è quello che è.
    """
    from telephone.history import as_a_card

    scheda = as_a_card(_una_chiamata(metrics={"runtime": "gemini_live"}))
    assert scheda["presentation_status"] == "interrotta"
    assert scheda["outcome_summary"] == (
        "La chiamata si è interrotta prima che riuscissi a concludere.")


# ---------------------------------------------------------------------------
# §22.F · la trascrizione
# ---------------------------------------------------------------------------

def test_the_transcript_keeps_the_order_in_which_it_was_said():
    """
    §9/§10: in ordine, con chi ha parlato, e niente altro.

        IL TESTO C'ERA GIÀ. L'AUDIO NON C'È MAI STATO.
    """
    from telephone.history import the_transcript
    from telephone.models import CallTurn

    chiamata = _una_chiamata(metrics=_riuscita(), turns=[
        CallTurn(who="ora", said="Buongiorno, sono l'assistente di Francesco."),
        CallTurn(who="them", said="Sì, mi dica."),
        CallTurn(who="ora", said="Vorremmo spostarlo alle 18."),
    ])
    battute = the_transcript(chiamata)

    assert [b["sequence_number"] for b in battute] == [0, 1, 2]
    assert [b["speaker"] for b in battute] == ["ora", "counterparty", "ora"]
    assert battute[1]["text"] == "Sì, mi dica."
    # E in ogni battuta c'è solo quello che serve a leggerla.
    assert set(battute[0]) == {"sequence_number", "speaker", "text", "at"}


def test_a_call_with_nothing_said_has_an_empty_transcript_not_an_error():
    """
    §11: non aver parlato con nessuno è un esito, non un guasto.

    Il dettaglio non deve fallire: deve dire perché non c'è niente da leggere.
    """
    from telephone.history import as_a_card

    scheda = as_a_card(_una_chiamata(state="failed", how_it_ended="no_answer"))
    assert scheda["transcript_available"] is False


# ---------------------------------------------------------------------------
# §22.G/H/I · quello che non deve finire qui dentro
# ---------------------------------------------------------------------------

def test_no_audio_ever_reaches_the_history():
    """
    §21: l'audio è un fiume, non un archivio — e non lo diventa adesso.

    Non c'è un campo dove metterlo, e quello che si racconta sono testi, tempi
    e conteggi. Se un giorno qualcuno aggiungesse «il PCM, per il debug»,
    questa prova cade.
    """
    import json
    import re

    from telephone.history import as_a_card, in_full, the_transcript
    from telephone.models import CallTurn

    chiamata = _una_chiamata(
        metrics=_riuscita(), audio_frames=3065, audio_bytes=1961600,
        turns=[CallTurn(who="ora", said="Buongiorno.")],
    )
    tutto = json.dumps(
        [as_a_card(chiamata), in_full(chiamata), the_transcript(chiamata)],
        ensure_ascii=False, default=str,
    )
    for mai in ("pcm", "audio_bytes", "audio_frames", "inlineData", "base64"):
        assert mai not in tutto.lower(), mai
    assert not re.findall(r"[A-Za-z0-9+/]{200,}={0,2}", tutto), "blob sospetto"


def test_the_number_is_in_the_record_but_never_in_the_packet():
    """
    §5: il numero serve a chi legge, non a chi parla.

        CHI COMPONE È IL TRASPORTO. CHI PARLA NON NE HA BISOGNO.

    È la stessa regola di sempre, guardata dall'altro capo: resta fuori dal
    pacchetto della missione, e compare nel resoconto.
    """
    from telephone.dossier import TelephoneCallDossier
    from telephone.history import as_a_card
    from telephone.mission import packet_for

    chiamata = _una_chiamata(metrics=_riuscita())
    scheda = as_a_card(chiamata)
    assert scheda["counterparty_number"] == "+393000000000"

    dossier = TelephoneCallDossier(
        owner_id="u1", call_id=chiamata.id, on_behalf_of="Francesco Cefalà",
    )
    packet = packet_for(chiamata, dossier)
    detto = packet.for_the_model()
    for cifre in ("+39", "3774714389", "393774"):
        assert cifre not in detto, cifre


def test_a_fact_handed_over_during_the_call_does_not_land_in_the_history():
    """
    §21: quello che è stato dato al telefono non si archivia qui.

    La data di nascita è uscita perché la missione l'aveva autorizzata e
    qualcuno l'ha chiesta in quel momento. Rimetterla nel resoconto vorrebbe
    dire conservarla senza che nessuno l'abbia chiesto — e «tanto ce l'avevamo
    già» è il modo in cui i dati si accumulano.
    """
    import json

    from telephone.history import in_full
    from telephone.models import CallTurn

    chiamata = _una_chiamata(
        metrics=_riuscita(),
        turns=[CallTurn(who="ora", said="La data di nascita è il 12 marzo 1990.")],
    )
    aperta = json.dumps(in_full(chiamata), ensure_ascii=False)
    assert "12 marzo 1990" not in aperta, (
        "un dato consegnato al telefono è finito nel riassunto"
    )


# ---------------------------------------------------------------------------
# §22.J · l'ordine
# ---------------------------------------------------------------------------

def test_the_most_recent_call_comes_first():
    """
    §22.J: chi apre questa schermata quasi sempre vuole sapere com'è andata
    quella di poco fa.
    """
    from telephone.history import as_a_card

    tre = [
        _una_chiamata(authorised_at="2026-09-12T09:00:00+00:00"),
        _una_chiamata(authorised_at="2026-09-14T08:00:00+00:00"),
        _una_chiamata(authorised_at="2026-09-13T15:00:00+00:00"),
    ]
    ordinate = sorted(tre, key=lambda c: c.authorised_at, reverse=True)
    quando = [as_a_card(c)["created_at"] for c in ordinate]
    assert quando == sorted(quando, reverse=True)
    assert quando[0].startswith("2026-09-14")


# ---------------------------------------------------------------------------
# E la durata si conta da quando hanno risposto
# ---------------------------------------------------------------------------

def test_the_ringing_is_not_part_of_the_conversation():
    """
    §1: la durata è quella della conversazione, non della chiamata.

    Contare gli squilli farebbe sembrare lunga una telefonata a cui non ha
    risposto nessuno.
    """
    from telephone.history import how_long

    assert how_long(_una_chiamata()) == 52
    assert how_long(_una_chiamata(started_at=None)) is None
    assert how_long(_una_chiamata(ended_at=None)) is None


def test_a_call_still_going_says_so():
    """§3: «in corso» è uno stato, e si vede."""
    from telephone.history import as_a_card

    from telephone.models import now_iso

    for stato in ("authorised", "dialling", "talking"):
        scheda = as_a_card(_una_chiamata(state=stato, ended_at=None,
                                          authorised_at=now_iso()))
        assert scheda["presentation_status"] == "in_corso", stato
        assert scheda["outcome_summary"] == "Chiamata in corso."

    #     V3.21.2 §13: UN SÌ DI GIORNI FA NON E' UNA TELEFONATA IN CORSO.
    vecchia = as_a_card(_una_chiamata(state="authorised", ended_at=None,
                                      started_at=None))
    assert vecchia["presentation_status"] == "non_avviata"
    assert vecchia["status_label"] == "Non avviata"
