"""
Quello che ORA ha visto, e cosa può diventare.

    UNA FOTO È EVIDENZA, NON CONOSCENZA.
    «HO VISTO» != «SO».

Un'osservazione visiva è una cosa che ORA può dire di aver visto, in un
momento preciso, dentro un'immagine che una persona le ha mostrato. Non è un
fatto della sua vita: è una lettura, con un grado di leggibilità, delle
incertezze dichiarate e una provenienza che sopravvive all'immagine.

La riga che conta è quella che *non* c'è: da qui non parte nessuna strada
verso la memoria canonica. Un'osservazione può diventare conoscenza soltanto
attraverso la governance che governa tutto il resto — la stessa porta, gli
stessi controlli, la stessa possibilità per la persona di dire di no. Una
scorciatoia «l'ho visto quindi lo so» sarebbe comoda da scrivere e sarebbe il
modo più veloce di riempire la vita di qualcuno di cose che non ha mai detto.

E c'è una seconda cosa che questo file possiede: l'identità. La stessa
immagine caricata due volte è la stessa immagine, e deve produrre una
osservazione sola. L'identità è l'impronta dei byte — un fatto tecnico — e
non il significato, che non è affare del codice.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

# Quanto ORA riesce a leggere di quello che ha davanti. Non è una misura di
# qualità dell'immagine: è una dichiarazione su quanto ci si può fidare di
# quello che segue.
Readability = Literal["readable", "partially_readable", "unreadable", "ambiguous"]

Confidence = Literal["weak", "reasonable", "strong"]

# Quanto regge un legame fra quello che si è visto e una parte di vita.
#
#     STESSA CONTROPARTE NON È LO STESSO EVENTO.
#     STESSO DOMINIO NON È LA STESSA SITUAZIONE.
#     RELAZIONE PLAUSIBILE NON È RELAZIONE VERIFICATA.
#
# Non è una tassonomia da mostrare a qualcuno: è il livello delle prove, che
# deve viaggiare accanto alla conclusione perché chi la scrive in italiano
# sappia con che forza può dirla. Senza questo, un bonifico dell'11 settembre
# e un appuntamento del 17 presso lo stesso studio «coincidono temporalmente»
# — una frase certa costruita su una coincidenza di nome.
LinkStrength = Literal[
    # C'è scritto nell'immagine, e nella riga che ORA già teneva: lo stesso
    # identificativo, lo stesso importo alla stessa data. Non serve dedurre.
    "observed",
    # Più elementi indipendenti puntano nella stessa direzione, e niente la
    # contraddice. Si può dire, dicendo su cosa si regge.
    "supported",
    # Sta in piedi, ma potrebbe essere un'altra cosa che le somiglia: stessa
    # controparte, stesso dominio, stesso ordine di grandezza. Si propone, non
    # si afferma.
    "plausible",
    # Non c'è niente che lo regga. Si dice che non si sa.
    "unknown",
]

# Cosa ne è stato di un'osservazione. `seen` è dove nascono tutte; le altre
# due sono decisioni prese altrove, e nessuna di esse è «diventata vera».
Standing = Literal[
    # L'ho vista, e resta un'osservazione.
    "seen",
    # È stata proposta alla governance come conoscenza da confermare.
    "proposed",
    # Serviva solo a rispondere in quel momento, e non la si tiene.
    "transient",
]

MAX_ITEMS = 12
MAX_TEXT = 1200


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_observation_id() -> str:
    return f"vis_{uuid.uuid4().hex[:14]}"


def fingerprint(image: bytes) -> str:
    """
    L'identità di un'immagine: i suoi byte.

    Non il nome del file, che cambia a ogni schermata catturata, e non quello
    che ci si vede dentro, che è un giudizio. Due caricamenti della stessa
    immagine sono la stessa immagine, e devono produrre una osservazione sola.
    """
    return hashlib.sha256(image or b"").hexdigest()[:32]


class LifeTie(BaseModel):
    """
    Una parte di vita a cui questa immagine potrebbe appartenere, e perché.

        STESSO ARGOMENTO NON VUOL DIRE STESSA SITUAZIONE.

    `ties_it_here` è obbligatorio e non è decorazione: è la frase che dice
    cosa lega questa immagine a *quella* parte di vita e non a un'altra che le
    somiglia. Un preventivo di mutuo può riguardare l'acquisto di una casa;
    la foto di una casa qualunque no, e la differenza sta tutta in quella
    frase — che se non si riesce a scrivere, la relazione non si stabilisce.
    """

    ref: str = Field(min_length=1, max_length=64)
    ties_it_here: str = Field(min_length=1, max_length=300)
    # Con quanta forza. Il valore prudente è quello di partenza: un legame che
    # arriva senza dire quanto regge regge poco, e va proposto — non affermato.
    how_strong: LinkStrength = "plausible"
    # E cosa manca perché regga di più: la frase che permette a chi risponde
    # di dire «non ho una prova che *questo* bonifico sia *quell*'appuntamento»
    # invece di tacere sul punto o di superarlo.
    what_would_settle_it: str = Field(default="", max_length=300)

    def what_it_licenses(self) -> Dict[str, str]:
        """
        La frase più forte che questo legame consente, e quella che nega.

            NON IL LIVELLO: LA FRASE.

        Finora di ogni legame usciva `how_strong`, e accanto un paragrafo che
        spiegava come tradurlo. Tradurre è un passaggio, e un passaggio si
        salta: alla domanda «questo riguarda la casa?» il livello diceva
        `plausible` e la risposta diceva «è collegato all'appuntamento del 17
        settembre». Fra il livello e la frase c'era un margine, ed è lì che
        finiva la prudenza.

        Quindi il margine si toglie. Esce la frase, già fatta, con accanto
        quella che non si può dire — e la seconda vale per ogni livello, anche
        per il più alto, perché è una cosa che questo tipo di dato non può
        sapere: `ref` indica una **parte di vita**, non un evento. Nessun
        legame, per quanto solido, identifica un appuntamento preciso. Dire
        «è lo stesso evento» richiede una prova di identità, e una prova di
        identità qui non c'è mai — non perché manchi, ma perché non è questo
        il campo che la porterebbe.
        """
        may = {
            # Il documento stesso e quello che ORA già teneva dicono la stessa
            # cosa: si afferma.
            "observed": (
                "Puoi dirlo come un fatto: questo riguarda quella parte della "
                "sua vita."
            ),
            # Più elementi indipendenti, niente contro: si dice, dicendo su
            # cosa si regge.
            "supported": (
                "Puoi dirlo, dicendo su cosa si regge: «questo riguarda …, "
                "perché …». Non presentarlo come verificato."
            ),
            # Reggerebbe anche per una cosa che gli somiglia: si propone.
            "plausible": (
                "Proponilo, non affermarlo: «rende probabile che riguardi …», "
                "«potrebbe riguardare …». Non «è», non «riguarda "
                "direttamente», non «corrisponde». E di' che cosa servirebbe "
                "per esserne certi."
            ),
            "unknown": "Di' che non lo sai.",
        }
        return {
            "you_may_say": may.get(self.how_strong, may["plausible"]),
            "you_may_never_say": (
                "Che questo è lo stesso evento di un impegno che la persona "
                "ha in calendario. Questo legame porta a una parte della sua "
                "vita, non a un appuntamento: non contiene nessuna prova di "
                "identità con un evento preciso, e nessun livello di forza "
                "gliene dà una. Un pagamento e un appuntamento restano due "
                "cose diverse anche con la stessa controparte e la stessa "
                "pratica."
            ),
        }


class VisualObservation(BaseModel):
    """Quello che ORA ha visto in un'immagine, con tutto quello che non sa."""

    id: str = Field(default_factory=new_observation_id)
    owner_id: str

    # --- da dove viene ---------------------------------------------------
    source_ref: str = Field(default="", max_length=64)
    document_ref: str = Field(default="", max_length=64)
    session_ref: str = Field(default="", max_length=64)
    mime_type: str = Field(default="", max_length=80)
    # L'impronta dei byte: la stessa immagine due volte è la stessa immagine.
    content_fingerprint: str = Field(default="", max_length=64)
    uploaded_at: str = Field(default_factory=now_iso)
    observed_at: str = Field(default_factory=now_iso)

    # --- cosa si vede ----------------------------------------------------
    what_i_see: str = Field(default="", max_length=400)
    readability: Readability = "readable"
    observed_text: str = Field(default="", max_length=MAX_TEXT)
    what_i_could_not_read: str = Field(default="", max_length=400)
    observed_entities: List[str] = Field(default_factory=list, max_length=MAX_ITEMS)
    observed_numbers: List[str] = Field(default_factory=list, max_length=MAX_ITEMS)
    observed_dates: List[str] = Field(default_factory=list, max_length=MAX_ITEMS)
    observed_amounts: List[str] = Field(default_factory=list, max_length=MAX_ITEMS)

    # --- cosa se ne capisce ----------------------------------------------
    interpretation: str = Field(default="", max_length=600)
    uncertainty: str = Field(default="", max_length=400)
    confidence: Confidence = "reasonable"
    about_life: List[LifeTie] = Field(default_factory=list, max_length=6)

    # --- cosa ne è stato --------------------------------------------------
    standing: Standing = "seen"
    worth_keeping: bool = False
    why_keep: str = Field(default="", max_length=300)

    def how_ora_knows(self) -> str:
        """
        «Come lo sai?», con una risposta che una persona può leggere.

        E che resta vera anche dopo: se l'immagine non c'è più, questa frase
        continua a raccontare com'è andata senza far finta di poterla
        riaprire. Una provenienza che promette di poter rileggere una cosa
        cancellata è una bugia con una data sopra.
        """
        when = self.observed_at[:10]
        return f"L'ho visto in un'immagine che mi hai mostrato il {when}."

    def for_ai(self) -> Dict[str, Any]:
        """Quello che il ragionamento riceve, senza i byte e senza gli id."""
        return {
            "what_i_see": self.what_i_see,
            "how_well_i_could_read_it": self.readability,
            "text_i_read": self.observed_text[:600],
            "what_i_could_not_read": self.what_i_could_not_read or None,
            "entities": self.observed_entities,
            "numbers": self.observed_numbers,
            "dates": self.observed_dates,
            "amounts": self.observed_amounts,
            "what_it_seems_to_mean": self.interpretation or None,
            "what_i_am_unsure_about": self.uncertainty or None,
            "parts_of_life_it_belongs_to": [
                {
                    "ref": t.ref,
                    "why": t.ties_it_here,
                    # Quanto regge, e cosa lo renderebbe piu' saldo.
                    "how_strong": t.how_strong,
                    "what_would_settle_it": t.what_would_settle_it or None,
                    # E la frase che quel livello consente, gia' fatta, con
                    # accanto quella che nega: fra il livello e la frase c'era
                    # un passaggio, e il passaggio si saltava.
                    **t.what_it_licenses(),
                }
                for t in self.about_life
            ],
            "how_i_know": self.how_ora_knows(),
        }

    def for_human(self) -> Dict[str, Any]:
        """Quello che una persona legge. Nessun id, nessun percorso, nessun byte."""
        return {
            "cosa_vedo": self.what_i_see,
            "quanto_riesco_a_leggere": {
                "readable": "si legge bene",
                "partially_readable": "si legge in parte",
                "unreadable": "non riesco a leggerlo",
                "ambiguous": "non è chiaro",
            }[self.readability],
            "non_sono_riuscito_a_leggere": self.what_i_could_not_read or None,
            "cosa_sembra": self.interpretation or None,
            "cosa_non_so": self.uncertainty or None,
            "come_lo_so": self.how_ora_knows(),
        }
