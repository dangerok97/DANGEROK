"""
Cosa significa, per questa vita, una cosa che riguarda i soldi.

    IL CODICE ORCHESTRA. L'AI RAGIONA.
    L'IMPORTO NON DECIDE L'IMPORTANZA.

Non c'e' nessuna soglia in questo file, e non deve entrarci. `if amount > 500`
sarebbe una risposta permanente a una domanda che dipende interamente da chi
e' la persona: cinquanta euro sono niente per qualcuno e una settimana per
qualcun altro. Il codice qui raccoglie i fatti, li mette davanti al modello e
scrive quello che torna; l'importanza, il significato e l'urgenza sono
giudizi e restano dall'altra parte.

Due domande, tenute separate perche' sono due.

**Cosa e' questo.** Un'email o un documento sono arrivati; c'e' dentro un
fatto economico? Di che tipo? Con quali numeri, e cosa non si sa? La risposta
puo' benissimo essere «niente»: una newsletter sui prestiti e' rumore, e il
fatto che nomini dei soldi non la rende un impegno.

**Cosa comporta.** Dato un fatto e quello che si sa di questa vita, pesa
qualcosa? Su cosa? E cosa manca per poterlo dire? `uncertain` con
`missing_information` e' una risposta buona quanto le altre, e molto meglio
di un `relevant` tirato a indovinare.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from research.reasoning import _ask_model

logger = logging.getLogger("ora.financial.reasoning")

_DISCIPLINE = (
    "You are reading something that reached a person — a message, a document — "
    "and deciding whether it says anything about their money, and what that "
    "would mean for their life.\n\n"
    "You are not an accountant and this is not a budgeting app. Most things "
    "that mention money mean nothing that needs anybody: an advertisement for "
    "loans, a receipt for something already paid and closed, a price that "
    "moved by an amount nobody would notice. Saying so is the correct answer "
    "and the common one.\n\n"
    "Never invent a number. If an amount, a date or a frequency is not "
    "actually stated, say it is unknown — an unknown amount is a fact, a "
    "guessed one is a lie that will be added to other numbers.\n\n"
    "Never decide that something matters because it is large, or that it does "
    "not because it is small. What a sum means depends on whose life it is.\n\n"
    "Write about the person's life, never about data, providers or records. "
    "Answer with JSON only. No markdown fences."
)

# Cosa puo' essere. Le stesse parole del modello dei fatti, piu' «nothing»,
# che e' la risposta ordinaria.
WHAT_IT_IS = ("nothing", "commitment", "income", "event", "constraint")

# Quanto pesa. `uncertain` non e' un fallimento: e' la risposta onesta quando
# manca qualcosa di decisivo.
IMPACT_LEVELS = ("negligible", "relevant", "material", "uncertain")


async def read_financial_meaning(
    observation: Dict[str, Any],
    *,
    life: Dict[str, Any],
    already_known: List[Dict[str, Any]],
    language: str = "it",
) -> Optional[Dict[str, Any]]:
    """
    C'e' un fatto economico qui dentro? Quale?

    Torna `None` quando non c'e' una risposta utilizzabile — provider giu',
    JSON malformato, una parola fuori vocabolario. `None` significa «non lo
    so», e chi chiama deve lasciare le cose come stanno: il silenzio qui e'
    una risposta mancante, non una risposta di «niente».
    """
    instruction = (
        "Something reached this person. Decide whether it says anything about "
        "their money.\n\n"
        "You are shown what was observed and what is already known about "
        "their finances. Compare: a message about a cost they already have is "
        "a change to that cost, not a second one.\n\n"
        "Your choices for what this is:\n"
        "- `nothing` — it says nothing about their money that anybody needs. "
        "The ordinary answer.\n"
        "- `commitment` — money they will owe: rent, an instalment, a bill, "
        "a policy, a subscription, a tax.\n"
        "- `income` — money coming to them.\n"
        "- `event` — something that already happened: a receipt, a payment "
        "made, an invoice that arrived.\n"
        "- `constraint` — a limit or a budget they have stated.\n\n"
        "For amounts, dates and frequency: give them only when they are "
        "actually stated. Everything you cannot read, name in "
        "`what_is_not_known` — that list is more useful than a guess.\n\n"
        "Name the thing, not the news about it. `in_their_words` is what the "
        "person calls the thing itself — «affitto», «bolletta della luce» — "
        "never the event that reached them: «aumento affitto» is not "
        "something anybody pays, it is a message about something they pay.\n\n"
        "If this is about something they already have — the rent goes up, the "
        "subscription renews at a new price — then use for `in_their_words` "
        "the *same* name that known thing already has in what you were shown, "
        "and copy that name again, exactly, into `changes_what`. Getting this "
        "wrong leaves the person with two rents.\n\n"
        "Return JSON: {\"what_it_is\": \"nothing|commitment|income|event|"
        "constraint\", "
        "\"in_their_words\": \"how they would name this, a few words\", "
        "\"amount\": null or number, \"currency\": null or \"EUR\", "
        "\"direction\": \"incoming|outgoing|neutral\", "
        "\"how_often\": \"one_time|recurring|unknown\", "
        "\"recurrence\": null or \"ogni mese\", "
        "\"due_at\": null or ISO date, \"occurred_at\": null or ISO date, "
        "\"counterparty\": null or a name actually written there, "
        "\"valid_from\": null or ISO date when a new price starts, "
        "\"changes_what\": \"\" or the name of the known thing this replaces, "
        "\"what_is_not_known\": [\"...\"], "
        "\"reasoning\": \"one short sentence, never shown to them\"}\n\n"
        "Write anything a person reads in their language."
    )

    data = await _ask_model(
        _DISCIPLINE + "\n\n" + instruction,
        _dump({
            "what_arrived": observation,
            "what_we_know_about_them": life,
            "what_we_already_know_about_their_money": already_known,
        }),
    )
    if not isinstance(data, dict):
        return None
    what = str(data.get("what_it_is") or "").strip()
    if what not in WHAT_IT_IS:
        return None
    data["what_it_is"] = what
    # Un importo che il modello non ha trovato resta assente. Questa riga
    # esiste perche' `0` e `""` sono i due modi in cui un «non lo so» diventa
    # un numero senza che nessuno lo decida.
    if data.get("amount") in ("", 0, "0"):
        data["amount"] = None if data.get("amount") != 0 else data.get("amount")
    return data


async def weigh_against_their_life(
    fact: Dict[str, Any],
    *,
    life: Dict[str, Any],
    goals: List[Dict[str, Any]],
    situations: List[Dict[str, Any]],
    language: str = "it",
) -> Optional[Dict[str, Any]]:
    """
    Quanto pesa questo, e su cosa. Il giudizio, non una soglia.
    """
    instruction = (
        "Here is something known about this person's money, and what is going "
        "on in their life. How much does it weigh, and on what?\n\n"
        "Do not answer from the size of the number. A small recurring increase "
        "can matter to somebody saving for a deposit and mean nothing to "
        "somebody else; a large one-off can be already planned for. What "
        "decides is what else is true about them.\n\n"
        "If something decisive is missing — you do not know their income, "
        "their balance, whether this is already accounted for — answer "
        "`uncertain` and say what is missing. That is a real answer. A "
        "confident one built on a guess is not.\n\n"
        "Name the goals or situations this touches only when it genuinely "
        "does. Most money facts touch nothing in particular.\n\n"
        "Return JSON: {\"level\": \"negligible|relevant|material|uncertain\", "
        "\"reason\": \"one sentence about their life\", "
        "\"affected_goal_ids\": [], \"affected_situation_ids\": [], "
        "\"missing_information\": [\"...\"]}\n\n"
        "Write anything a person reads in their language."
    )

    data = await _ask_model(
        _DISCIPLINE + "\n\n" + instruction,
        _dump({
            "the_money_fact": fact,
            "what_we_know_about_them": life,
            "what_they_are_trying_to_do": goals,
            "what_is_going_on": situations,
        }),
    )
    if not isinstance(data, dict):
        return None
    level = str(data.get("level") or "").strip()
    if level not in IMPACT_LEVELS:
        return None
    data["level"] = level
    return data


async def answer_with_what_is_known(
    question: str,
    *,
    horizon: Dict[str, Any],
    life: Dict[str, Any],
    language: str = "it",
) -> Optional[Dict[str, Any]]:
    """
    Rispondi a una domanda sui soldi con quello che si sa, e dì cosa manca.

        MEGLIO «NON LO SO, MI MANCA QUESTO» CHE UN NUMERO SBAGLIATO.

    E' la funzione che deve rendere impossibile la frase «ti rimarranno 995
    euro» quando il saldo non lo sa nessuno.
    """
    instruction = (
        "This person asked something about their money. Answer with what is "
        "actually known, and be explicit about what is not.\n\n"
        "You are shown the commitments and the incoming money that are known "
        "for the period, and a list of what is not known. If that list "
        "contains anything that the question depends on — their balance, "
        "their income, whether these are all the movements — then you cannot "
        "give a number as an answer, and you must not. Say what you do know, "
        "then say plainly what would be needed to answer properly.\n\n"
        "Never present a subtraction of the known items as what will be left. "
        "Known movements are not a balance.\n\n"
        # Le tre distinzioni che una risposta sui soldi non puo' sbagliare, e
        # che nessuna quantita' di prudenza generica produce da sola.
        "Three distinctions you must not collapse.\n\n"
        "FIRST, the source. If `la_banca.posso_leggere_adesso` is false, the "
        "account is no longer connected: you do not know the current balance, "
        "you cannot read new movements, and you must not imply that you will "
        "look. You may say what the balance was the last time you could read "
        "it, and that you cannot confirm it is still so. If it is true, an "
        "amount you were given is still a reading with a time on it — say "
        "when you read it rather than stating it as a timeless fact.\n\n"
        "SECOND, shape. Recurring means only that something repeats. A single "
        "payment is not a recurring expense however large it is, and a small "
        "regular charge is a pattern however small it is. Anything marked "
        "`identificato: false` has no name: describe it the way the bank "
        "wrote it and say you have not worked out what it is. Do not invent a "
        "category for it.\n\n"
        "THIRD, the monthly figure. `questo_mese.differenza_parziale` is the "
        "sum of the movements you have read, not what is left and not a "
        "balance. If you use it, name it for what it is, and name the item "
        "that weighs most, which is what explains it.\n\n"
        "Return JSON: {\"answer\": \"what you can honestly say, in their "
        "language\", \"can_answer_with_a_number\": false, "
        "\"what_i_know\": [\"...\"], \"what_i_would_need\": [\"...\"]}\n\n"
        "Write in their language."
    )

    data = await _ask_model(
        _DISCIPLINE + "\n\n" + instruction,
        _dump({
            "they_asked": question,
            "what_is_known_for_the_period": horizon,
            "what_we_know_about_them": life,
        }),
    )
    if not isinstance(data, dict):
        return None
    return data


def _dump(payload: Dict[str, Any]) -> str:
    try:
        return json.dumps(payload, ensure_ascii=False, default=str)[:12000]
    except Exception:
        return "{}"


# Cosa un movimento puo' sembrare. Le stesse parole del modello dei fatti,
# piu' `unclear`, che e' una risposta e non una rinuncia.
INTERPRETED_KINDS = ("commitment", "income", "event", "unclear", "noise")

# In che punto della sua storia sta. Il codice conta le volte; questa parola
# la sceglie il giudizio.
PATTERN_STATUS = (
    "one_off", "recurring", "new_recurrence", "ended_recurrence",
    "amount_changed", "unusual", "past_receipt", "unrecognised", "unclear",
)

CERTAINTY = ("high", "medium", "low")


async def read_a_movement(
    observation: Dict[str, Any],
    *,
    pattern: Dict[str, Any],
    life: Dict[str, Any],
    already_known: List[Dict[str, Any]],
    nearby_evidence: List[Dict[str, Any]],
    situations: List[Dict[str, Any]],
    goals: List[Dict[str, Any]],
    language: str = "it",
) -> Optional[Dict[str, Any]]:
    """
    Cosa sembra questo movimento, guardando tutto quello che c'e' intorno.

        UNA TRANSAZIONE E' UN'OSSERVAZIONE. IL SIGNIFICATO VIENE DOPO.

    Il codice ha contato — quante volte, ogni quanto, quanto e' cambiato — e
    ha raccolto quello che c'e' vicino: email, documenti, cosa si sa gia' di
    questa vita. Da qui in poi e' tutto giudizio, e la risposta piu' utile e'
    spesso «un addebito ricorrente che non ho ancora capito cosa sia».

    `-760 € · BONIFICO A ROSSI MARCO` non e' un affitto. Puo' diventarlo se
    c'e' un'email che dice che il canone e' 760, se il modello della vita sa
    che questa persona affitta, se succede ogni mese verso la stessa persona.
    E' l'insieme a dirlo, non la stringa.
    """
    instruction = (
        "A movement appeared on this person's account. Say what it looks "
        "like, and how sure you are.\n\n"
        "You are given the line as the bank wrote it, arithmetic about "
        "similar lines seen before, what is already known about this "
        "person's money, what else was observed around the same time — "
        "messages, documents — and what is going on in their life.\n\n"
        "The description alone decides nothing. A line saying «ENERGIA "
        "ITALIA» may be an electricity bill, a refund from one, or a payment "
        "somebody made on their behalf. A transfer to a person's name may be "
        "rent, a loan repaid, or a birthday present. What settles it is "
        "everything together — and when nothing settles it, `unclear` with "
        "an empty `likely_label` is the right answer. «A recurring charge I "
        "have not identified» is useful to a person. A confident wrong "
        "category is not.\n\n"
        "The arithmetic you are shown is counting, not meaning: six times "
        "thirty days apart is a fact, «it is a subscription» is your call, "
        "and a fortnightly grocery run and a monthly rent look alike in "
        "those numbers.\n\n"
        "In particular: a small regular amount is not a subscription. It can "
        "be an insurance premium, a union fee, a standing order somebody set "
        "up on their card. If the only things you have are the amount and "
        "its regularity, you do not know what it is, and `unclear` is the "
        "answer. Naming it «monthly subscription» is a guess wearing the "
        "clothes of a fact, and the person will read it as one.\n\n"
        "`should_persist` means this is worth ORA remembering. Two things "
        "qualify. One: something standing — a rent, a salary, a "
        "subscription. Two: a one-off that belongs to something they are "
        "actually doing — the notary for the house they are buying, the "
        "deposit for the trip they are planning. That second case matters as "
        "much as the first: it is the cost of a thing in their life, and "
        "forgetting it leaves them planning without it.\n\n"
        "What does not qualify is a one-off that belongs to nothing: a "
        "supermarket run, a coffee, a jacket. Those happened; they are not "
        "something to know about somebody.\n\n"
        "`should_ask_user` means a "
        "short question would settle something you cannot settle alone; use "
        "it sparingly, and never for something that does not matter.\n\n"
        "Link a situation or a goal only when the evidence points there. "
        "Most movements belong to nothing in particular.\n\n"
        "Return JSON: {"
        "\"interpreted_kind\": \"commitment|income|event|unclear|noise\", "
        "\"likely_label\": \"what they would call it, or empty if unsure\", "
        "\"recurring_likelihood\": \"high|medium|low\", "
        "\"pattern_status\": \"one_off|recurring|new_recurrence|"
        "ended_recurrence|amount_changed|unusual|past_receipt|unrecognised|"
        "unclear\", "
        "\"linked_situations\": [], \"linked_goals\": [], "
        "\"certainty\": \"high|medium|low\", "
        "\"missing_information\": [\"...\"], "
        "\"evidence_refs\": [\"...\"], "
        "\"should_persist\": false, \"should_ask_user\": false, "
        "\"reason\": \"one short sentence about their life\"}\n\n"
        "Write anything a person reads in their language."
    )

    data = await _ask_model(
        _DISCIPLINE + "\n\n" + instruction,
        _dump({
            "the_movement": observation,
            "arithmetic_on_similar_movements": pattern,
            "what_we_already_know_about_their_money": already_known,
            "what_else_was_observed_around_it": nearby_evidence,
            "what_we_know_about_them": life,
            "what_is_going_on_in_their_life": situations,
            "what_they_are_trying_to_do": goals,
        }),
    )
    if not isinstance(data, dict):
        return None

    kind = str(data.get("interpreted_kind") or "").strip()
    status = str(data.get("pattern_status") or "").strip()
    certainty = str(data.get("certainty") or "").strip()
    if kind not in INTERPRETED_KINDS:
        return None
    if status not in PATTERN_STATUS:
        status = "unclear"
    if certainty not in CERTAINTY:
        certainty = "low"

    data["interpreted_kind"] = kind
    data["pattern_status"] = status
    data["certainty"] = certainty
    # Un'etichetta senza certezza non e' un'etichetta: e' una supposizione con
    # l'aria di un fatto. Se il giudizio dice di non avere capito, il nome che
    # ha proposto non viaggia.
    if kind == "unclear":
        data["likely_label"] = ""
    return data
