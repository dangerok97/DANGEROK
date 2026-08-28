"""
The guided first setup: what ORA asks, in what shape, and what an answer means.

This is a declarative catalogue, not a flow. Each entry says one thing worth
knowing, how it is best answered — a choice, a number, a place, a document —
and what has to be true for it to be worth asking at all. Nothing here is a
sequence: the order emerges from what somebody has already said, which is why
two people get different questions in the same area and why saying "non lavoro"
closes a branch instead of skipping past it.

Three rules shape every entry:

**Structured first.** During the first setup a person answers by choosing, not
by writing. Free text exists only behind "Altro", and only for the objective
that was already on screen — it never opens a general conversation.

**An option can mean "there is none".** "Non ho l'auto" is not a skip: it
resolves the question it answers and retires everything that depended on it, so
a life without a car stops being an incomplete life.

**The frontend renders, it does not decide.** Which question comes next, which
options exist, what an answer implies — all of it is here. The interface
receives an objective and draws it.

The facts these produce are written into the same `LifeProfile` everything else
writes into. There is no second store for setup answers.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field

ControlType = Literal[
    "single",     # one card from a set
    "multi",      # several cards
    "yes_no",     # two clear options
    "currency",   # an amount, in euro
    "number",
    "date",
    "location",   # a place, typed with suggestions
    "document_upload",  # hand ORA a file instead of answering
    "text",       # only ever reached through "Altro"
]


class Option(BaseModel):
    """One answer somebody can choose, and what it means."""

    id: str
    label: str
    description: str = ""
    # What choosing this establishes. Values are facts about a life, written
    # into the profile exactly as any other fact is.
    sets: Dict[str, Any] = Field(default_factory=dict)
    # Objectives this answer retires: there is nothing left to know, because
    # there is nothing there. Not the same as skipping.
    not_applicable: Tuple[str, ...] = ()
    # "Preferisco non indicarlo" — an answer, and never asked again.
    declines: bool = False


class Condition(BaseModel):
    """What has to be true for an objective to be worth asking."""

    key: str
    # Any of these values. Empty means "any value at all".
    equals: Tuple[str, ...] = ()
    # True when the fact must be *absent* or false.
    absent: bool = False

    def holds(self, facts: Dict[str, Any]) -> bool:
        raw = facts.get(self.key)
        present = raw not in (None, "", [], {}, False, "False", "false")
        if self.absent:
            return not present
        if not present:
            return False
        if not self.equals:
            return True
        value = str(raw).strip().lower()
        # Multi-select answers arrive as lists.
        if isinstance(raw, (list, tuple, set)):
            values = {str(v).strip().lower() for v in raw}
            return bool(values & {e.lower() for e in self.equals})
        return value in {e.lower() for e in self.equals}


class GuidedObjective(BaseModel):
    """One thing ORA would like to understand, and how to ask it."""

    id: str
    area_id: str
    question: str
    hint: str = ""
    control: ControlType = "single"
    options: List[Option] = Field(default_factory=list)
    allow_other: bool = True
    allow_skip: bool = True
    # "Preferisco non indicarlo" as a first-class answer, for the questions
    # where refusing is a reasonable thing to want.
    allow_decline: bool = False
    sensitivity: str = "normal"
    weight: float = 0.6
    depends_on: List[Condition] = Field(default_factory=list)
    # Some things are better read than typed.
    document_type: Optional[str] = None
    unit: str = ""

    def relevant(self, facts: Dict[str, Any]) -> bool:
        return all(c.holds(facts) for c in self.depends_on)


def _o(id: str, label: str, **kw: Any) -> Option:
    return Option(id=id, label=label, **kw)


# ---------------------------------------------------------------------------
# Before the areas: what to call somebody
#
# It belongs to no part of a life, which is exactly why it cannot live inside
# one. Asked in the middle of Casa it reads as a form changing subject; asked
# once at the start it is simply the first thing two people establish.
#
# It is skipped entirely when the account already has a name worth using.
# ---------------------------------------------------------------------------

IDENTITY_OBJECTIVE = GuidedObjective(
    id="identity.preferred_name",
    area_id="",
    question="Come preferisci che ti chiami?",
    hint="Serve solo per rivolgersi a te nel modo giusto.",
    control="text",
    weight=0.0,
    allow_other=False,
    allow_skip=True,
)


# ---------------------------------------------------------------------------
# Casa
#
# The first area, and the one that has to prove the setup is worth doing. Two
# facts — a town and "di proprietà" — is not a picture of where somebody lives:
# it says nothing about who is there, what it costs, or what ORA could actually
# help with.
# ---------------------------------------------------------------------------

_CASA: List[GuidedObjective] = [
    GuidedObjective(
        id="casa.situazione",
        area_id="casa",
        question="Qual è la tua situazione abitativa principale?",
        hint="Scegli l'opzione che ti rappresenta meglio.",
        control="single",
        weight=1.0,
        options=[
            # Every branch records what it establishes, including the negative
            # one. Found in QA: somebody said "casa in affitto" and the
            # ownership objective stayed open forever — no later question
            # asks it, so their Casa could never be complete and ORA kept
            # counting as missing something it had just been told.
            _o("proprieta", "Casa di proprietà", sets={"casa.owned": True}),
            _o("affitto", "Casa in affitto", sets={"casa.affitto": True, "casa.owned": False},
               not_applicable=("casa.mutuo", "casa.mutuo_rata", "doc.rogito")),
            _o("familiari", "Vivo con familiari", sets={"casa.owned": False},
               not_applicable=("casa.mutuo", "casa.mutuo_rata", "casa.affitto_canone", "doc.rogito")),
            _o("uso_gratuito", "Ospite / uso gratuito", sets={"casa.owned": False},
               not_applicable=("casa.mutuo", "casa.mutuo_rata", "casa.affitto_canone", "doc.rogito")),
        ],
    ),
    GuidedObjective(
        id="casa.citta",
        area_id="casa",
        question="Dove si trova la casa?",
        hint="Basta il comune: serve per scadenze e servizi locali.",
        control="location",
        weight=0.9,
        allow_other=False,
    ),
    GuidedObjective(
        id="casa.convivenza",
        area_id="casa",
        question="Con chi vivi?",
        control="single",
        weight=0.8,
        options=[
            _o("solo", "Da solo"),
            _o("partner", "Con il partner", sets={"famiglia.partner": True}),
            _o("famiglia", "Con la famiglia", sets={"famiglia.membri": True}),
            _o("coinquilini", "Con coinquilini"),
        ],
    ),
    GuidedObjective(
        id="casa.mutuo",
        area_id="casa",
        question="Hai un mutuo attivo su questa casa?",
        control="yes_no",
        weight=0.85,
        allow_decline=True,
        depends_on=[Condition(key="casa.situazione", equals=("proprieta",))],
        options=[
            _o("si", "Sì", sets={"casa.mutuo": True}),
            _o("no", "No", sets={"casa.mutuo": False},
               not_applicable=("casa.mutuo_rata",)),
        ],
    ),
    GuidedObjective(
        id="casa.mutuo_rata",
        area_id="casa",
        question="Quanto paghi circa al mese di mutuo?",
        hint="Un valore indicativo va benissimo.",
        control="currency",
        unit="€/mese",
        weight=0.7,
        allow_other=False,
        allow_decline=True,
        depends_on=[Condition(key="casa.mutuo", equals=("true", "si", "sì"))],
    ),
    GuidedObjective(
        id="casa.affitto_canone",
        area_id="casa",
        question="Quanto paghi di affitto al mese?",
        control="currency",
        unit="€/mese",
        weight=0.7,
        allow_other=False,
        allow_decline=True,
        depends_on=[Condition(key="casa.situazione", equals=("affitto",))],
    ),
    GuidedObjective(
        id="casa.spazio_auto",
        area_id="casa",
        question="Hai uno spazio per l'auto?",
        control="single",
        weight=0.5,
        options=[
            _o("garage", "Garage"),
            _o("posto_auto", "Posto auto"),
            _o("entrambi", "Entrambi"),
            _o("nessuno", "Nessuno"),
        ],
    ),
    GuidedObjective(
        id="casa.utenze",
        area_id="casa",
        question="Come gestisci luce e gas?",
        control="single",
        weight=0.75,
        # Every option has to say what it means on its own. "Utenze intestate
        # a…" cut off mid-phrase told a person nothing, and a setup that needs
        # a tooltip to be understood is a form.
        options=[
            _o("mie", "Sono intestate a me"),
            _o("altra_persona", "Sono intestate a un'altra persona"),
            _o("inclusi", "Sono incluse nel canone o nel condominio",
               not_applicable=("servizi.fornitori",)),
            _o("non_so", "Non lo so con certezza"),
        ],
    ),
    GuidedObjective(
        id="doc.bolletta",
        area_id="casa",
        question="Vuoi aggiungere una bolletta?",
        hint=(
            "ORA ne ricava fornitore, offerta, consumi e scadenza senza farti "
            "scrivere nulla. Puoi anche farlo più tardi."
        ),
        control="document_upload",
        document_type="bolletta",
        weight=0.6,
        allow_other=False,
        depends_on=[Condition(key="casa.utenze", equals=("mie", "altra_persona"))],
    ),
    GuidedObjective(
        id="casa.assicurazione",
        area_id="casa",
        question="Hai una polizza sulla casa?",
        control="yes_no",
        weight=0.6,
        depends_on=[Condition(key="casa.situazione", equals=("proprieta", "affitto"))],
        options=[
            _o("si", "Sì", sets={"casa.assicurazione": True}),
            _o("no", "No", sets={"casa.assicurazione": False}),
        ],
    ),
]

# ---------------------------------------------------------------------------
# Lavoro — the branch that has to close cleanly
# ---------------------------------------------------------------------------

_WORK_DEPENDENTS = (
    "lavoro.tipo",
    "lavoro.contratto",
    "lavoro.orario",
    "lavoro.ruolo",
    "lavoro.modalita",
    "lavoro.reddito",
    "doc.contratto_lavoro",
)

_LAVORO: List[GuidedObjective] = [
    GuidedObjective(
        id="lavoro.active",
        area_id="lavoro",
        question="Attualmente lavori?",
        control="yes_no",
        weight=1.0,
        allow_other=False,
        options=[
            _o("si", "Sì", sets={"lavoro.active": True}),
            _o("no", "No", sets={"lavoro.active": False},
               not_applicable=_WORK_DEPENDENTS),
        ],
    ),
    GuidedObjective(
        id="lavoro.tipo",
        area_id="lavoro",
        question="Quale situazione ti descrive meglio?",
        control="single",
        weight=0.9,
        depends_on=[Condition(key="lavoro.active", equals=("true", "si", "sì"))],
        options=[
            _o("dipendente_pubblico", "Dipendente pubblico"),
            _o("dipendente_privato", "Dipendente privato"),
            _o("autonomo", "Autonomo / professionista"),
            _o("imprenditore", "Imprenditore"),
            _o("collaborazione", "Collaborazione / occasionale"),
        ],
    ),
    GuidedObjective(
        id="lavoro.contratto",
        area_id="lavoro",
        question="Che tipo di rapporto hai?",
        control="single",
        weight=0.7,
        depends_on=[
            Condition(key="lavoro.tipo", equals=("dipendente_pubblico", "dipendente_privato"))
        ],
        options=[
            _o("indeterminato", "Tempo indeterminato"),
            _o("determinato", "Tempo determinato"),
            _o("apprendistato", "Apprendistato"),
        ],
    ),
    GuidedObjective(
        id="lavoro.orario",
        area_id="lavoro",
        question="Full-time o part-time?",
        control="single",
        weight=0.5,
        depends_on=[Condition(key="lavoro.active", equals=("true", "si", "sì"))],
        options=[_o("full_time", "Full-time"), _o("part_time", "Part-time")],
    ),
    GuidedObjective(
        id="lavoro.modalita",
        area_id="lavoro",
        question="Come lavori di solito?",
        control="single",
        weight=0.6,
        depends_on=[Condition(key="lavoro.active", equals=("true", "si", "sì"))],
        options=[
            _o("sede", "In sede"),
            _o("ibrido", "Ibrido"),
            _o("remoto", "Da remoto"),
            _o("in_giro", "In giro / presso clienti"),
        ],
    ),
    GuidedObjective(
        id="lavoro.ruolo",
        area_id="lavoro",
        question="Di cosa ti occupi?",
        hint="Anche solo il settore: serve per capire il contesto, non per profilarti.",
        control="text",
        weight=0.7,
        allow_decline=True,
        depends_on=[Condition(key="lavoro.active", equals=("true", "si", "sì"))],
    ),
]

# ---------------------------------------------------------------------------
# Studio — its own area, its own "no"
# ---------------------------------------------------------------------------

# Everything that only exists if somebody is studying — the guided questions
# and the older catalogue's entries alike. A "no" has to close all of it, or
# the area sits at a permanent half-finished number for a person who has
# nothing to tell it.
_STUDY_DEPENDENTS = (
    "studio.tipo",
    "studio.ambito",
    "studio.fase",
    "studio.universita",
    "studio.esame",
    "doc.piano_di_studi",
)

_STUDIO: List[GuidedObjective] = [
    GuidedObjective(
        id="studio.active",
        area_id="studio",
        question="Attualmente studi?",
        control="yes_no",
        weight=1.0,
        allow_other=False,
        options=[
            _o("si", "Sì", sets={"studio.active": True}),
            _o("no", "No", sets={"studio.active": False},
               not_applicable=_STUDY_DEPENDENTS),
        ],
    ),
    GuidedObjective(
        id="studio.tipo",
        area_id="studio",
        question="Che percorso stai seguendo?",
        control="single",
        weight=0.8,
        depends_on=[Condition(key="studio.active", equals=("true", "si", "sì"))],
        options=[
            _o("universita", "Università", sets={"studio.universita": True}),
            _o("scuola", "Scuola superiore"),
            _o("master", "Master / specializzazione"),
            _o("corso", "Corso o certificazione"),
        ],
    ),
    GuidedObjective(
        id="studio.ambito",
        area_id="studio",
        question="In che ambito?",
        control="text",
        weight=0.6,
        depends_on=[Condition(key="studio.active", equals=("true", "si", "sì"))],
    ),
    GuidedObjective(
        id="studio.fase",
        area_id="studio",
        question="A che punto sei?",
        control="single",
        weight=0.5,
        depends_on=[Condition(key="studio.active", equals=("true", "si", "sì"))],
        options=[
            _o("inizio", "All'inizio"),
            _o("meta", "A metà percorso"),
            _o("fine", "Verso la fine"),
            _o("tesi", "Tesi / esame finale"),
        ],
    ),
]

# ---------------------------------------------------------------------------
# Mobilità
# ---------------------------------------------------------------------------

_CAR_DEPENDENTS = (
    "auto.rapporto",
    "auto.rata",
    "auto.assicurazione_scadenza",
    "doc.libretto",
    "auto.alimentazione",
)

_MOBILITA: List[GuidedObjective] = [
    GuidedObjective(
        id="mobilita.mezzi",
        area_id="mobilita",
        question="Come ti sposti abitualmente?",
        hint="Puoi selezionare più opzioni.",
        control="multi",
        weight=1.0,
        options=[
            _o("auto", "Auto", sets={"auto.owned": True}),
            _o("moto", "Moto o scooter"),
            _o("pubblico", "Trasporto pubblico"),
            _o("bici", "Bicicletta"),
            _o("piedi", "A piedi"),
            _o("nessuno", "Nessuno di questi",
               not_applicable=_CAR_DEPENDENTS + ("auto.owned",)),
        ],
    ),
    GuidedObjective(
        id="auto.rapporto",
        area_id="mobilita",
        question="Che rapporto hai con l'auto?",
        control="single",
        weight=0.8,
        depends_on=[Condition(key="mobilita.mezzi", equals=("auto",))],
        options=[
            _o("proprieta", "Di proprietà"),
            _o("leasing", "Leasing"),
            _o("noleggio", "Noleggio a lungo termine"),
            _o("aziendale", "Aziendale"),
            _o("familiare", "Di un familiare"),
        ],
    ),
    GuidedObjective(
        id="auto.rata",
        area_id="mobilita",
        question="Quanto paghi al mese per l'auto?",
        control="currency",
        unit="€/mese",
        weight=0.5,
        allow_other=False,
        allow_decline=True,
        depends_on=[Condition(key="auto.rapporto", equals=("leasing", "noleggio"))],
    ),
    GuidedObjective(
        id="doc.libretto",
        area_id="mobilita",
        question="Vuoi aggiungere il libretto?",
        hint="ORA ne ricava targa, alimentazione e scadenze. Puoi farlo più tardi.",
        control="document_upload",
        document_type="libretto",
        weight=0.6,
        allow_other=False,
        depends_on=[Condition(key="auto.rapporto", equals=("proprieta", "leasing", "noleggio"))],
    ),
    GuidedObjective(
        id="auto.assicurazione_scadenza",
        area_id="mobilita",
        question="Quando scade l'assicurazione dell'auto?",
        control="date",
        weight=0.6,
        allow_other=False,
        allow_decline=True,
        depends_on=[Condition(key="auto.rapporto", equals=("proprieta", "leasing", "noleggio"))],
    ),
]

# ---------------------------------------------------------------------------
# Famiglia, Patrimonio, Finanze, Assicurazioni, Servizi, Salute
# ---------------------------------------------------------------------------

_FAMIGLIA: List[GuidedObjective] = [
    GuidedObjective(
        id="famiglia.situazione",
        area_id="famiglia",
        question="Chi c'è nella tua vita di tutti i giorni?",
        hint="Serve solo per tenerne conto. Puoi selezionare più opzioni.",
        control="multi",
        weight=1.0,
        options=[
            _o("partner", "Un partner", sets={"famiglia.partner": True}),
            _o("figli", "Figli", sets={"famiglia.figli": True}),
            _o("genitori", "Genitori di cui ti occupi"),
            _o("altri", "Altri familiari vicini"),
            _o("nessuno", "Preferisco non indicarlo", declines=True),
        ],
    ),
    GuidedObjective(
        id="famiglia.figli_numero",
        area_id="famiglia",
        question="Quanti figli?",
        control="number",
        weight=0.5,
        allow_other=False,
        depends_on=[Condition(key="famiglia.situazione", equals=("figli",))],
    ),
]

_PATRIMONIO: List[GuidedObjective] = [
    GuidedObjective(
        id="patrimonio.beni",
        area_id="patrimonio",
        question="Possiedi altri beni importanti di cui ORA dovrebbe tenere conto?",
        control="multi",
        weight=1.0,
        sensitivity="sensitive",
        options=[
            _o("immobili", "Altri immobili", sets={"patrimonio.immobili_altri": True}),
            _o("terreni", "Terreni"),
            _o("attivita", "Attività o quote societarie"),
            _o("altri", "Altri beni rilevanti"),
            _o("nessuno", "Nessuno",
               not_applicable=(
                   "patrimonio.immobili_dettaglio",
                   "patrimonio.immobili_altri",
               )),
        ],
    ),
    GuidedObjective(
        id="patrimonio.immobili_dettaglio",
        area_id="patrimonio",
        question="Gli altri immobili sono affittati o a tua disposizione?",
        control="single",
        weight=0.6,
        sensitivity="sensitive",
        depends_on=[Condition(key="patrimonio.beni", equals=("immobili",))],
        options=[
            _o("affittati", "Affittati"),
            _o("disposizione", "A disposizione"),
            _o("misto", "Sia l'uno che l'altro"),
        ],
    ),
    GuidedObjective(
        id="patrimonio.finanziamenti",
        area_id="patrimonio",
        question="Hai finanziamenti o prestiti in corso, oltre all'eventuale mutuo?",
        control="yes_no",
        weight=0.7,
        sensitivity="sensitive",
        allow_decline=True,
        options=[
            _o("si", "Sì", sets={"patrimonio.finanziamenti": True}),
            _o("no", "No", sets={"patrimonio.finanziamenti": False}),
        ],
    ),
]

_FINANZE: List[GuidedObjective] = [
    GuidedObjective(
        id="finanze.reddito",
        area_id="finanze",
        question="Quanto è circa il tuo reddito netto mensile?",
        hint="Facoltativo. Serve solo a rendere realistici i consigli economici.",
        control="single",
        weight=0.9,
        sensitivity="sensitive",
        allow_decline=True,
        options=[
            _o("lt1000", "Meno di 1.000 €"),
            _o("1000_1500", "1.000 – 1.500 €"),
            _o("1500_2000", "1.500 – 2.000 €"),
            _o("2000_3000", "2.000 – 3.000 €"),
            _o("gt3000", "Più di 3.000 €"),
        ],
    ),
    GuidedObjective(
        id="finanze.spese_ricorrenti",
        area_id="finanze",
        question="Quanto pesano più o meno le spese fisse ogni mese?",
        control="single",
        weight=0.7,
        sensitivity="sensitive",
        allow_decline=True,
        options=[
            _o("poche", "Poche, sotto il 30% delle entrate"),
            _o("medie", "Circa la metà"),
            _o("molte", "La maggior parte"),
            _o("non_so", "Non lo so con precisione"),
        ],
    ),
    GuidedObjective(
        id="patrimonio.risparmi",
        area_id="finanze",
        question="Hai risparmi o investimenti da tenere in conto?",
        control="single",
        weight=0.6,
        sensitivity="sensitive",
        allow_decline=True,
        options=[
            _o("liquidita", "Soprattutto liquidità"),
            _o("investimenti", "Investimenti"),
            _o("entrambi", "Entrambi"),
            _o("nessuno", "Non per ora"),
        ],
    ),
]

_ASSICURAZIONI: List[GuidedObjective] = [
    GuidedObjective(
        id="assicurazioni.tipo",
        area_id="assicurazioni",
        question="Hai assicurazioni attive?",
        hint="Puoi selezionare più opzioni.",
        control="multi",
        weight=1.0,
        options=[
            _o("auto", "Auto"),
            _o("casa", "Casa"),
            _o("vita", "Vita"),
            _o("infortuni", "Infortuni"),
            _o("salute", "Salute"),
            _o("professionale", "Professionale"),
            _o("nessuna", "Nessuna", not_applicable=("doc.polizza",)),
        ],
    ),
    GuidedObjective(
        id="doc.polizza",
        area_id="assicurazioni",
        question="Vuoi aggiungere una polizza?",
        hint="ORA ne ricava compagnia, copertura e scadenza. Puoi farlo più tardi.",
        control="document_upload",
        document_type="polizza",
        weight=0.6,
        allow_other=False,
        depends_on=[Condition(key="assicurazioni.tipo", equals=("auto", "casa", "vita", "infortuni", "salute", "professionale"))],
    ),
]

_SERVIZI: List[GuidedObjective] = [
    GuidedObjective(
        id="servizi.fornitori",
        area_id="servizi",
        question="Quali servizi ricorrenti paghi?",
        hint="Puoi selezionare più opzioni.",
        control="multi",
        weight=1.0,
        options=[
            _o("luce", "Luce"),
            _o("gas", "Gas"),
            _o("internet", "Internet"),
            _o("telefono", "Telefono"),
            _o("abbonamenti", "Abbonamenti digitali", sets={"abbonamenti.list": True}),
            _o("nessuno", "Nessuno di questi"),
        ],
    ),
]

_SALUTE: List[GuidedObjective] = [
    GuidedObjective(
        id="salute.obiettivi",
        area_id="salute",
        question="C'è qualcosa che vorresti curare di più?",
        hint="Facoltativo, e senza entrare nel merito medico.",
        control="multi",
        weight=0.8,
        sensitivity="sensitive",
        allow_decline=True,
        options=[
            _o("movimento", "Muovermi di più"),
            _o("sonno", "Dormire meglio"),
            _o("alimentazione", "Mangiare meglio"),
            _o("stress", "Gestire lo stress"),
            _o("controlli", "Stare dietro ai controlli"),
            _o("nulla", "Niente in particolare"),
        ],
    ),
]

GUIDED_OBJECTIVES: Tuple[GuidedObjective, ...] = tuple(
    _CASA + _LAVORO + _STUDIO + _MOBILITA + _FAMIGLIA
    + _PATRIMONIO + _FINANZE + _ASSICURAZIONI + _SERVIZI + _SALUTE
)

# The identity step is looked up like any other objective, but it belongs to no
# area, so it never appears in `for_area` and never shows up in a path.
_BY_ID: Dict[str, GuidedObjective] = {o.id: o for o in GUIDED_OBJECTIVES}
_BY_ID[IDENTITY_OBJECTIVE.id] = IDENTITY_OBJECTIVE


def objective(objective_id: str) -> Optional[GuidedObjective]:
    return _BY_ID.get((objective_id or "").strip())


def for_area(area_id: str) -> List[GuidedObjective]:
    return [o for o in GUIDED_OBJECTIVES if o.area_id == area_id]


def option_of(objective_id: str, option_id: str) -> Optional[Option]:
    obj = objective(objective_id)
    if not obj:
        return None
    for opt in obj.options:
        if opt.id == option_id:
            return opt
    return None
