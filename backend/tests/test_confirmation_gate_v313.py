"""
Una porta aperta non è una porta attraversata.

    «ALLE 18 ABBIAMO POSTO» NON È «L'HO SPOSTATO ALLE 18».

Nel PoC l'esecutore chiudeva la missione sulla prima delle due. Aveva capito
bene — c'era posto — ma nessuno aveva ancora spostato niente, e Francesco si
sarebbe presentato alle diciotto davanti a una porta chiusa, con in mano la
certezza che qualcuno gliel'aveva confermato.

La tentazione era scriverlo nel prompt: «non dire di aver concluso finché non
te lo confermano». C'era già scritto. Un prompt è una raccomandazione, e regge
finché il modello ha voglia di darle retta.

    UNA CONDIZIONE NON SI RACCOMANDA. SI VERIFICA.

Queste prove verificano il registro: chi decide da che punto della trattativa
siamo non è chi sta parlando.
"""

from __future__ import annotations

import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


def _registro():
    from telephone.mission import MissionLedger

    return MissionLedger()


CAMBIAMENTI = {"appointment_date": "2026-09-14", "new_time": "18:00"}


# ---------------------------------------------------------------------------
# A · disponibilità non basta
# ---------------------------------------------------------------------------

def test_availability_alone_does_not_close_the_mission():
    """
    §A: «alle 18 abbiamo posto», e la voce prova a chiudere.

    È il difetto osservato negli scenari 1 e 5 del PoC, riprodotto qui senza
    telefono: il registro lo rifiuta prima che tocchi qualunque cosa.
    """
    reg = _registro()
    reg.a_new_turn_begins()                       # «Studio Bianchi, buongiorno»
    reg.a_new_turn_begins()                       # «mi dica il nome»
    reg.a_new_turn_begins()
    reg.heard("availability", "alle 18 di oggi c'è posto")

    assert reg.progress == "available"
    # Il motivo adesso e piu preciso: non «confermami», ma «chiediglielo».
    # Chiedere conferma di una cosa che nessuno ha ancora fatto e il modo piu
    # veloce di farsi dire di si a vuoto.
    assert reg.why_not_complete(CAMBIAMENTI) == "change_not_requested_yet"


def test_the_refusal_tells_the_model_what_to_do_and_the_mouth_what_to_say():
    """
    §2: una risposta utile, non tecnica.

    Due registri separati apposta. `instruction` è per chi ragiona e può
    nominare gli strumenti; `say` è per la bocca, e la bocca non nomina mai
    sistemi — dall'altra parte c'è una segretaria, non un collega.
    """
    from telephone.mission import REFUSALS

    for motivo in ("missing_changes", "confirmation_required",
                   "change_not_requested_yet"):
        rifiuto = REFUSALS[motivo]
        assert rifiuto["instruction"].strip()
        assert rifiuto["say"].strip()
        detto = rifiuto["say"].lower()
        for tecnicismo in ("tool", "strumento", "backend", "json", "api",
                           "confirmed_changes", "missione", "sistema"):
            assert tecnicismo not in detto, f"«{tecnicismo}» detto ad alta voce"


# ---------------------------------------------------------------------------
# B · disponibilità, accettazione, conferma
# ---------------------------------------------------------------------------

def test_a_confirmation_in_a_later_turn_closes_the_mission():
    """
    §B: la trattativa completa, e si chiude.

    Fra la disponibilità e la conferma la controparte ha riaperto bocca: vuol
    dire che in mezzo ci è finita la domanda che mancava.
    """
    reg = _registro()
    reg.a_new_turn_begins()
    reg.a_new_turn_begins()
    reg.a_new_turn_begins()
    reg.heard("availability", "alle 18 c'è posto")
    assert reg.progress == "available"

    reg.a_new_turn_begins()                       # «va bene, l'ho spostato»
    assert reg.progress == "accepted_by_agent"
    reg.heard("confirmation", "appuntamento spostato alle 18:00")

    assert reg.progress == "confirmed_by_counterparty"
    assert reg.why_not_complete(CAMBIAMENTI) == ""


def test_a_confirmation_in_the_same_breath_as_the_availability_does_not_count():
    """
    §B, al rovescio: il passaggio che conta è il turno, non l'etichetta.

        UNA PORTA APERTA E ATTRAVERSATA NELLA STESSA FRASE È UNA PORTA APERTA.

    Se la voce etichetta come conferma la stessa battuta in cui le hanno detto
    che ci sarebbe posto, il registro non gliela conta. Il tipo lo dichiara
    chi parla, e chi parla può sbagliarsi in buona fede; che la controparte
    abbia riaperto bocca invece è un fatto.
    """
    reg = _registro()
    reg.a_new_turn_begins()
    reg.heard("availability", "alle 18 c'è posto")
    reg.heard("confirmation", "alle 18 c'è posto")   # la stessa battuta

    assert reg.progress == "available"
    assert reg.why_not_complete(CAMBIAMENTI) == "change_not_requested_yet"


# ---------------------------------------------------------------------------
# C · una proposta è una proposta
# ---------------------------------------------------------------------------

def test_a_proposal_is_not_a_confirmation():
    """§C: «potremmo fare le 18» — potremmo."""
    reg = _registro()
    reg.a_new_turn_begins()
    reg.heard("proposal", "potremmo fare le 18")

    assert reg.progress == "proposed"
    assert reg.why_not_complete(CAMBIAMENTI) == "change_not_requested_yet"


# ---------------------------------------------------------------------------
# D · una conferma piena si chiude subito
# ---------------------------------------------------------------------------

def test_even_a_plain_confirmation_is_checked_once():
    """
    §4.D: «l'ho già spostato alle 18», come prima risposta.

        SI PREFERISCE UNA DOMANDA IN PIÙ A UN FALSO SUCCESSO.

    Questa prova prima diceva l'opposto — che una conferma piena chiude
    subito — ed era esattamente il buco che la sesta telefonata vera ha
    imboccato: Gemini ha etichettato «alle 18 abbiamo disponibilità» come
    conferma, non aveva registrato nient'altro, e il registro l'ha fatta
    passare. Missione compiuta su una porta solo aperta.

    Adesso la prima cosa che ci dicono non chiude niente, chiunque scelga
    l'etichetta. Si chiede, rispondono, e allora sì.
    """
    reg = _registro()
    reg.a_new_turn_begins()
    reg.heard("confirmation", "l'ho già spostato alle 18:00")
    assert reg.why_not_complete(CAMBIAMENTI) == "change_not_requested_yet"

    # ORA chiede: «mi conferma che risulta registrato?». Loro riparlano.
    reg.a_new_turn_begins()
    assert reg.why_not_complete(CAMBIAMENTI, "sì, confermo") == ""


def test_a_question_only_mission_does_not_need_the_second_round():
    """
    §2: il giro in più vale per le missioni che cambiano qualcosa.

    Chiedere se il pacco è arrivato non ha un «prima» e un «dopo»: la prima
    risposta è già l'esito, e pretendere una conferma di una risposta sarebbe
    solo una telefonata più lunga.
    """
    from telephone.mission import MissionLedger

    reg = MissionLedger("ask")
    reg.a_new_turn_begins()
    assert reg.why_not_complete({"stato": "consegnato"}, "sì, è arrivato") == ""


# ---------------------------------------------------------------------------
# E · nel dubbio non si chiude
# ---------------------------------------------------------------------------

def test_an_ambiguous_sentence_read_as_availability_does_not_close():
    """
    §E: «alle 18 va bene» — e non si capisce se l'hanno fatto o se si potrebbe.

    Il contratto dell'enum dice: nel dubbio, `availability`. È la lettura che
    costa meno se è sbagliata — al massimo si fa una domanda in più, invece di
    mandare qualcuno davanti a una porta chiusa.
    """
    reg = _registro()
    reg.a_new_turn_begins()
    reg.a_new_turn_begins()
    reg.a_new_turn_begins()
    reg.heard("availability", "alle 18 va bene")

    assert reg.why_not_complete(CAMBIAMENTI) == "change_not_requested_yet"


def test_the_enum_says_out_loud_which_reading_is_the_cheap_one():
    """
    §E: e la regola sta scritta dove il modello la legge, non solo qui.

    Se il tipo giusto nel dubbio non è dichiarato nello schema dello
    strumento, questa prova sta verificando una convenzione che nessuno ha
    mai comunicato a chi deve rispettarla.

        E SI GUARDA LO SCHEMA CHE PARTE DAVVERO.

    Prima questa prova leggeva il banco del PoC, che viveva fuori dal repo su
    una macchina sola: si saltava ovunque tranne che lì, e teneva ferma una
    copia che nessuna telefonata usa più. `THE_SIX` è l'elenco che il runtime
    manda a Gemini a ogni chiamata vera — se la regola non è scritta lì, non è
    scritta da nessuna parte.
    """
    import json

    from telephone.live import THE_SIX

    schemi = {
        f["name"]: f for f in THE_SIX[0]["function_declarations"]
    }
    kind = schemi["record_call_fact"]["parameters"]["properties"]["kind"]
    assert set(kind["enum"]) == {
        "availability", "proposal", "confirmation", "refusal", "detail",
    }
    assert "dubbio" in json.dumps(kind, ensure_ascii=False).lower()


# ---------------------------------------------------------------------------
# F · si può riprovare, e la seconda volta passa
# ---------------------------------------------------------------------------

def test_a_premature_close_can_be_retried_once_the_confirmation_arrives():
    """
    §F: rifiutare non è chiudere la porta.

    La voce prova troppo presto, riceve un motivo e una frase da dire, chiede,
    ottiene, riprova. È esattamente il giro che vogliamo: il gate non fa
    fallire la missione, la rallenta di una domanda.
    """
    reg = _registro()
    reg.a_new_turn_begins()
    reg.heard("availability", "alle 18 c'è posto")
    assert reg.why_not_complete(CAMBIAMENTI) == "change_not_requested_yet"

    reg.a_new_turn_begins()
    reg.heard("confirmation", "sì, risulta spostato alle 18")
    assert reg.why_not_complete(CAMBIAMENTI) == ""

    reg.completed()
    assert reg.progress == "completed"


# ---------------------------------------------------------------------------
# G · e un successo senza oggetto resta un non-successo
# ---------------------------------------------------------------------------

def test_a_success_with_nothing_in_it_is_still_refused():
    """
    §G: quello che c'era prima non si è rotto.

    E si controlla per primo: se non c'è scritto **che cosa**, non serve
    nemmeno chiedersi se qualcuno l'ha detto.
    """
    reg = _registro()
    reg.a_new_turn_begins()
    reg.heard("availability", "alle 18 c'è posto")
    reg.a_new_turn_begins()
    reg.heard("confirmation", "spostato")

    assert reg.why_not_complete({}) == "missing_changes"
    assert reg.why_not_complete(None) == "missing_changes"
    assert reg.why_not_complete(CAMBIAMENTI) == ""


# ---------------------------------------------------------------------------
# E il gate non si lascia aggirare
# ---------------------------------------------------------------------------

def test_a_refusal_never_opens_the_door():
    """Un «no» non è un passaggio verso il sì."""
    reg = _registro()
    reg.a_new_turn_begins()
    reg.heard("refusal", "oggi dopo le 18 siamo al completo")
    reg.a_new_turn_begins()
    reg.heard("detail", "il dottore esce alle 19")

    assert reg.progress == "opening"
    # Qui hanno parlato in due turni: il problema non è che non abbiamo
    # chiesto, è che nessuno ha confermato. I due rifiuti dicono cose diverse
    # apposta, e alla bocca fanno dire frasi diverse.
    assert reg.why_not_complete(CAMBIAMENTI) == "confirmation_required"


def test_the_gate_costs_nothing_when_the_call_went_properly():
    """
    Il gate non aggiunge un turno a chi ha fatto le cose per bene.

    Se la conferma c'è ed è al posto giusto, `why_not_complete` è vuoto al
    primo tentativo: nessuna domanda in più, nessun secondo giro.
    """
    reg = _registro()
    for _ in range(3):
        reg.a_new_turn_begins()
    reg.heard("availability", "alle 18 c'è posto")
    reg.a_new_turn_begins()
    reg.heard("confirmation", "fatto, spostato alle 18")

    assert reg.why_not_complete(CAMBIAMENTI) == ""


# ---------------------------------------------------------------------------
# La prova viaggia con la richiesta
# ---------------------------------------------------------------------------

def test_the_confirmation_can_travel_with_the_close():
    """
    §B, come succede davvero al telefono.

    Alla prima prova con il gate acceso lo studio aveva confermato per intero
    — «è fatto, l'ho spostato alle diciotto» — e la chiusura è stata respinta
    lo stesso, perché la voce era andata dritta a chiudere senza annotare
    quella frase. Chiedere due gesti in fila quando ne basta uno è un modo
    elegante di costruirsi un loop.
    """
    reg = _registro()
    reg.a_new_turn_begins()
    reg.a_new_turn_begins()
    reg.a_new_turn_begins()
    reg.heard("availability", "alle 18 c'è posto")

    reg.a_new_turn_begins()
    assert reg.why_not_complete(
        CAMBIAMENTI, "è fatto, ho spostato l'appuntamento alle 18",
    ) == ""


def test_a_confirmation_carried_in_the_same_breath_still_does_not_count():
    """
    E il turno resta l'autorità, chiunque dichiari la conferma.

        LA PROVA LA PORTA CHI PARLA. IL PESO GLIELO DÀ CHI ASCOLTA.

    Qui la voce allega una frase di conferma nello stesso respiro in cui le
    hanno detto che ci sarebbe posto: è precisamente il difetto osservato
    negli scenari 1 e 5, e passare la prova a mano non lo salva.
    """
    reg = _registro()
    reg.a_new_turn_begins()
    reg.a_new_turn_begins()
    reg.a_new_turn_begins()
    reg.heard("availability", "alle 18 di oggi c'è posto")

    assert reg.why_not_complete(
        CAMBIAMENTI, "alle 18 di oggi c'è posto",
    ) == "change_not_requested_yet"


def test_an_empty_close_is_refused_before_the_confirmation_is_even_weighed():
    """§G: si guarda prima se c'è scritto che cosa, e non si annota nulla."""
    reg = _registro()
    reg.a_new_turn_begins()
    assert reg.why_not_complete({}, "l'ho spostato alle 18") == "missing_changes"
    assert reg.statements == [], "ha annotato una conferma su una chiusura vuota"
