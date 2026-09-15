"""
Una telefonata sola, con dentro solo quello che serve per farla.

    ORA SA TUTTO. CHI TELEFONA SA UNA COSA.

Il fascicolo dello Sprint 3 portava in linea «quello che ORA sa»: il mandato,
la presentazione, e le situazioni aperte della persona — fino a quattro, con
il loro titolo. Serviva a capire di cosa si parlasse, ed era ragionevole
finché a parlare era ORA stessa.

Non lo è più quando a parlare è un modello che vive fuori. Un elenco di cose
aperte nella vita di qualcuno non serve a spostare un appuntamento dal
dentista, e quello che non serve non si manda.

    MINIMA DIVULGAZIONE: SI PORTA LA MISSIONE, NON LA PERSONA.

Qui dentro c'è un obiettivo, una controparte, uno stato di partenza, uno di
arrivo, e i confini entro cui si può trattare. Tutto il resto resta dov'è, e
si chiede **se e quando** serve — una domanda alla volta, e la risposta la
decide ORA, non chi sta parlando.

    E IL NUMERO DI TELEFONO NON C'È.

Chi compone il numero è il trasporto; chi parla non ne ha bisogno. Un dato
che non serve a chi lo riceve è un dato che non gli si dà, anche quando è
innocuo — perché «innocuo» è un giudizio che invecchia male.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from telephone.introduction import Introduction

MissionType = Literal[
    "reschedule",   # spostare qualcosa che esiste
    "book",         # prenderne uno nuovo
    "cancel",       # disdire
    "ask",          # chiedere e basta, senza impegnarsi
    "confirm",      # verificare che una cosa sia com'è scritta
]

MissionStatus = Literal[
    "success",      # la missione è compiuta e la controparte l'ha confermato
    "partial",      # qualcosa è stato fatto, non tutto
    "failed",       # non si è potuto fare
    "needs_user",   # serve una decisione che nessuno aveva autorizzato
]

# Quanto è delicato un dato. Non è il modello a stabilirlo, e non è nemmeno
# una proprietà del dato in sé: è quanto costa a una persona che quel dato
# esca per sbaglio.
Sensitivity = Literal[
    "public",       # il nome di uno studio dentistico
    "mission",      # l'orario dell'appuntamento che si sta spostando
    "identity",     # nome e cognome, data di nascita, codice fiscale
    "high",         # documenti, salute, denaro, credenziali
]


# Che cosa ha appena fatto la controparte con le parole. Non e una sfumatura
# di stile: e la differenza fra una porta aperta e una porta attraversata.
#
#     «ALLE 18 ABBIAMO POSTO» NON E «L'HO SPOSTATO ALLE 18».
#
# La prima dice che si puo; la seconda dice che e stato fatto. Un esecutore
# che le confonde chiude la telefonata con in mano un appuntamento che nessuno
# ha mai spostato, e la persona si presenta alle diciotto davanti a una porta
# chiusa.
StatementKind = Literal[
    "availability",   # c'e posto, si potrebbe fare
    "proposal",       # propongono loro qualcosa di preciso
    "confirmation",   # l'hanno registrato: e fatto
    "refusal",        # no
    "detail",         # altro, pertinente ma che non muove la trattativa
]

# I passaggi di una trattativa, dal primo squillo alla stretta di mano. Il
# backend ne tiene il conto: chi parla puo dire quello che vuole, ma da quale
# passaggio siamo lo stabilisce chi ascolta.
MissionProgress = Literal[
    "opening",                    # si sono appena presentati
    "available",                  # hanno detto che ci sarebbe posto
    "proposed",                   # hanno messo sul tavolo una cosa precisa
    "accepted_by_agent",          # noi abbiamo detto di si, e aspettiamo
    "confirmed_by_counterparty",  # loro hanno detto che e registrato
    "completed",                  # e chiusa
]


class CounterpartyStatement(BaseModel):
    """
    Una frase della controparte, con addosso che cosa fa.

    Il tipo lo dichiara chi sta parlando, dentro una enum stretta — ma non e
    una dichiarazione che si accetta sulla fiducia: il `turn` dice in che
    battuta e arrivata, e su quello il backend ha l'ultima parola.
    """

    kind: StatementKind
    fact: str = Field(max_length=200)
    # In quale battuta della controparte e stata detta. Serve al gate: una
    # conferma non puo stare nello stesso respiro della disponibilita.
    turn: int = 0


class MissionFact(BaseModel):
    """
    Un fatto che si può dire, e quanto costa dirlo.

    Non è una stringa: è una stringa con addosso il motivo per cui è lì. Un
    fatto senza motivo è un fatto che prima o poi qualcuno manda perché
    «tanto c'era».
    """

    field: str = Field(min_length=1, max_length=60)
    value: str = Field(max_length=200)
    sensitivity: Sensitivity = "mission"
    # Perché questo dato è nella missione. Se non si riesce a scriverlo, il
    # dato non serve.
    why_it_is_here: str = Field(default="", max_length=160)


class CallMissionPacket(BaseModel):
    """
    Tutto quello che serve per fare **questa** telefonata, e niente di più.

        SE UN CAMPO NON SERVE A QUESTA CHIAMATA, NON ESISTE.

    Piccolo per una ragione misurata: il prompt di ORA pesa 18.650 token e
    costa due secondi e mezzo a leggerlo. Una voce al telefono deve rispondere
    in uno e mezzo, e non può portarsi dietro una vita intera per spostare un
    appuntamento.
    """

    mission_id: str = Field(min_length=1, max_length=64)
    mission_type: MissionType
    # L'obiettivo in una riga, con le parole di chi ha chiesto la chiamata.
    goal: str = Field(min_length=1, max_length=200)

    # --- chi c'è dall'altra parte ----------------------------------------
    counterparty: str = Field(min_length=1, max_length=120)
    on_behalf_of: str = Field(min_length=1, max_length=80)
    #     IL NUMERO NON STA QUI, ED È DELIBERATO.
    # Lo compone il trasporto. Chi parla non ne ha bisogno, e un dato che non
    # serve a chi lo riceve non gli si dà.

    # --- quando siamo, dove sta la persona --------------------------------
    local_datetime: str = Field(min_length=1, max_length=40)
    timezone: str = Field(min_length=1, max_length=60)

    # --- da cosa a cosa ----------------------------------------------------
    subject: str = Field(min_length=1, max_length=160)
    current_state: Dict[str, str] = Field(default_factory=dict)
    desired_state: Dict[str, str] = Field(default_factory=dict)

    # --- i confini ---------------------------------------------------------
    hard_constraints: List[str] = Field(default_factory=list, max_length=6)
    soft_preferences: List[str] = Field(default_factory=list, max_length=6)
    # Quello che si può accettare in linea senza richiamare nessuno. Viene dal
    # mandato, che è la stessa cosa che governa il runtime classico.
    allowed_negotiation: List[str] = Field(default_factory=list, max_length=8)
    forbidden_actions: List[str] = Field(default_factory=list, max_length=8)

    # --- cosa si può dire e cosa si può chiedere ---------------------------
    known_facts: List[MissionFact] = Field(default_factory=list, max_length=10)
    # I campi che si possono chiedere **durante** la chiamata, uno alla volta,
    # e che ORA deciderà se consegnare. Qui c'è il nome del campo, mai il
    # valore: il valore esce solo se qualcuno lo chiede e ORA dice di sì.
    allowed_on_demand_fields: List[str] = Field(
        default_factory=list, max_length=10,
    )

    # --- com'è andata si riconosce così ------------------------------------
    success_criteria: List[str] = Field(default_factory=list, max_length=5)
    failure_criteria: List[str] = Field(default_factory=list, max_length=5)
    escalation_conditions: List[str] = Field(default_factory=list, max_length=6)

    # --- come si parla -----------------------------------------------------
    #     CHI CHIAMA SI PRESENTA, E NON SI PRESENTA COME QUALCUN ALTRO.
    # L'apertura non e un suggerimento di stile: e un contratto, con due
    # contenuti obbligatori che il runtime verifica di aver consegnato. Sta
    # qui dentro perche nasce dalla missione — di chi siamo l'assistente e
    # perche chiamiamo sono due cose che il pacchetto gia sa.
    introduction: Optional["Introduction"] = None
    say_this_first: str = Field(default="", max_length=200)
    style: str = Field(default="", max_length=300)

    def for_the_model(self) -> str:
        """
        Il packet come lo legge chi parla: compatto, e senza campi vuoti.

            UN CAMPO VUOTO OCCUPA POSTO E NON DICE NIENTE.

        Si tolgono le chiavi senza valore e si scrive stretto. Su un contesto
        che deve restare sotto i duemila token, la punteggiatura pesa.
        """
        grezzo = self.model_dump(exclude_none=True)
        pulito = {
            k: v for k, v in grezzo.items()
            if v not in (None, "", [], {})
        }
        # I fatti si scrivono senza il motivo: quello serve a chi costruisce il
        # packet per decidere se metterlo, non a chi parla per usarlo.
        if pulito.get("known_facts"):
            pulito["known_facts"] = {
                f["field"]: f["value"] for f in pulito["known_facts"]
            }
        return json.dumps(pulito, ensure_ascii=False, separators=(",", ":"))

    def may_release(self, field: str) -> bool:
        """Se questo campo può essere chiesto durante la chiamata."""
        wanted = (field or "").strip().lower()
        return bool(wanted) and wanted in {
            f.strip().lower() for f in self.allowed_on_demand_fields
        }

    def already_knows(self, field: str) -> Optional[str]:
        """Il valore di un fatto già nel packet, se c'è."""
        wanted = (field or "").strip().lower()
        for fact in self.known_facts:
            if fact.field.strip().lower() == wanted:
                return fact.value
        return None


class CallMissionOutcome(BaseModel):
    """
    Che cosa è successo, in una forma che ORA può validare.

        CHI HA PARLATO NON SCRIVE NIENTE NEL MONDO.

    Questo oggetto non è un comando: è un resoconto. ORA lo legge, controlla
    che stia dentro la missione e dentro l'autorità, e solo allora tocca il
    calendario o la memoria. Un modello che aggiorna un calendario da solo è
    un modello che può sbagliare appuntamento a nome di qualcuno.
    """

    mission_id: str = Field(min_length=1, max_length=64)
    status: MissionStatus

    # Quello che la controparte ha **confermato**, non quello che sembrava.
    confirmed_changes: Dict[str, str] = Field(default_factory=dict)
    rejected_changes: List[str] = Field(default_factory=list, max_length=6)
    # Frasi della controparte che contano, ognuna con che cosa fa: una che
    # apre una porta e una che la attraversa non si possono piu confondere.
    counterparty_statements: List[CounterpartyStatement] = Field(
        default_factory=list, max_length=8,
    )
    # Fatti nuovi emersi, solo se pertinenti alla missione.
    new_facts: List[MissionFact] = Field(default_factory=list, max_length=6)
    # Che cosa serve chiedere a chi ha ordinato la chiamata.
    user_confirmation_needed: str = Field(default="", max_length=300)
    #     E LA PROPOSTA ANCHE IN DATE, QUANDO SI RIESCE A TRADURLA.
    # «Giovedi' 8 alle 11» e' una frase, e una frase non si puo' confrontare
    # con un mandato. Chi ha sentito parlare e' l'unico che puo' convertirla —
    # lo fa gia' per dire a che ora hanno spostato un appuntamento — e qui
    # quella conversione serve a far entrare la decisione nella policy invece
    # che in un elenco di testo.
    proposed_slot: Dict[str, Any] = Field(default_factory=dict)
    followup_required: bool = False
    notes: str = Field(default="", max_length=400)

    def is_actionable(self) -> bool:
        """
        Se da qui si può muovere qualcosa nel mondo.

        Solo un successo confermato con dei cambiamenti dentro. Tutto il resto
        torna a una persona: «parziale» e «serve l'utente» sono esiti, non
        permessi.
        """
        return self.status == "success" and bool(self.confirmed_changes)


class MissionLedger:
    """
    Chi tiene il conto di dove siamo arrivati davvero.

        LA DISPONIBILITA NON E UNA CONFERMA, E NON LO DIVENTA DICENDOLO.

    Il PoC ci ha mostrato un esecutore che chiudeva la missione su «alle
    diciotto abbiamo posto». Aveva capito bene: c'era posto. Ma nessuno aveva
    ancora spostato niente, e un appuntamento non spostato e peggio di un
    appuntamento non chiesto — perche la persona ci conta.

    La tentazione era scriverlo nel prompt. Un prompt e una raccomandazione:
    regge finche il modello ha voglia di darle retta, e non lascia traccia di
    perche una telefonata sia finita come e finita. Questo registro invece e
    una condizione, e sta dalla parte di chi ha l'autorita.

    Due cose deve vedere prima di lasciar chiudere:

        una frase dichiarata `confirmation`;
        e che non sia nello stesso respiro della disponibilita.

    La seconda e quella che conta davvero. Il tipo lo dichiara chi parla, e
    chi parla puo sbagliarsi in buona fede; ma per confermare una cosa
    **dopo** averla proposta bisogna che la controparte abbia riaperto bocca,
    e quello e un fatto, non un giudizio. In mezzo ci finisce per forza la
    domanda che mancava: «allora me lo conferma?».
    """

    #     LE MISSIONI CHE CAMBIANO UNO STATO CHIEDONO UN GIRO IN PIU'.
    # Spostare, prenotare, disdire: sono cose che qualcuno deve *fare*, e fra
    # il dire che si puo fare e l'averlo fatto c'e un passaggio. Chiedere
    # un'informazione no — li una risposta sola basta ed e' gia l'esito.
    CHANGES_THE_WORLD = ("reschedule", "book", "cancel")

    def __init__(self, mission_type: str = "reschedule") -> None:
        self._heard: List[CounterpartyStatement] = []
        self._turn = 0
        self._closed = False
        self._changes_something = mission_type in self.CHANGES_THE_WORLD

    # --- il tempo della conversazione -------------------------------------

    def a_new_turn_begins(self) -> None:
        """La controparte ha ripreso a parlare."""
        self._turn += 1

    def heard(self, kind: str, fact: str = "") -> CounterpartyStatement:
        """Annota una frase, con il tipo che le da chi sta parlando."""
        detta = CounterpartyStatement(
            kind=kind, fact=(fact or "")[:200], turn=self._turn,
        )
        self._heard.append(detta)
        return detta

    @property
    def statements(self) -> List[CounterpartyStatement]:
        return list(self._heard)

    # --- dove siamo arrivati ----------------------------------------------

    def _last_turn_of(self, *kinds: str) -> Optional[int]:
        turni = [d.turn for d in self._heard if d.kind in kinds]
        return max(turni) if turni else None

    @property
    def progress(self) -> str:
        if self._closed:
            return "completed"
        if self._a_real_confirmation() is not None:
            return "confirmed_by_counterparty"

        aperto = self._last_turn_of("availability", "proposal")
        if aperto is not None:
            # Se da allora la controparte ha riparlato, vuol dire che noi nel
            # frattempo avevamo detto di si: siamo noi ad aspettare loro.
            if self._turn > aperto:
                return "accepted_by_agent"
            if self._last_turn_of("proposal") == aperto:
                return "proposed"
            return "available"
        return "opening"

    def _a_real_confirmation(self) -> Optional[CounterpartyStatement]:
        """
        La prima conferma che regge davvero.

        Due condizioni, e nessuna delle due guarda le parole.

            NON NELLO STESSO RESPIRO DELLA DISPONIBILITA'.

        Una porta aperta e attraversata nella stessa frase e' quasi sempre una
        porta solo aperta.

            E NON ALLA PRIMA COSA CHE DICONO.

        Questa e' nuova, ed e' arrivata da una telefonata vera. Perche'
        qualcuno confermi una modifica bisogna che gliel'abbiamo chiesta; e
        perche' gliel'abbiamo chiesta bisogna che avesse gia' detto qualcosa
        prima. Quindi una conferma vale solo se la controparte aveva gia'
        parlato in un turno precedente — chiunque abbia scelto l'etichetta.

        Vale per le missioni che cambiano qualcosa nel mondo. Per una domanda
        secca non serve: li la prima risposta e' gia l'esito.
        """
        for detta in self._heard:
            if detta.kind != "confirmation":
                continue
            aperto = self._last_turn_of_before("availability", "proposal",
                                               limite=detta.turn)
            if aperto is not None and detta.turn <= aperto:
                continue
            if self._changes_something and not self._somebody_spoke_before(detta):
                continue
            return detta
        return None

    def _somebody_spoke_before(self, detta: CounterpartyStatement) -> bool:
        """
        Se la controparte aveva gia' aperto bocca in un turno precedente.

        E' il modo osservabile di dire «non e' la prima cosa che ci hanno
        detto»: fra due turni della controparte c'e per forza qualcosa che
        abbiamo detto noi, ed e quella la richiesta che rende una conferma una
        conferma.
        """
        return any(
            altra is not detta and altra.turn < detta.turn
            for altra in self._heard
        )

    def _last_turn_of_before(self, *kinds: str, limite: int) -> Optional[int]:
        turni = [
            d.turn for d in self._heard
            if d.kind in kinds and d.turn <= limite
        ]
        return max(turni) if turni else None

    # --- e il permesso di chiudere ----------------------------------------

    def why_not_complete(
        self,
        confirmed_changes: Optional[dict],
        confirmation: str = "",
    ) -> str:
        """
        Il motivo per cui questa chiusura non si accetta, o stringa vuota.

        Prima si controlla che ci sia scritto **che cosa** e stato confermato:
        un successo senza un oggetto non e un successo. Poi che qualcuno
        l'abbia davvero detto.

        La frase che conferma si puo portare qui, insieme alla chiusura.

            LA PROVA VIAGGIA CON LA RICHIESTA, NON PRIMA DI ESSA.

        Alla prima prova con il gate acceso abbiamo visto il caso peggiore:
        lo studio aveva confermato davvero — «e fatto, l'ho spostato alle
        diciotto» — e la chiusura e stata respinta lo stesso, perche la voce
        era andata dritta a chiudere senza annotare quella frase. Chiedere a
        chi parla di ricordarsi due gesti in fila quando ne basta uno e un
        modo elegante di costruirsi un loop.

        Il turno resta l'autorita: una conferma portata nello stesso respiro
        in cui ci hanno detto che ci sarebbe posto non vale, chiunque la
        dichiari.
        """
        if not confirmed_changes:
            return "missing_changes"
        if confirmation.strip():
            self.heard("confirmation", confirmation)
        if self.progress == "confirmed_by_counterparty":
            return ""
        #     PERCHE' NON SI CHIUDE CAMBIA COSA BISOGNA CHIEDERE.
        # Se non hanno ancora detto niente, la domanda non e «me lo conferma?»
        # ma «puo farlo?»: chiedere conferma di una cosa che nessuno ha ancora
        # fatto e' il modo piu veloce di farsi dire di si a vuoto.
        if self._changes_something and not self._heard_more_than_one_turn():
            return "change_not_requested_yet"
        return "confirmation_required"

    def _heard_more_than_one_turn(self) -> bool:
        turni = {d.turn for d in self._heard}
        return len(turni) > 1

    def completed(self) -> None:
        self._closed = True

    def something_is_on_the_table(self) -> bool:
        """
        Se e rimasta in sospeso una cosa che qualcuno potrebbe voler valutare.

            «NON SI PUO FARE» E «QUALCUNO DEVE DECIDERE» NON SONO LO STESSO ESITO.

        Alla seconda telefonata vera lo studio ha proposto domani alle undici.
        La voce ha detto la cosa giusta — «devo sentire Francesco» — e poi ha
        chiuso dichiarando un fallimento. Ma un fallimento e una porta chiusa,
        e quella porta era aperta: c'era un'alternativa sul tavolo, fuori dal
        mandato, che solo una persona puo accettare o scartare.

        La differenza non e una sfumatura di parole: decide se domani qualcuno
        rilegge «non si e potuto fare» oppure «ti hanno proposto questo».
        """
        for detta in self._heard:
            if detta.kind in ("availability", "proposal"):
                return True
        return False


# Che cosa rispondere a chi ha provato a chiudere troppo presto. Due registri
# diversi apposta: `instruction` e per chi ragiona, `say` e per la bocca — e
# la bocca non nomina mai strumenti ne sistemi.
REFUSALS: Dict[str, Dict[str, str]] = {
    "missing_changes": {
        "instruction": (
            "Non hai indicato che cosa e stato confermato. Fattelo ripetere e "
            "riporta data e ora esatte in confirmed_changes."
        ),
        "say": (
            "Prima di chiudere: mi conferma la data e l'ora esatte del nuovo "
            "appuntamento?"
        ),
    },
    "change_not_requested_yet": {
        "instruction": (
            "Non hai ancora chiesto di eseguire la modifica: finora ti hanno "
            "solo detto che si potrebbe fare. Chiedi esplicitamente di farla, "
            "aspetta che ti rispondano, e solo allora chiudi."
        ),
        "say": "Perfetto. Allora puo procedere e spostarlo?",
    },
    "confirmation_required": {
        "instruction": (
            "Finora la controparte ha detto soltanto che ci sarebbe posto. "
            "Chiedile di confermare che la modifica e stata registrata, "
            "annota la risposta come confirmation e solo allora chiudi."
        ),
        "say": (
            "Perfetto. Me lo conferma che l'appuntamento risulta spostato?"
        ),
    },
}


def mission_id_for(call_id: str) -> str:
    """
    Il nome della missione di questa telefonata. Uno, sempre lo stesso.

    Sta qui perche' e' della missione: il legame con l'oggetto da modificare
    lo usa per ritrovarla, e il record dell'applicazione per non applicarla
    due volte, ma nessuno dei due lo inventa.
    """
    return f"mis_{call_id}"[:64]


def packet_for(
    call,
    dossier,
    *,
    current_when: str = "",
    desired_when: str = "",
    binding=None,
) -> CallMissionPacket:
    """
    La missione, costruita da quello che ORA sapeva gia prima di comporre.

        NON SI INVENTA UN SECONDO MANDATO.

    Il mandato di questa telefonata esiste gia — e' lo stesso che governa il
    runtime classico — e qui si traduce, non si riscrive. Quello che entra e'
    un sottoinsieme: obiettivo, controparte, confini, e nient'altro.

        E IL NUMERO RESTA FUORI, ANCHE ADESSO.

    `call.to_number` e' a un attributo di distanza, ed e' esattamente per
    questo che va detto: non ci finisce, e non e' una dimenticanza.

        E NEMMENO L'IDENTIFICATIVO DELL'EVENTO.

    Se questa missione e' legata a un appuntamento del calendario, il legame
    porta due cose diverse: **quando** e' l'appuntamento, che serve a parlare —
    «quello delle sedici» — e **quale** e', che non serve a parlare per
    niente. Il primo entra qui. Il secondo resta nel legame, sul server, e chi
    telefona non lo vede mai: e' la stessa regola del numero, applicata a un
    dato che sarebbe ancora piu' inutile pronunciare.
    """
    perche = (call.mandate.why_calling or "").strip()
    tipo = _what_kind_of_mission(perche)

    if binding is not None and not current_when:
        current_when = (binding.expected or {}).get("start_datetime", "")
    if binding is not None and not desired_when:
        #     UNA PRENOTAZIONE NON HA UN PRIMA, SOLO UN DOPO.
        # Per le altre due missioni il legame porta da dove si parte; qui
        # porta dove si vuole arrivare, ed e' l'unica cosa che chi parla deve
        # chiedere. L'identificativo dell'evento non c'e' nemmeno adesso:
        # quello nascera' dopo, e non si pronuncia comunque.
        desired_when = (binding.desired or {}).get("start_datetime", "")

    #     IL NOME DELLA MISSIONE VIENE DAL LEGAME, QUANDO C'E'.
    #
    # Di solito e' quello della telefonata. Non lo e' quando una commissione
    # si e' fermata e ha ripreso: la seconda chiamata porta il nome della
    # prima, ed e' cosi' che l'esito che ne esce ha la chiave della missione
    # logica invece che una tutta sua.
    #
    # Ricalcolarlo da `call.id` sembrava innocuo. Sul vero ha prodotto due
    # chiavi di idempotenza per la stessa commissione — e due chiavi vogliono
    # dire che la stessa cosa si puo' applicare due volte.
    nome = (
        binding.mission_id if binding is not None and binding.mission_id
        else mission_id_for(call.id)
    )

    packet = CallMissionPacket(
        mission_id=nome,
        mission_type=tipo,
        goal=perche[:200] or "parlare con la controparte",
        counterparty=(call.calling_whom or "la controparte")[:120],
        on_behalf_of=(dossier.on_behalf_of or "la persona che mi ha mandato")[:80],
        local_datetime=_now_local(),
        timezone=_where_they_are(),
        subject=_what_it_is_about(perche) or "la ragione di questa chiamata",
        current_state={"when": current_when} if current_when else {},
        desired_state={"when": desired_when} if desired_when else {},
        allowed_negotiation=list(call.mandate.may_agree_to)[:8],
        forbidden_actions=[
            "accettare qualcosa che non sia nelle alternative consentite",
            "prendere altri impegni a nome della persona",
            "accettare costi, penali o altre prestazioni",
        ],
        known_facts=[],
        allowed_on_demand_fields=["data_di_nascita"],
        success_criteria=list(call.mandate.must_bring_back)[:5],
        style="Breve, cortese, concreta. Una cosa per volta.",
    )

    from telephone.introduction import introduction_for

    packet.introduction = introduction_for(packet)
    #     IL SALUTO SEGUE L'ORA DI CHI TELEFONA, NON QUELLA DEL SERVER.
    # `local_datetime` porta gia' il fuso della persona: e' l'unico orologio
    # che conti per decidere fra «buongiorno» e «buonasera».
    packet.say_this_first = packet.introduction.opening_line(
        packet.local_datetime)[:200]
    return packet


# Che cosa si va a fare, letto dal mandato che la persona ha scritto. Nel
# dubbio si sceglie il permesso piu' piccolo: `ask` non muove niente.
_KINDS = (
    ("reschedule", ("spost", "riman", "post", "anticip")),
    ("cancel", ("disdi", "annull", "cancell")),
    ("book", ("prenot", "fissa", "fissare")),
    ("confirm", ("conferm", "verific")),
)


#     IL VERBO CHE APRE LA FRASE VALE PIU' DI UNA SILLABA IN MEZZO.
# «Confermare la prenotazione del ristorante» finiva fra le prenotazioni,
# perche «prenotazione» contiene «prenot»: ne usciva «chiamo per prenotare la
# sua prenotazione», e soprattutto una missione con l'autorita sbagliata.
def _what_kind_of_mission(why: str) -> str:
    testo = (why or "").strip().lower()
    prima = testo.split()[0] if testo.split() else ""
    for tipo, indizi in _KINDS:
        if any(prima.startswith(i) for i in indizi):
            return tipo
    for tipo, indizi in _KINDS:
        if any(i in testo for i in indizi):
            return tipo
    return "ask"


def _now_local() -> str:
    from datetime import datetime

    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo(_where_they_are())).isoformat(timespec="seconds")
    except Exception:
        return datetime.now().isoformat(timespec="seconds")


def _where_they_are() -> str:
    import os

    return (os.environ.get("ORA_TIMEZONE") or "Europe/Rome").strip()


#     IL MANDATO E' UNA RICHIESTA. L'OGGETTO E' UNA COSA.
# La persona scrive «spostare il mio appuntamento dal dentista di oggi alle 16
# alle 18», che e' giusto per un mandato e sbagliato per una presentazione:
# premettendoci un altro verbo veniva fuori «chiamo per spostare il suo
# spostare il mio appuntamento». Qui si tiene solo il nome della cosa.
_LEADING_VERBS = (
    "spostare", "riprogrammare", "posticipare", "anticipare", "prenotare",
    "fissare", "disdire", "annullare", "cancellare", "confermare",
    "verificare", "chiedere", "sapere",
)


def _what_it_is_about(why: str) -> str:
    import re as _re

    testo = (why or "").strip()
    basso = testo.lower()
    for verbo in _LEADING_VERBS:
        if basso.startswith(verbo + " "):
            testo = testo[len(verbo) + 1:]
            break
    # Il possessivo di chi ha scritto il mandato non e' quello di chi parla.
    testo = _re.sub(r"^(il|lo|la|i|gli|le|l')\s*(mio|mia|miei|mie)\s+", "", testo, flags=_re.I)
    # L'ordine conta: `un` prima di `una` si mangerebbe solo la prima
    # meta dell'articolo e lascerebbe «a revisione».
    testo = _re.sub(
        r"^(?:(?:il|lo|la|i|gli|le|una|uno|un)\s+|(?:l'|un'))",
        "", testo, flags=_re.I,
    )
    # E gli orari li dice l'apertura, non l'oggetto.
    testo = _re.sub(r"\s+(dalle|alle|dal|al|per le)\s+\d.*$", "", testo, flags=_re.I)
    return testo.strip(" ,.;:")[:160]
