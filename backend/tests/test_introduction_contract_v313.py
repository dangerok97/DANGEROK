"""
Chi sta chiamando, e perché.

    NON SONO FRANCESCO. SONO L'ASSISTENTE DI FRANCESCO.

Fra le due frasi non c'è una sfumatura di cortesia: c'è la differenza fra una
telefonata e un raggiro. Una voce sintetica che dice «sono Francesco Cefalà»
sta dicendo una cosa falsa a una persona che non ha modo di verificarla e che
prenderà decisioni su quella base.

Queste prove tengono ferme quattro cose:

    chi chiama lo dice, e dice per chi;
    dice perché chiama, e nient'altro;
    se lo interrompono finisce, non ricomincia;
    e quando ha finito non lo ripete più.
"""

from __future__ import annotations

import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


def _packet(**cambia):
    from telephone.mission import CallMissionPacket, MissionFact

    campi = dict(
        mission_id="mis_prova",
        mission_type="reschedule",
        goal="Spostare l'appuntamento di oggi dalle 16:00 alle 18:00",
        counterparty="Studio Dentistico Bianchi",
        on_behalf_of="Francesco Cefalà",
        local_datetime="2026-09-14T09:00:00+02:00",
        timezone="Europe/Rome",
        subject="appuntamento dal dentista di oggi",
        current_state={"when": "2026-09-14T16:00:00+02:00"},
        desired_state={"when": "2026-09-14T18:00:00+02:00"},
        known_facts=[
            MissionFact(
                field="nome_paziente", value="Francesco Cefalà",
                sensitivity="identity",
                why_it_is_here="senza il nome non trovano la prenotazione",
            ),
        ],
        allowed_on_demand_fields=["data_di_nascita"],
    )
    campi.update(cambia)
    return CallMissionPacket(**campi)


def _ledger(packet=None):
    from telephone.introduction import IntroductionLedger, introduction_for

    return IntroductionLedger(introduction_for(packet or _packet()))


# ---------------------------------------------------------------------------
# 1 · l'apertura che va bene
# ---------------------------------------------------------------------------

def test_the_backend_writes_the_opening_not_the_model():
    """
    §1: l'apertura nasce dalla missione.

        UNA FRASE INVENTATA OGNI VOLTA È UNA FRASE CHE PRIMA O POI SBAGLIA.

    Chi parla riceve `say_this_first` già scritta. Non decide come presentarsi:
    decide come dirla.
    """
    from telephone.introduction import introduction_for

    intro = introduction_for(_packet())
    assert intro.assistant_for == "Francesco Cefalà"
    detta = intro.opening_line()
    assert "sono l'assistente di Francesco Cefalà" in detta
    assert "16" in detta and "18" in detta
    assert intro.reason_keywords, "nessuna parola su cui verificare la consegna"


def test_name_and_reason_together_make_a_valid_introduction():
    """§16.1: le due cose ci sono, e l'apertura è completa."""
    reg = _ledger()
    reg.we_said(
        "Buongiorno, sono l'assistente di Francesco. Chiamo per spostare il "
        "suo appuntamento dal dentista di oggi: vorremmo spostarlo dalle 16 "
        "alle 18."
    )
    assert reg.state == "completed"
    assert reg.is_settled()
    assert not reg.pretended_to_be_them


# ---------------------------------------------------------------------------
# 2, 3, 4 · le aperture che non vanno bene
# ---------------------------------------------------------------------------

def test_the_reason_without_saying_whose_assistant_is_not_enough():
    """
    §16.2: dice perché chiama, ma non per chi.

    Dall'altra parte resta una voce che chiede di spostare l'appuntamento di
    qualcuno senza dire di chi è né chi è lei.
    """
    reg = _ledger()
    reg.we_said(
        "Buongiorno, chiamo per spostare l'appuntamento dal dentista di oggi "
        "dalle 16 alle 18."
    )
    assert reg.state == "partial"
    assert not reg.is_settled()
    assert "assistente di Francesco Cefalà" in reg.what_still_has_to_be_said()


def test_claiming_to_be_the_person_is_not_a_shorter_introduction():
    """
    §16.3: «sono Francesco Cefalà».

        QUESTA NON È UN'APERTURA INCOMPLETA. È UN'ALTRA PERSONA.

    Il nome c'è, il motivo pure — e proprio per questo la prova conta: un
    controllo che cercasse solo la presenza del nome direbbe che va tutto
    bene. Qui invece si chiede che ci sia la parola che dichiara di parlare
    **per** qualcuno, e la sua assenza accanto al nome è un allarme, non una
    mancanza.
    """
    reg = _ledger()
    reg.we_said(
        "Buongiorno, sono Francesco Cefalà. Chiamo per spostare il mio "
        "appuntamento dal dentista di oggi dalle 16 alle 18."
    )
    assert reg.pretended_to_be_them
    assert not reg.is_settled()
    assert "Non sei Francesco Cefalà" in reg.what_still_has_to_be_said()


def test_saying_who_without_saying_why_is_not_enough():
    """§16.4: si presenta e poi tace sul motivo."""
    reg = _ledger()
    reg.we_said("Buongiorno, sono l'assistente di Francesco.")
    assert reg.state == "partial"
    manca = reg.what_still_has_to_be_said()
    assert "chiami per" in manca
    assert "assistente" not in manca, "sta rifacendo il pezzo che aveva già detto"


# ---------------------------------------------------------------------------
# 5 · interrotti a metà
# ---------------------------------------------------------------------------

def test_an_interrupted_opening_is_finished_not_restarted():
    """
    §16.5 / §2: «pronto, mi dica» in mezzo alla presentazione.

        UN'APERTURA INTERROTTA NON SI RICOMINCIA: SI FINISCE.

    Ricominciare da capo è la cosa che fa sembrare una voce una registrazione.
    Completare solo il pezzo mancante, al primo momento buono, è quello che fa
    una persona.
    """
    reg = _ledger()
    reg.we_said("Buongiorno, sono l'assistente di Francesco Cefa")   # tagliata
    assert reg.state == "partial"

    nota = reg.what_still_has_to_be_said()
    assert "Non ricominciare la presentazione da capo" in nota
    assert "chiami per" in nota

    reg.we_said("Chiamo per spostare il suo appuntamento dal dentista di oggi "
                "dalle 16 alle 18.")
    assert reg.state == "completed"
    assert reg.is_settled()


# ---------------------------------------------------------------------------
# 6 · e poi non se ne parla più
# ---------------------------------------------------------------------------

def test_a_finished_introduction_is_never_asked_for_again():
    """
    §16.6: nessuno si sente ripetere chi siamo a ogni battuta.

    È la stessa ragione del gate di conferma al rovescio: lì si rallentava di
    una domanda chi voleva chiudere presto, qui non si aggiunge niente a chi
    ha già fatto le cose per bene.
    """
    reg = _ledger()
    reg.we_said(
        "Buongiorno, sono l'assistente di Francesco. Chiamo per spostare il "
        "suo appuntamento dal dentista di oggi dalle 16 alle 18."
    )
    for _ in range(5):
        assert reg.what_still_has_to_be_said() == ""
    assert reg.nudges == 0


# ---------------------------------------------------------------------------
# 7 · presentarsi non è spogliarsi
# ---------------------------------------------------------------------------

def test_the_reason_carries_nothing_it_does_not_need():
    """
    §16.7 / §4: il motivo è minimo, e si vede.

        SI DICE PERCHÉ SI CHIAMA, NON DI CHE COSA SI SOFFRE.

    «Per spostare il suo appuntamento di oggi» basta a farsi passare la
    segretaria. La data di nascita, il codice fiscale e il nome della patologia
    non servono, e chi li dice per presentarsi li ha già dati via.
    """
    from telephone.introduction import introduction_for, what_is_missing

    packet = _packet()
    assert what_is_missing(packet) == []

    motivo = introduction_for(packet).reason_summary
    for mai in ("Cefalà", "12 marzo", "1990", "codice fiscale", "CFLFNC"):
        assert mai not in motivo, f"«{mai}» detto per presentarsi"


def test_a_reason_that_leaks_a_sensitive_fact_is_reported():
    """
    §4: e se un giorno ci finisse dentro, si vede prima di comporre.

    Qui l'oggetto della missione è scritto male apposta — contiene il nome per
    esteso, che è un fatto di identità. Il controllo lo trova.
    """
    from telephone.introduction import what_is_missing

    storto = _packet(subject="appuntamento di Francesco Cefalà dal dentista")
    problemi = what_is_missing(storto)
    assert problemi, "una presentazione che dice un dato d'identità è passata"
    assert "nome_paziente" in problemi[0]


def test_the_opening_never_carries_the_phone_number():
    """§17: nemmeno per presentarsi."""
    from telephone.introduction import introduction_for

    detta = introduction_for(_packet()).opening_line()
    for cifre in ("+39", "3774714389", "339"):
        assert cifre not in detta


# ---------------------------------------------------------------------------
# E la missione porta l'apertura con sé
# ---------------------------------------------------------------------------

def test_the_packet_carries_the_contract_not_just_a_sentence():
    """
    §1: il contratto è strutturato, non è una stringa sperando bene.

    `say_this_first` resta — è quello che chi parla dice — ma accanto c'è la
    forma esplicita su cui il runtime verifica la consegna.
    """
    from telephone.introduction import introduction_for

    packet = _packet()
    packet.introduction = introduction_for(packet)
    packet.say_this_first = packet.introduction.opening_line()

    detto = packet.for_the_model()
    assert "introduction" in detto
    assert "assistant_for" in detto
    assert "Francesco Cefalà" in detto
    assert packet.say_this_first.startswith("Buongiorno, sono l'assistente di")


# ---------------------------------------------------------------------------
# L'apertura nasce dal mandato che la persona ha scritto
# ---------------------------------------------------------------------------

def _from_a_mandate(why: str):
    from telephone.dossier import TelephoneCallDossier
    from telephone.mission import packet_for
    from telephone.models import Mandate, PhoneCall

    call = PhoneCall(
        owner_id="u1", to_number="+393774714389", session_ref="s1",
        calling_whom="Studio Dentistico Bianchi",
        mandate=Mandate(
            why_calling=why, may_agree_to=["confermare"],
            must_bring_back=["l'esito"],
        ),
    )
    dossier = TelephoneCallDossier(
        owner_id="u1", call_id=call.id, on_behalf_of="Francesco Cefalà",
    )
    return packet_for(
        call, dossier,
        current_when="2026-09-14T16:00:00+02:00",
        desired_when="2026-09-14T18:00:00+02:00",
    )


def test_a_mandate_becomes_a_sentence_a_person_would_say():
    """
    §0: quattro mandati veri, quattro aperture che stanno in piedi.

        IL MANDATO È UNA RICHIESTA. L'APERTURA È UNA FRASE.

    Ognuna di queste è uscita storta almeno una volta, e ognuna per un motivo
    diverso: un verbo raddoppiato, un possessivo di prima persona rimasto
    dentro, un articolo mangiato a metà, un genere sbagliato, una missione
    classificata su una sillaba trovata in mezzo a una parola.
    """
    casi = [
        ("spostare il mio appuntamento dal dentista di oggi alle 16 alle 18",
         "reschedule",
         "Chiamo per spostare il suo appuntamento dal dentista di oggi, "
         "dalle 16 alle 18."),
        ("prenotare una revisione per la macchina",
         "book",
         "Chiamo per prenotare la sua revisione per la macchina."),
        ("confermare la prenotazione del ristorante di sabato",
         "confirm",
         "Chiamo per confermare la sua prenotazione del ristorante di sabato."),
        ("sapere se il pacco è arrivato",
         "ask",
         "Chiamo per sapere se il pacco è arrivato."),
    ]
    for mandato, tipo, coda in casi:
        packet = _from_a_mandate(mandato)
        assert packet.mission_type == tipo, mandato
        assert packet.say_this_first == (
            f"Buongiorno, sono l'assistente di Francesco Cefalà. {coda}"
        ), packet.say_this_first


def test_a_mission_built_from_a_real_call_never_carries_the_number():
    """§17: il numero è a un attributo di distanza, e resta fuori lo stesso."""
    packet = _from_a_mandate("spostare il mio appuntamento di oggi")
    detto = packet.for_the_model()
    for cifre in ("+39", "3774714389", "393774"):
        assert cifre not in detto, cifre


def test_an_opening_delivered_in_fragments_still_counts_as_delivered():
    """
    §3: la trascrizione di uscita arriva a pezzi, e l'apertura è una sola.

        UNA FRASE NON ARRIVA IN UNA VOLTA SOLA.

    Al primo giro contro Gemini Live vero l'apertura risultava `not_started`
    mentre era stata detta per intera: passavo al registro ogni frammento da
    solo, e nessun frammento contiene né il nome intero né metà delle parole
    del motivo. Due spinte inutili a una voce che aveva già fatto il suo
    lavoro.
    """
    reg = _ledger()
    for pezzo in ["Buongiorno, so", "no l'assi", "stente di Fran", "cesco",
                  " Cefalà. Chiamo per spo", "stare il suo appunt",
                  "amento dal dentista di oggi, dalle 16 alle 18."]:
        reg.we_said(pezzo)
    assert reg.state == "completed", "ricomposta male: l'apertura risulta mai detta"
    assert reg.what_still_has_to_be_said() == ""
    assert reg.nudges == 0


def test_pretending_to_be_them_is_caught_across_fragments_too():
    """E il controllo che conta di più non si perde nella ricomposizione."""
    reg = _ledger()
    for pezzo in ["Buongiorno, so", "no Fran", "cesco Cefalà. Chiamo per ",
                  "spostare il mio appuntamento dal dentista di oggi."]:
        reg.we_said(pezzo)
    assert reg.pretended_to_be_them
    assert not reg.is_settled()
