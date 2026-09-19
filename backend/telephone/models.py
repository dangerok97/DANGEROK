"""
Una telefonata, e cosa ORA può dire dentro.

    UNA CHIAMATA È UN'AZIONE CHE RAGGIUNGE UNA PERSONA.
    QUELLO CHE SI DICE A UN ESTRANEO NON SI PUÒ RITIRARE.

Questo file non fa telefonare nessuno. Tiene due cose: cos'è una chiamata
mentre succede, e — la parte che conta — il *mandato*: l'elenco esplicito di
ciò che ORA può accettare a nome di qualcuno mentre è in linea.

Il mandato esiste perché durante una telefonata non c'è tempo di chiedere.
In chat, davanti a una decisione fuori portata, ORA si ferma e domanda; al
telefono dall'altra parte c'è una persona che aspetta una risposta adesso, e
«ci devo pensare» detto male diventa un sì. Quindi quello che si può accettare
si decide *prima* di comporre il numero, lo decide l'autorità che governa
tutto il resto, e in linea non si allarga mai — nemmeno se l'interlocutore
insiste, nemmeno se sembra ragionevole, nemmeno se è gratis.

L'altra riga che conta è l'esito. Una telefonata non lascia una traccia
utilizzabile se resta una registrazione o un muro di parole: lascia un fatto,
oppure lascia il fatto che non si è capito. `CallOutcome` ha posto per
entrambi, e `understood` è un campo vero — una chiamata finita senza aver
capito è un esito legittimo, e dirlo è meglio che inventare un orario.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

# Dove si trova una chiamata adesso. Nessuno di questi stati è «riuscita»:
# quella è una lettura dell'esito, e la fa chi legge.
CallState = Literal[
    "authorised",   # si può fare, non è ancora partita
    "dialling",     # il numero sta squillando
    "talking",      # qualcuno ha risposto e si sta parlando
    "ended",        # la linea è chiusa, comunque sia andata
    "failed",       # non è mai arrivata a parlare con nessuno
]

# Come è finita, secondo la rete e non secondo noi.
HowItEnded = Literal[
    "we_hung_up", "they_hung_up", "no_answer", "busy", "failed", "unknown",
]

MAX_TURNS = 120
MAX_TEXT = 2000


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_call_id() -> str:
    return f"tel_{uuid.uuid4().hex[:14]}"


class Mandate(BaseModel):
    """
    Che cosa ORA può accettare, in linea, a nome di questa persona.

        NIENTE CHE NON SIA SCRITTO QUI.

    Non è un suggerimento al modello: è l'elenco chiuso delle cose che possono
    uscire dalla bocca di ORA come un impegno. Tutto il resto — un preventivo
    più alto, una data diversa da quelle permesse, un'altra prestazione, un
    pagamento, qualunque cosa — si riporta a chi ha chiesto la chiamata, e in
    linea si dice che si deve chiedere. Dire «devo chiedere a Francesco» non è
    una figura goffa: è l'unica frase onesta quando l'autorità non c'è.
    """

    # Perché si sta chiamando, in una riga, con le parole di chi ha chiesto.
    why_calling: str = Field(min_length=1, max_length=300)
    # Le cose che ORA può accettare senza richiamare nessuno. Vuoto è un
    # mandato valido: vuol dire che questa chiamata serve solo a chiedere.
    may_agree_to: List[str] = Field(default_factory=list, max_length=8)
    # E quelle che, se vengono proposte, si riportano indietro. Elencarle
    # serve a riconoscerle, non a vietarle una per una: quello che non sta in
    # `may_agree_to` è già vietato.
    must_bring_back: List[str] = Field(default_factory=list, max_length=8)
    # Quanto può durare, in minuti. Una chiamata che non finisce è una
    # chiamata che costa e che nessuno sta guardando.
    minutes: int = Field(default=5, ge=1, le=15)
    #     UN MESSAGGIO DA CONSEGNARE, CON LE PAROLE DI CHI LO MANDA.
    #
    # Quando c'è, la telefonata non negozia e non cambia niente nel mondo: porta
    # una frase a una persona. Si tiene com'è stata detta — «la amo», «arrivo
    # venti minuti in ritardo» — perché è la versione che fa fede: chi parla può
    # renderla naturale, non cambiarne il significato.
    message: str = Field(default="", max_length=400)
    # A chi va detta, e solo a lei. Se risponde qualcun altro, non la sente.
    recipient: str = Field(default="", max_length=120)

    def allows(self, thing: str) -> bool:
        """Se questa cosa sta nel mandato. Confronto esatto, non somiglianza."""
        wanted = (thing or "").strip().lower()
        return bool(wanted) and any(
            wanted == item.strip().lower() for item in self.may_agree_to
        )


class CallTurn(BaseModel):
    """Una battuta, di chi l'ha detta, quando."""

    who: Literal["ora", "them"]
    said: str = Field(default="", max_length=MAX_TEXT)
    at: str = Field(default_factory=now_iso)


class CallOutcome(BaseModel):
    """
    Che cosa è successo, in una forma utilizzabile.

        NON AVER CAPITO È UN ESITO.

    Il campo che tiene in piedi tutto il resto è `understood`. Una telefonata
    in cui l'interlocutore ha detto tre cose contraddittorie e poi ha
    riagganciato è finita, ma non ha prodotto niente da scrivere in un
    calendario — e la tentazione di riempire i campi comunque, con l'orario
    più probabile, è esattamente il modo in cui una persona si presenta il
    giorno sbagliato.
    """

    understood: bool = False
    # Cosa si è capito, in italiano, come lo direbbe una persona.
    in_a_line: str = Field(default="", max_length=400)
    # I fatti, se ce ne sono. Nessuno di questi è obbligatorio.
    when: Optional[str] = None           # ISO, se è stata detta una data e un'ora
    where: Optional[str] = None
    with_whom: Optional[str] = None
    how_much: Optional[str] = None
    # Cosa è rimasto aperto, e cosa ORA ha dovuto riportare indietro.
    still_open: List[str] = Field(default_factory=list, max_length=6)
    brought_back: List[str] = Field(default_factory=list, max_length=6)
    # Quello che ORA ha accettato in linea, se ha accettato qualcosa. Serve a
    # poterlo confrontare con il mandato dopo, non solo prima.
    agreed_to: List[str] = Field(default_factory=list, max_length=6)
    #     SE UNA COSA CONCRETA STIA DENTRO UN PERMESSO ASTRATTO È UN GIUDIZIO.
    #
    # Il mandato dice «un appuntamento fra giovedì e sabato, in orario di
    # studio»; quello che ORA ha accettato è «venerdì diciotto alle dieci».
    # Sono la stessa cosa, e due stringhe diverse. Il primo controllo qui
    # confrontava testo, e ha segnalato come violazione un appuntamento
    # perfettamente dentro il mandato — un falso allarme su un controllo di
    # sicurezza è peggio di nessun controllo, perché insegna a ignorarlo.
    # Quindi il confronto lo fa chi rilegge la telefonata, che ha in mano
    # tutte e due le cose, e qui resta scritto solo il risultato.
    outside_the_mandate: List[str] = Field(default_factory=list, max_length=6)
    # E cosa non si è capito, detto per nome.
    unclear: str = Field(default="", max_length=400)

    def worth_writing_down(self) -> bool:
        """
        Se da qui può nascere qualcosa nel calendario.

        Due condizioni, e servono entrambe: aver capito, e avere un momento.
        Un esito capito ma senza orario è una cosa da dire alla persona, non
        da scrivere in agenda.
        """
        return bool(self.understood and self.when)


class PhoneCall(BaseModel):
    """Una telefonata, dal momento in cui è autorizzata a quando è raccontata."""

    id: str = Field(default_factory=new_call_id)
    owner_id: str

    # --- chi, e perché ----------------------------------------------------
    to_number: str = Field(default="", max_length=32)
    # Come si chiama il posto che si sta chiamando, per poterlo dire a voce.
    calling_whom: str = Field(default="", max_length=120)
    mandate: Mandate

    # --- l'autorità che l'ha resa possibile -------------------------------
    #
    # Non un booleano. Il riferimento alla decisione presa altrove, così che
    # dopo si possa risalire a *quale* autorizzazione ha aperto questa linea.
    authority_ref: str = Field(default="", max_length=64)
    authorised_at: str = Field(default_factory=now_iso)

    # --- mentre succede ---------------------------------------------------
    state: CallState = "authorised"
    provider_ref: str = Field(default="", max_length=64)   # l'id della chiamata dal carrier
    session_ref: str = Field(default="", max_length=64)    # la conversazione da cui nasce
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    how_it_ended: HowItEnded = "unknown"
    turns: List[CallTurn] = Field(default_factory=list, max_length=MAX_TURNS)

    #     QUANTO AUDIO È PASSATO È UN FATTO; L'AUDIO NON LO È.
    #
    # Tre numeri, e nessun campione. Servono a poter dire, dopo, che il filo
    # ha funzionato davvero — quanti pacchetti sono arrivati, quanti byte,
    # quanto ci ha messo il primo. Senza, l'unica prova che l'audio sia
    # arrivato sarebbe una riga di log, che nessuno rilegge.
    # Perché la rete ha rifiutato, quando lo dice. Una parola dell'operatore,
    # non una diagnosi: «restricted» si sistema nel pannello, non nel codice.
    why_the_network_refused: str = Field(default="", max_length=120)

    audio_frames: int = 0
    audio_bytes: int = 0
    first_audio_ms: Optional[int] = None
    # I tempi della conversazione, turno per turno: quanto ha aspettato la
    # persona, quanto ci ha messo ORA a stare zitta quando l'hanno interrotta.
    # Solo numeri e nomi di stati — mai una parola di quello che si è detto,
    # mai un campione di audio.
    metrics: Dict[str, Any] = Field(default_factory=dict)

    # --- dopo -------------------------------------------------------------
    outcome: Optional[CallOutcome] = None
    # Cosa è stato scritto nel mondo per via di questa chiamata, se qualcosa.
    # Vuoto è il caso normale.
    wrote: List[str] = Field(default_factory=list, max_length=4)

    def how_ora_knows(self) -> str:
        """Da dove viene quello che ORA dice di sapere, in italiano."""
        day = (self.started_at or self.authorised_at or "")[:10]
        who = self.calling_whom or "il numero che mi hai dato"
        return f"L'ho chiesto al telefono a {who}" + (f", il {day}" if day else "")

    def for_human(self) -> Dict[str, Any]:
        """Quello che una persona legge. Nessun id, nessun numero di provider."""
        out: Dict[str, Any] = {
            "ho_chiamato": self.calling_whom or self.to_number,
            "perche": self.mandate.why_calling,
            "com_e_finita": {
                "we_hung_up": "ho chiuso io",
                "they_hung_up": "hanno chiuso loro",
                "no_answer": "non ha risposto nessuno",
                "busy": "occupato",
                "failed": "la chiamata non è partita",
                "unknown": "",
            }[self.how_it_ended],
        }
        if self.outcome:
            out["ho_capito"] = self.outcome.in_a_line if self.outcome.understood else None
            out["non_ho_capito"] = self.outcome.unclear or None
            out["ho_riportato_indietro"] = self.outcome.brought_back or None
        return {k: v for k, v in out.items() if v}
