"""
Che cosa ORA può accettare, scritto in modo che un backend possa verificarlo.

    «UN APPUNTAMENTO FRA GIOVEDÌ E SABATO, IN ORARIO DI STUDIO».

È il mandato come lo scrive una persona, ed è giusto che lo scriva così. Ma
nessun confronto di testo può decidere se «venerdì 18 alle 10» ci stia dentro,
e provarci produce falsi allarmi — il progetto l'ha già imparato una volta, e
da allora l'unico controllo sull'orario è un parafulmine da quattordici giorni
che non interpreta niente.

Questo file tiene la stessa autorità in una seconda forma: date vere, orari
veri, limiti veri. Quella che una persona legge resta dov'era; questa è quella
su cui si decide.

    E A DECIDERE È IL BACKEND. SEMPRE.

Chi telefona riporta che cosa gli hanno detto — è l'unico che l'ha sentito — e
si ferma lì. Che quella proposta sia dentro il mandato non è una cosa che può
stabilire chi sta parlando: è la stessa disciplina del confirmation gate, per
la stessa ragione. Un modello che giudica la propria autorità è un modello che
prima o poi se la allarga.

    QUATTRO RISPOSTE, E NON SI SOMIGLIANO.

`allowed` si può fare. `needs_user` non si può fare **da soli** — è un orario
fuori dal mandato, e una persona può autorizzarlo. `forbidden` non si può fare
e basta: un'operazione diversa, un altro oggetto, una cosa vietata per nome —
nessuno l'ha chiesto e nessuno lo chiederà al telefono. `invalid` vuol dire che
non si è capito abbastanza per giudicare, ed è diverso da un no.
"""

from __future__ import annotations

import logging
from datetime import date as _date
from datetime import datetime, timedelta
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger("ora.telephone.authority")

#     IL GIUDICE NON SA CHE COSA STA GIUDICANDO, E NON DEVE.
#
# L'elenco cresce coi domini — `complete` e `postpone` sono arrivate con gli
# impegni — ma qui dentro restano nomi: `evaluate_authority` confronta
# operazioni, oggetti e orari, e non ha un ramo per nessuno dei tre domini.
# Il giorno in cui ne avesse uno, sarebbe il momento in cui due domini
# possono ricevere due risposte diverse alla stessa domanda.
Operation = Literal[
    "reschedule", "book", "cancel", "complete", "postpone",
]

# Le quattro risposte del giudice.
Verdict = Literal["allowed", "needs_user", "forbidden", "invalid"]

# Le operazioni che hanno bisogno di un quando. Disdire non ne ha bisogno: è
# lo stesso appuntamento, tolto. E nemmeno chiudere: un impegno concluso non
# va da nessuna parte.
#
#     RIMANDARE INVECE È TUTTO UN QUANDO.
#
# «Slitta» non è un esito: senza una data è un'intenzione, e un mandato che la
# lasciasse passare autorizzerebbe una scrittura che non si può verificare.
NEEDS_A_TIME = ("reschedule", "book", "postpone")


class TimeSlot(BaseModel):
    """
    Un giorno e un'ora veri, non una frase.

        «GIOVEDÌ 8 ALLE 11» È UNA FRASE. QUESTO È UN ORARIO.

    La traduzione da una all'altro la fa chi ha sentito parlare — è già quello
    che fa per `complete_mission`, con lo stesso schema — e da qui in poi
    nessuno legge più parole.
    """

    date: str = Field(default="", max_length=10)     # AAAA-MM-GG
    time: str = Field(default="", max_length=5)      # HH:MM
    minutes: int = Field(default=0, ge=0, le=8 * 60)

    def is_real(self) -> bool:
        return bool(self.when())

    def when(self) -> Optional[datetime]:
        """Il momento preciso, o niente se non si riesce a leggerlo."""
        giorno, ora = (self.date or "").strip()[:10], (self.time or "").strip()[:5]
        if not giorno or not ora:
            return None
        try:
            return datetime.strptime(f"{giorno} {ora}", "%Y-%m-%d %H:%M")
        except ValueError:
            return None

    def same_moment_as(self, altro: "TimeSlot") -> bool:
        """
        Due fessure che indicano lo stesso momento.

        La durata non entra nel confronto: «venerdì alle 10» resta «venerdì
        alle 10» anche se uno dei due non sa quanto dura.
        """
        mio, suo = self.when(), altro.when()
        return mio is not None and suo is not None and mio == suo

    def says(self) -> str:
        """Come si dice a una persona. Serve ai motivi, non alle decisioni."""
        quando = self.when()
        return quando.strftime("%d/%m alle %H:%M") if quando else "(orario illeggibile)"


class CallMissionAuthority(BaseModel):
    """
    L'autorità di questa telefonata, in una forma che si può verificare.

        IL TESTO E LA POLICY SONO DUE COSE, E STANNO IN DUE POSTI.

    `human_summary` è quello che una persona ha scritto e che una persona
    rilegge; tutto il resto è quello su cui si decide. Tenerli nello stesso
    campo significherebbe, prima o poi, decidere leggendo una frase.
    """

    operation: Operation
    domain: str = Field(default="calendar", max_length=32)
    #     L'OGGETTO, QUANDO ESISTE.
    # Per una prenotazione no: nasce dopo. Vuoto è legittimo, ed è lo stesso
    # vuoto che il legame porta nel suo `target`.
    entity_id: str = Field(default="", max_length=64)

    # --- che cosa si è chiesto -------------------------------------------
    desired: Optional[TimeSlot] = None
    # Le alternative che si possono accettare senza richiamare nessuno. Date e
    # orari, non descrizioni.
    alternatives: List[TimeSlot] = Field(default_factory=list, max_length=12)

    # --- entro quali confini ----------------------------------------------
    earliest: str = Field(default="", max_length=20)   # AAAA-MM-GG
    latest: str = Field(default="", max_length=20)     # AAAA-MM-GG
    #     LO STESSO GIORNO, QUANDO CONTA.
    # «Spostalo più tardi, ma oggi» è un vincolo comunissimo e non si esprime
    # con due date: si esprime così.
    same_day_only: bool = False

    forbidden_changes: List[str] = Field(default_factory=list, max_length=8)
    #     QUELLO CHE ESCE DAL MANDATO TORNA A UNA PERSONA.
    # Falso vorrebbe dire che ORA può accettare qualunque cosa purché non sia
    # vietata per nome, ed è l'opposto di come è stato pensato il mandato.
    requires_user_confirmation: bool = True

    # Il mandato come l'ha scritto una persona. Si mostra, non si legge per
    # decidere.
    human_summary: str = Field(default="", max_length=400)

    def has_any_rule(self) -> bool:
        """
        Se qui dentro c'è abbastanza per giudicare qualcosa.

        Un'autorità senza nessun vincolo non è un'autorità permissiva: è
        un'autorità che non c'è, e chi la riceve deve saperlo distinguere.
        """
        return bool(
            self.desired or self.alternatives or self.earliest
            or self.latest or self.same_day_only or self.forbidden_changes
        )

    def already_allows(self, quando: TimeSlot) -> bool:
        """Se questo momento è già scritto fra quelli accettabili."""
        if self.desired is not None and self.desired.same_moment_as(quando):
            return True
        return any(a.same_moment_as(quando) for a in self.alternatives)

    def now_also_allows(self, quando: TimeSlot) -> "CallMissionAuthority":
        """
        La stessa autorità, con dentro una possibilità in più.

            UNA DECISIONE AGGIUNGE, NON RISCRIVE.

        Chi ha risposto «va bene così» non ha tolto niente: ha detto che anche
        quello va bene. E se quella possibilità c'era già, questa funzione non
        fa niente — è quello che rende una decisione presa due volte una
        decisione sola.
        """
        if not quando.is_real() or self.already_allows(quando):
            return self
        copia = self.model_copy(deep=True)
        copia.alternatives = [*copia.alternatives, quando][:12]
        return copia


class Proposal(BaseModel):
    """
    Quello che la controparte ha messo sul tavolo, tradotto in date.

    Non è un giudizio: è un rapporto. Chi lo scrive ha sentito le parole, e
    quello che fa è convertirle — la stessa cosa che fa per dire a che ora
    hanno spostato un appuntamento.
    """

    operation: str = Field(default="", max_length=32)
    slot: Optional[TimeSlot] = None
    entity_id: str = Field(default="", max_length=64)


class AuthorityVerdict(BaseModel):
    """La risposta del giudice: che cosa, e perché, in due forme."""

    verdict: Verdict
    # Il perché in una parola, per chi programma.
    code: str = Field(default="", max_length=48)
    # E in una riga, per chi legge.
    says: str = Field(default="", max_length=300)

    def ok(self) -> bool:
        return self.verdict == "allowed"


def evaluate_authority(
    proposal: Proposal, authority: Optional[CallMissionAuthority],
) -> AuthorityVerdict:
    """
    L'unico posto in cui si decide se una proposta sta dentro il mandato.

        CHI TELEFONA RIPORTA. CHI STA QUI GIUDICA.

    Deterministico di proposito: gli stessi due oggetti danno sempre la stessa
    risposta, e quella risposta si può rileggere fra sei mesi e capire perché.
    Nessun modello nel mezzo, nessuna frase da interpretare.
    """
    if authority is None or not authority.has_any_rule():
        #     NESSUNA REGOLA NON VUOL DIRE «TUTTO PERMESSO».
        # Vuol dire che non c'è abbastanza per giudicare, e chi ha chiamato
        # questa funzione deve saperlo — non ricevere un sì.
        return AuthorityVerdict(
            verdict="invalid", code="no_structured_authority",
            says="questa telefonata non ha un mandato verificabile",
        )

    fare = (proposal.operation or "").strip() or authority.operation
    if fare != authority.operation:
        return AuthorityVerdict(
            verdict="forbidden", code="operation_not_allowed",
            says=f"potevo solo {_in_italiano(authority.operation)}, "
                 f"non {_in_italiano(fare)}",
        )

    if (
        authority.entity_id and proposal.entity_id
        and proposal.entity_id != authority.entity_id
    ):
        #     UN ALTRO OGGETTO NON E' UN'ALTRA OPZIONE: E' UN ALTRO IMPEGNO.
        return AuthorityVerdict(
            verdict="forbidden", code="wrong_target",
            says="questa proposta riguarda un altro appuntamento",
        )

    vietato = _anything_forbidden(proposal, authority)
    if vietato:
        return AuthorityVerdict(
            verdict="forbidden", code="forbidden_change",
            says=f"non potevo cambiare {vietato}",
        )

    if authority.operation not in NEEDS_A_TIME:
        # Disdire non ha un quando da verificare: è lo stesso appuntamento.
        return AuthorityVerdict(
            verdict="allowed", code="no_time_to_check",
            says="rientra in quello che potevo fare",
        )

    quando = proposal.slot
    if quando is None or not quando.is_real():
        return AuthorityVerdict(
            verdict="invalid", code="no_time_in_proposal",
            says="non ho un giorno e un'ora da verificare",
        )

    if authority.desired is not None and authority.desired.same_moment_as(quando):
        return AuthorityVerdict(
            verdict="allowed", code="exactly_what_was_asked",
            says="è esattamente quello che avevo chiesto",
        )

    if any(a.same_moment_as(quando) for a in authority.alternatives):
        return AuthorityVerdict(
            verdict="allowed", code="explicitly_allowed",
            says=f"{quando.says()} era fra le alternative consentite",
        )

    fuori = _outside_the_bounds(quando, authority)
    if fuori:
        return AuthorityVerdict(
            verdict="needs_user", code=fuori[0], says=fuori[1],
        )

    #     DENTRO I CONFINI MA NON SCRITTO: SI CHIEDE.
    # È il caso più comune di tutti, ed è per questo che il mandato è un elenco
    # chiuso: quello che non c'è non è permesso, è da chiedere.
    return AuthorityVerdict(
        verdict="needs_user", code="not_in_the_mandate",
        says=f"{quando.says()} non era fra le cose che potevo accettare",
    )


def _anything_forbidden(proposal: Proposal, authority: CallMissionAuthority) -> str:
    """
    Se la proposta tocca qualcosa di vietato per nome.

    Confronto esatto, non somiglianza: il progetto ha già visto un controllo
    per somiglianza segnalare come violazione un appuntamento perfettamente
    dentro il mandato, e un allarme che grida a vuoto insegna a ignorarlo.
    """
    tocca = {"operation": (proposal.operation or "").strip().lower()}
    if proposal.slot is not None:
        tocca["date"] = (proposal.slot.date or "").strip()
        tocca["time"] = (proposal.slot.time or "").strip()
        if proposal.slot.minutes:
            tocca["duration"] = "duration"
    for vietato in authority.forbidden_changes:
        nome = (vietato or "").strip().lower()
        if nome and nome in tocca and tocca[nome]:
            return nome
    return ""


def _outside_the_bounds(quando: TimeSlot, authority: CallMissionAuthority):
    """I confini temporali, uno per uno. Torna `(codice, frase)` o niente."""
    momento = quando.when()
    if momento is None:
        return None

    if authority.same_day_only and authority.desired is not None:
        atteso = authority.desired.when()
        if atteso is not None and momento.date() != atteso.date():
            return (
                "different_day",
                f"{quando.says()} è un altro giorno, e potevo restare solo "
                f"su {atteso.strftime('%d/%m')}",
            )

    primo = _read_day(authority.earliest)
    if primo is not None and momento.date() < primo:
        return (
            "before_earliest",
            f"{quando.says()} è prima del {primo.strftime('%d/%m')}",
        )

    ultimo = _read_day(authority.latest)
    if ultimo is not None and momento.date() > ultimo:
        return (
            "after_latest",
            f"{quando.says()} è dopo il {ultimo.strftime('%d/%m')}",
        )
    return None


def _read_day(testo: str) -> Optional[_date]:
    grezzo = (testo or "").strip()[:10]
    if not grezzo:
        return None
    try:
        return datetime.strptime(grezzo, "%Y-%m-%d").date()
    except ValueError:
        return None


def _in_italiano(operazione: str) -> str:
    return {
        "reschedule": "spostare", "book": "prenotare", "cancel": "disdire",
        "complete": "chiudere", "postpone": "rimandare",
    }.get((operazione or "").strip(), operazione or "fare questo")


def a_slot_from(date: str, time: str, minutes: int = 0) -> TimeSlot:
    """Una fessura da tre pezzi, senza far scrivere il modello a nessuno."""
    try:
        quanti = int(minutes or 0)
    except (TypeError, ValueError):
        quanti = 0
    return TimeSlot(
        date=str(date or "").strip()[:10],
        time=str(time or "").strip()[:5],
        minutes=quanti if 0 < quanti <= 8 * 60 else 0,
    )
