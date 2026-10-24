"""
The capabilities that actually do something, and what they are honest about.

    AUTONOMOUS WORK MUST BE REAL WORK.
    A TOOL RESULT IS NOT A LIFE FACT.

Sprint 1 stood in for every capability, which was the right shape and the
wrong substance: an agent whose work is all stubs will happily report that a
goal is achieved, because everything it tried came back succeeded. This file
is where that stops being true — each function here reaches something that
already exists in ORA and returns what it actually found, or says plainly
that there was nothing behind the door.

Three rules hold for all of them.

Every outcome carries its **provenance**, set by the code that did the work,
because nothing downstream can reconstruct whether a provider was really
called. Every outcome carries **evidence** as claims rather than payloads: a
sentence about what was found, not the thing that was returned, because the
model needs to reason about facts and a raw dump is not a fact. And a
capability that is not connected says `requires_connection` rather than
returning an empty success — an empty success is how a system concludes that
somebody's calendar is clear when nobody ever plugged one in.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from agent.models import ResultProvenance
from agent.memory_sources import MEMORY_READ_PROJECTION, memory_source_id, memory_source_version

logger = logging.getLogger(__name__)

# How much of a life a bounded read may return. A snapshot relevant to a
# goal, never the database: a capability that hands over everything is a
# capability that put somebody's whole life in a prompt.
MAX_FACTS = 12
MAX_DOCUMENTS = 10
MAX_EVENTS = 10
MAX_CLAIMS = 8
# Weather carries current, trend, daylight and two days: twelve hours of profile
# alone is four claims, and cutting the daylight is how evening went unseen.
WEATHER_MAX_CLAIMS = 12


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Claim:
    """One thing found out, in a sentence. Never a payload."""

    text: str
    supports: str = ""
    # Optional numeric readings behind the sentence (e.g. temperature_c) for
    # display only. Never sent to a model; the sentence stays the evidence.
    measures: Dict[str, float] = field(default_factory=dict)


@dataclass
class CapabilityOutcome:
    """
    What a capability did, with where it came from attached.

    `status` distinguishes the ways of not succeeding that mean different
    things to a planner: nothing there (`unavailable`), nothing connected
    (`requires_connection` as the error type), it broke and might not next
    time (`failed` and retryable), and it worked but only partly (`partial`).
    """

    status: str  # succeeded | partial | unavailable | failed | waiting
    observation: str
    provenance: ResultProvenance
    claims: List[Claim] = field(default_factory=list)
    data_ref: str = ""
    error_type: str = ""
    retryable: bool = False


def _unavailable(capability: str, reason: str, note: str) -> CapabilityOutcome:
    return CapabilityOutcome(
        status="unavailable",
        observation=note,
        provenance=ResultProvenance(
            source_class="internal_observation", capability=capability
        ),
        error_type=reason,
        retryable=False,
    )


# --- what ORA already holds -------------------------------------------------

def _memory_ids(refs) -> List[str]:
    """Resolve recorded Memory handles only; never infer a subject from words."""
    out: List[str] = []
    for raw in refs or []:
        memory_id = memory_source_id(raw)
        if memory_id and memory_id not in out:
            out.append(memory_id)
    return out[:MAX_CLAIMS]


def _memory_reference(doc) -> str:
    memory_id = str(doc.get("id") or "").strip()
    if not memory_id or len(memory_id) > 120:
        return ""
    return memory_id if memory_id.startswith("mem_") else f"memory:{memory_id}"


def _memory_support(doc) -> str:
    parts = [f"Memoria {_memory_reference(doc) or 'senza riferimento'}"]
    # The time of this database read does not make a stored belief a present
    # observation. Keep the governed epistemic and temporal qualifications.
    for label, key in (("stato", "epistemic_status"), ("autorità", "authority")):
        value = str(doc.get(key) or (doc.get("status") if key == "epistemic_status" else "") or "").strip()
        if value:
            parts.append(f"{label}: {value[:40]}")
    temporal = doc.get("temporal_scope") or {}
    if isinstance(temporal, dict):
        for label, key in (("dal", "starts_at"), ("fino al", "ends_at")):
            if temporal.get(key):
                parts.append(f"{label}: {str(temporal[key])[:40]}")
    if doc.get("updated_at") or doc.get("created_at"):
        parts.append(f"registrata: {str(doc.get('updated_at') or doc.get('created_at'))[:40]}")
    return "; ".join(parts)[:300]


async def _read_situation_statement(db, owner_id: str, goal) -> Optional[CapabilityOutcome]:
    from situations.outcomes import situation_id, statement_text
    from situations.repository import SituationRepository

    sid = situation_id(goal) if getattr(goal, "owner_id", None) == owner_id else None
    if not sid:
        return None
    try:
        state = await SituationRepository(db).get(owner_id, sid)
    except Exception:
        return None
    if state is None or state.status not in ("active", "changed"):
        return None
    text = statement_text(state)
    return CapabilityOutcome(
        status="succeeded",
        observation="Ho riletto quello che hai dichiarato su questa situazione.",
        provenance=ResultProvenance(
            source_class="internal_observation", capability="information.read",
            provider="situation", source_refs=[f"situation:{state.id}:revision:{state.revision}"],
            freshness="fresh",
            certainty_note="Quello che la persona ha dichiarato; non è una misura dell'esito.",
        ),
        claims=[Claim(text=text, supports=(getattr(goal, "desired_outcome", "") or "")[:300])],
        data_ref=f"situation:{state.id}",
    )


async def read_internal_state(db, owner_id: str, goal, *, step=None) -> CapabilityOutcome:
    """Read cited governed memories, or explicitly bounded recent notes.

    Current governance writes ``statement``/``content``. Older notes used
    ``summary``/``fact_summary``. A read supports both, excludes superseded
    facts, and never treats an empty recent window as an exhaustive search
    through the person's profile, documents, calendar and other sources.
    """
    step_refs = list(getattr(step, "input_refs", None) or [])
    requested = _memory_ids(step_refs or getattr(goal, "source_refs", None))
    if step_refs and not requested:
        # Production 24/10: planners on a Situation goal asked to "re-read the
        # situation" through this capability and got a failure every pass.
        # The Situation itself is the person's own declaration: read that.
        statement = await _read_situation_statement(db, owner_id, goal)
        if statement is not None:
            return statement
        return _unavailable(
            "information.read", "memory_reference_required",
            "Per rileggere una memoria serve il suo riferimento già osservato.",
        )
    query = {
        "user_id": owner_id,
        "status": {"$in": ["active", "known", "likely", "ambiguous", None]},
    }
    if requested:
        query["id"] = {"$in": requested}
    facts: List[Claim] = []
    try:
        docs = await db.memories.find(
            query,
            MEMORY_READ_PROJECTION,
        ).sort([("updated_at", -1), ("created_at", -1), ("id", 1)]).limit(MAX_FACTS + 1).to_list(MAX_FACTS + 1)
    except Exception as e:
        logger.info("internal read soft-fail: %s", type(e).__name__)
        return CapabilityOutcome(
            status="failed",
            observation="Non sono riuscita a leggere quello che ho su di te.",
            provenance=ResultProvenance(
                source_class="internal_observation", capability="information.read"
            ),
            error_type="internal_read_failed",
            retryable=True,
        )

    refs: List[str] = []
    versions: dict[str, str] = {}
    observed_ids: List[str] = []
    for doc in docs[:MAX_FACTS]:
        value = next((doc.get(key) for key in ("statement", "content", "summary", "fact_summary")
                      if isinstance(doc.get(key), str) and doc[key].strip()), "")
        if value.strip():
            facts.append(Claim(text=value.strip()[:600], supports=_memory_support(doc)))
            ref = _memory_reference(doc)
            if ref:
                refs.append(ref)
                versions[ref] = memory_source_version(doc)
            observed_ids.append(str(doc.get("id") or ""))
            if len(facts) == MAX_CLAIMS:
                break

    scope = (
        "Lettura limitata alle memorie citate; non verifica da sola la loro validità attuale o le altre fonti."
        if requested else
        "Lettura limitata alle memorie recenti; non è una ricerca completa e non copre profilo, documenti o altre fonti."
    )
    provenance = ResultProvenance(
        source_class="internal_observation", capability="information.read",
        provider="life_memory", source_refs=refs, source_versions=versions,
        memory_read_scope=("empty" if not facts else
                           "versioned" if len(versions) == len(facts) else ""),
        freshness="fresh", certainty_note=scope,
    )

    if not facts:
        if requested:
            return CapabilityOutcome(
                status="unavailable", provenance=provenance,
                observation="Non trovo una memoria leggibile e ancora valida tra i riferimenti indicati.",
                error_type="memory_not_observed",
            )
        # Empty coverage is evidence about this selection, never evidence
        # that the requested information does not exist anywhere in ORA.
        empty = "Non ho trovato testo leggibile nelle memorie correnti selezionate."
        return CapabilityOutcome(
            status="succeeded",
            observation=empty, provenance=provenance,
            claims=[Claim(text=empty, supports="solo la selezione di memorie letta")],
            data_ref="internal:0",
        )

    incomplete = bool(requested and set(requested) - set(observed_ids))
    return CapabilityOutcome(
        status="partial" if incomplete else "succeeded",
        observation=(f"Ho riletto {len(facts)} memorie nella selezione. "
                     + ("Alcuni riferimenti non sono più disponibili." if incomplete else scope)),
        provenance=provenance, claims=facts,
        error_type="memory_selection_incomplete" if incomplete else "",
        data_ref=f"internal:{len(facts)}",
    )


async def read_documents(db, owner_id: str, goal, *, step=None) -> CapabilityOutcome:
    """
    What documents exist and what they are, structurally.

    Names, kinds and tags — not the contents. A step that needs what is
    inside a document should say so and be answered by a read that says so
    too; handing over extracted text by default is how a capability called
    "list the documents" ends up disclosing a payslip.
    """
    if step is not None and step.input_refs:
        from agent.document_read import read_excerpt
        return await read_excerpt(db, owner_id, step)
    try:
        docs = await db.documents.find(
            {"user_id": owner_id, "deleted": {"$ne": True}, "archived": {"$ne": True}},
            {"_id": 0, "id": 1, "filename": 1, "original_filename": 1, "display_title": 1, "mime_type": 1, "tags": 1,
             "created_at": 1, "detected_language": 1},
        ).sort("created_at", -1).to_list(MAX_DOCUMENTS)
    except Exception as e:
        logger.info("document read soft-fail: %s", type(e).__name__)
        return CapabilityOutcome(
            status="failed",
            observation="Non sono riuscita a guardare i documenti.",
            provenance=ResultProvenance(
                source_class="internal_observation", capability="document.read"
            ),
            error_type="document_read_failed",
            retryable=True,
        )

    if not docs:
        return CapabilityOutcome(
            status="succeeded",
            observation="Ho guardato l'archivio: non c'e nessun documento caricato.",
            provenance=ResultProvenance(
                source_class="internal_observation",
                capability="document.read",
                freshness="fresh",
            ),
            claims=[Claim(
                text="Non c'e nessun documento in archivio.",
                supports="cosa risulta in archivio",
            )],
            data_ref="documents:0",
        )

    claims = [
        Claim(
            text=(
                f"document:{d.get('id')}: {d.get('display_title') or d.get('original_filename') or d.get('filename') or 'senza nome'}"
                + (f" ({', '.join(d.get('tags') or [])})" if d.get("tags") else "")
            )[:400],
            supports="cosa risulta in archivio",
        )
        for d in docs
    ]
    return CapabilityOutcome(
        status="succeeded",
        observation=f"Ho guardato l'archivio: {len(docs)} documenti.",
        provenance=ResultProvenance(
            source_class="internal_observation",
            capability="document.read",
            provider="documents",
            freshness="fresh",
        ),
        claims=claims[:MAX_CLAIMS],
        data_ref=f"documents:{len(docs)}",
    )


async def read_local_calendar(db, owner_id: str, goal) -> CapabilityOutcome:
    """Read Home commitments only. This grants no access to provider calendars."""
    from home.manual_event import manual_events_between
    try:
        now = _now()
        events = await manual_events_between(db, owner_id, now, now + timedelta(days=14), limit=MAX_CLAIMS)
    except Exception:
        return _unavailable("calendar.local.read", "read_failed", "Non sono riuscita a leggere gli impegni ORA.")
    claims = [Claim(
        text=(f"Impegno ORA {event['id']}: {event['title']} — {event['starts_at']} / {event['ends_at']}; "
              f"fuso: {event['timezone']}; luogo: {event['location']}; note: {event['description']}"),
        supports=f"calendar:{event['id']}",
    ) for event in events]
    return CapabilityOutcome(
        status="succeeded",
        observation=f"Ho letto {len(events)} impegni dal calendario interno ORA nei prossimi 14 giorni. "
                    "Questa lettura non comprende calendari esterni né prova che gli altri orari siano liberi.",
        provenance=ResultProvenance(source_class="internal_observation", capability="calendar.local.read",
                                    provider="ora_local_calendar", freshness="fresh"),
        claims=claims, data_ref="calendar:local",
    )


async def read_mail_metadata(db, owner_id: str, goal) -> CapabilityOutcome:
    """Read a bounded slice of Gmail metadata already ingested by ORA.

    No body text is fetched or stored here. This capability exists so an
    autonomous mission can re-check whether a relevant conversation moved
    without turning the agent evidence store into a copy of somebody's mail.
    """
    try:
        from connectors.gmail.scopes import EMAIL_RECORD_TYPE
        from agent.connector_reads import authorized_instances, sync_provenance
        connected = await authorized_instances(db, owner_id, "mail_gmail", "mail.metadata", audit=True)
    except Exception as exc:
        logger.info("mail metadata connection check soft-fail: %s", type(exc).__name__)
        return CapabilityOutcome(
            status="failed", observation="Non riesco a verificare la connessione alla posta in questo momento.",
            provenance=ResultProvenance(source_class="internal_observation", capability="mail.metadata"),
            error_type="mail_connection_check_failed", retryable=True,
        )

    if not connected:
        return _unavailable(
            "mail.metadata",
            "requires_connection",
            "Non c'è una casella Gmail collegata con il permesso di lettura.",
        )

    try:
        rows = await db.ingestion_events.find(
            {"user_id": owner_id, "source_record_type": EMAIL_RECORD_TYPE,
             "connector_instance_id": {"$in": [row["id"] for row in connected]},
             "ingestion_status": {"$nin": ["superseded", "quarantined", "skipped"]},
             "source_status": {"$ne": "detached"}},
            {
                "_id": 0,
                "external_id": 1,
                "normalized_payload": 1,
                "ingested_at": 1,
            },
        ).sort("ingested_at", -1).limit(MAX_CLAIMS).to_list(MAX_CLAIMS)
    except Exception as exc:
        logger.info("mail metadata read soft-fail: %s", type(exc).__name__)
        return CapabilityOutcome(
            status="failed",
            observation="Non sono riuscita a rileggere le comunicazioni sincronizzate.",
            provenance=ResultProvenance(
                source_class="connected_provider",
                capability="mail.metadata",
                provider="gmail_sync",
            ),
            error_type="mail_metadata_read_failed",
            retryable=True,
        )

    claims: List[Claim] = []
    source_refs: List[str] = []
    from ingestion.reading import plain

    for row in rows[:MAX_CLAIMS]:
        payload = plain(row.get("normalized_payload"))
        message_ref = str(payload.get("message_ref") or row.get("external_id") or "")
        if message_ref:
            source_refs.append(f"mail:{message_ref}")
        subject = str(payload.get("subject") or "").strip()[:180] or "senza oggetto"
        relation = str(payload.get("sender_relationship") or "unknown")
        received = str(payload.get("received_at") or "")
        attachment_note = ""
        if payload.get("attachments_present"):
            attachment_note = f"; allegati: {int(payload.get('attachment_count') or 1)}"
        claims.append(Claim(
            text=(
                f"mail:{message_ref}: «{subject}»; mittente={relation}; "
                f"ricevuta={received or 'non disponibile'}{attachment_note}"
            )[:500],
            supports=f"mail:{message_ref}" if message_ref else "gmail:metadata",
        ))

    synced_at, freshness = sync_provenance(connected)
    sync_note = (f"Ultima sincronizzazione delle caselle lette: {synced_at}."
                 if synced_at else "Data dell'ultima sincronizzazione non disponibile.")
    return CapabilityOutcome(
        status="succeeded",
        observation=(
            f"Ho riletto {len(claims)} comunicazioni Gmail sincronizzate."
            if claims
            else "La casella è collegata, ma non risultano comunicazioni sincronizzate nella finestra letta."
        ) + " " + sync_note,
        provenance=ResultProvenance(
            source_class="connected_provider",
            capability="mail.metadata",
            provider="gmail_sync",
            source_refs=source_refs[:MAX_CLAIMS],
            freshness=freshness,
            certainty_note="Metadati delle caselle autorizzate, non una nuova lettura dal provider; finestra limitata.",
        ),
        claims=claims,
        data_ref="gmail:metadata",
    )


async def read_mail_body(db, owner_id: str, goal, *, step) -> CapabilityOutcome:
    """Read exactly one Gmail body transiently and persist only distilled facts."""
    refs = [
        str(ref) for ref in (step.input_refs or [])
        if str(ref).startswith("mail:")
    ]
    if len(refs) != 1:
        return _unavailable(
            "mail.read",
            "mail_reference_required",
            "Per leggere il contenuto serve un solo messaggio già osservato.",
        )

    message_ref = refs[0]
    message_id = message_ref.removeprefix("mail:").strip()
    if not message_id:
        return _unavailable(
            "mail.read",
            "mail_reference_required",
            "Il riferimento al messaggio non è valido.",
        )

    try:
        from connectors.gmail.scopes import EMAIL_RECORD_TYPE
        row = await db.ingestion_events.find_one(
            {
                "user_id": owner_id,
                "source_record_type": EMAIL_RECORD_TYPE,
                "$or": [
                    {"external_id": message_id},
                    {"normalized_payload.message_ref": message_id},
                ],
            },
            {"_id": 0, "connector_instance_id": 1},
            sort=[("ingested_at", -1)],
        )
    except Exception as exc:
        logger.info("mail body reference lookup soft-fail: %s", type(exc).__name__)
        row = None

    instance_id = str((row or {}).get("connector_instance_id") or "")
    if not instance_id:
        return _unavailable(
            "mail.read",
            "message_not_observed",
            "Quel messaggio non risulta fra quelli sincronizzati da ORA.",
        )

    try:
        from deps import get_gmail_service
        body = await get_gmail_service().body_for(
            user_id=owner_id,
            instance_id=instance_id,
            message_id=message_id,
        )
    except Exception as exc:
        logger.info("transient mail body read soft-fail: %s", type(exc).__name__)
        return CapabilityOutcome(
            status="failed",
            observation="Non sono riuscita a leggere quel messaggio in questo momento.",
            provenance=ResultProvenance(
                source_class="connected_provider",
                capability="mail.read",
                provider="gmail_live_body",
                source_refs=[message_ref],
                freshness="fresh",
            ),
            error_type="mail_body_read_failed",
            retryable=True,
        )

    # The body is intentionally kept in this local variable only. The
    # distiller returns paraphrased mission facts; nothing below persists or
    # returns the original text.
    try:
        from agent.reasoning import distill_private_mail
        distilled = await distill_private_mail(
            goal={
                "objective": goal.objective,
                "desired_outcome": goal.desired_outcome,
                "why_now": goal.why_now,
                "success_criteria": list(goal.success_criteria),
            },
            step=step.for_ai(),
            message_ref=message_ref,
            content=str(body or ""),
        )
    except Exception as exc:
        logger.info("mail distillation soft-fail: %s", type(exc).__name__)
        distilled = None

    if distilled is None:
        return CapabilityOutcome(
            status="failed",
            observation="Ho letto il messaggio, ma non sono riuscita a ricavarne fatti utilizzabili senza conservarne il testo.",
            provenance=ResultProvenance(
                source_class="connected_provider",
                capability="mail.read",
                provider="gmail_live_body",
                source_refs=[message_ref],
                freshness="fresh",
            ),
            error_type="private_content_distillation_unavailable",
            retryable=True,
        )

    facts = [
        Claim(text=str(fact)[:220], supports=step.expected_result or message_ref)
        for fact in (distilled.get("facts") or [])[:4]
        if str(fact).strip()
    ]
    if not facts:
        return CapabilityOutcome(
            status="partial",
            observation="Ho letto il messaggio: non aggiunge fatti utili a questo passo.",
            provenance=ResultProvenance(
                source_class="connected_provider",
                capability="mail.read",
                provider="gmail_live_body",
                source_refs=[message_ref],
                freshness="fresh",
                certainty_note="contenuto letto transitoriamente; testo originale non conservato",
            ),
            claims=[],
            data_ref=message_ref,
            error_type="no_relevant_mail_facts",
            retryable=False,
        )

    enough = bool(distilled.get("enough_for_this_step"))
    return CapabilityOutcome(
        status="succeeded" if enough else "partial",
        observation=(
            f"Ho letto il messaggio e isolato {len(facts)} fatti rilevanti senza conservarne il testo."
        ),
        provenance=ResultProvenance(
            source_class="connected_provider",
            capability="mail.read",
            provider="gmail_live_body",
            source_refs=[message_ref],
            freshness="fresh",
            certainty_note="contenuto letto transitoriamente; persistono solo fatti parafrasati",
        ),
        claims=facts,
        data_ref=message_ref,
        error_type="" if enough else "mail_facts_partial",
        retryable=False,
    )


async def read_contacts(db, owner_id: str, goal, *, step) -> CapabilityOutcome:
    """Resolve one named person/business against the synced device address book.

    The persistent evidence deliberately does not copy phone numbers. The
    telephone preparation/trust layer re-reads the contact when a call is
    actually being prepared, which keeps the sensitive value at the boundary
    that already knows how to confirm and revoke it.
    """
    try:
        state = await db.contacts_device_state.find_one(
            {"user_id": owner_id}, {"_id": 0, "status": 1, "synced_at": 1}
        )
    except Exception as exc:
        logger.info("contacts state read soft-fail: %s", type(exc).__name__)
        state = None

    if not state or state.get("status") != "connected":
        return _unavailable(
            "contacts.read",
            "requires_connection",
            "La rubrica del dispositivo non è collegata a ORA.",
        )

    who = str((step.parameters or {}).get("who") or "").strip()[:120]
    if not who:
        return _unavailable(
            "contacts.read",
            "contact_query_required",
            "Per leggere la rubrica devo sapere quale persona o attività cercare.",
        )

    try:
        from preparation.contacts import AddressBook
        candidates = await AddressBook().look_for(
            db, owner_id=owner_id, who=who
        )
    except Exception as exc:
        logger.info("contacts read soft-fail: %s", type(exc).__name__)
        return CapabilityOutcome(
            status="failed",
            observation="Non sono riuscita a cercare nella rubrica sincronizzata.",
            provenance=ResultProvenance(
                source_class="connected_provider",
                capability="contacts.read",
                provider="device_contacts_cache",
            ),
            error_type="contacts_read_failed",
            retryable=True,
        )

    refs: List[str] = []
    claims: List[Claim] = []
    for candidate in candidates[:5]:
        identity = str(candidate.contact_identity or candidate.name or "").strip()
        ref = f"contact:{identity}"[:120] if identity else "contact:match"
        if ref not in refs:
            refs.append(ref)
        detail = str(candidate.source_detail or "").strip()
        text = f"Contatto in rubrica: {candidate.name}; recapito telefonico disponibile"
        if detail:
            text += f"; {detail}"
        claims.append(Claim(text=text[:400], supports=ref))

    if not claims:
        return CapabilityOutcome(
            status="succeeded",
            observation=f"Ho cercato «{who}» nella rubrica sincronizzata e non ho trovato corrispondenze.",
            provenance=ResultProvenance(
                source_class="connected_provider",
                capability="contacts.read",
                provider="device_contacts_cache",
                freshness="fresh",
            ),
            claims=[Claim(
                text=f"Nessun contatto in rubrica corrisponde a «{who}».",
                supports=f"contact_query:{who}"[:120],
            )],
            data_ref="contacts:0",
        )

    return CapabilityOutcome(
        status="succeeded",
        observation=f"Ho trovato {len(claims)} corrispondenze nella rubrica sincronizzata per «{who}».",
        provenance=ResultProvenance(
            source_class="connected_provider",
            capability="contacts.read",
            provider="device_contacts_cache",
            source_refs=refs[:8],
            freshness="fresh",
            certainty_note="numero non copiato nell'evidenza; verrà riletto dal gate telefonico se serve",
        ),
        claims=claims[:MAX_CLAIMS],
        data_ref=refs[0] if refs else "contacts",
    )


async def read_banking(db, owner_id: str, goal, *, step=None) -> CapabilityOutcome:
    """Read a bounded financial snapshot without dumping transaction history."""
    try:
        from connectors.bank.service import agent_bank_status
        reality = await agent_bank_status(db, owner_id)
    except Exception as exc:
        logger.info("bank reality read soft-fail: %s", type(exc).__name__)
        reality = "unavailable"

    if reality == "unavailable":
        return _unavailable(
            "banking.read",
            "requires_connection",
            "Non c'è un conto bancario leggibile collegato a ORA.",
        )

    try:
        from financial.observed import the_bank_right_now, this_month, what_was_seen

        bank = await the_bank_right_now(db, owner_id)
        month = await this_month(db, owner_id)
        patterns = await what_was_seen(db, owner_id)
    except Exception as exc:
        logger.info("banking read soft-fail: %s", type(exc).__name__)
        return CapabilityOutcome(
            status="failed",
            observation="Non sono riuscita a rileggere il contesto bancario disponibile.",
            provenance=ResultProvenance(
                source_class=(
                    "connected_provider" if reality == "real" else "simulated"
                ),
                capability="banking.read",
                provider="banking_psd2",
            ),
            error_type="banking_read_failed",
            retryable=True,
        )

    claims: List[Claim] = []
    balance = bank.get("ultimo_saldo_osservato") or {}
    if balance.get("quanto"):
        claims.append(Claim(
            text=(
                f"Ultimo saldo osservato: {balance.get('quanto')}; "
                f"tipo={balance.get('tipo') or 'non specificato'}; "
                f"letto={balance.get('letto_quando') or 'non disponibile'}"
            )[:400],
            supports="bank:balance",
        ))

    if month:
        claims.append(Claim(
            text=(
                f"Questo mese, dai movimenti osservati: entrate "
                f"{month.get('entrate_osservate') or 'non disponibili'}, uscite "
                f"{month.get('uscite_osservate') or 'non disponibili'}, differenza "
                f"{month.get('differenza_parziale') or 'non disponibile'}; "
                "è una somma parziale dei movimenti letti, non un saldo."
            )[:500],
            supports="bank:month",
        ))

    recurring_in = list(patterns.get("ricorrenti_in_entrata") or [])
    recurring_out = list(patterns.get("ricorrenti_in_uscita") or [])
    if recurring_in or recurring_out:
        claims.append(Claim(
            text=(
                f"Pattern osservati sul conto: {len(recurring_in)} entrate ricorrenti "
                f"e {len(recurring_out)} uscite ricorrenti; ricorrente descrive solo "
                "la ripetizione, non il significato del movimento."
            )[:400],
            supports="bank:patterns",
        ))

    source_class = "connected_provider" if reality == "real" else "simulated"
    from agent.evidence import freshness_of
    observed_at = str(
        (balance or {}).get("letto_quando")
        or ""
    )
    freshness = freshness_of(observed_at) if observed_at else "unknown"
    note = (
        "conto reale collegato; valori derivano dall'ultima lettura disponibile"
        if reality == "real"
        else "provider demo/sandbox: questi valori non descrivono il denaro reale della persona"
    )
    return CapabilityOutcome(
        status="succeeded" if claims else "partial",
        observation=(
            "Ho letto un riepilogo bancario limitato, senza copiare l'estratto conto."
            if claims
            else "Il conto è collegato, ma non ho un riepilogo bancario utilizzabile."
        ),
        provenance=ResultProvenance(
            source_class=source_class,
            capability="banking.read",
            provider="banking_psd2",
            source_refs=[
                ref for ref in ("bank:balance" if balance else "", "bank:month" if month else "")
                if ref
            ],
            freshness=freshness,
            certainty_note=note,
        ),
        claims=claims[:MAX_CLAIMS],
        data_ref="bank:summary",
        error_type="" if claims else "no_bank_summary",
        retryable=False,
    )


async def read_weather(db, owner_id: str, goal, *, step=None) -> CapabilityOutcome:
    """Read the same real weather surface ORA already uses on Home.

    An exact owned place:<id> in the step pins the forecast to that Life
    Place. This is important for follow-ups: the user may move while the thing
    being followed stays put. A watched Situation requires its fixed place;
    an unrelated current-weather request may use authorized device position.
    Provider observation time, forecast dates and retrieval time stay distinct.
    Raw coordinates never enter durable agent evidence.
    """
    try:
        import weather as weather_service
        from home.service import HomeService
    except Exception as exc:
        logger.info("weather read import soft-fail: %s", type(exc).__name__)
        return _unavailable(
            "weather.read", "not_wired", "Il meteo non è collegato al runtime."
        )

    if not weather_service.capabilities().get("available"):
        return _unavailable(
            "weather.read", "provider_unavailable", "Il provider meteo non è disponibile."
        )

    point = None
    pinned_ref = next(
        (
            str(ref).strip()
            for ref in (getattr(step, "input_refs", None) or [])
            if str(ref).strip().startswith("place:")
        ),
        "",
    )
    situation_refs = [str(ref) for ref in (getattr(goal, "source_refs", None) or [])
                      if str(ref).startswith("situation:")]
    situation = None
    source_refs = []
    saved = None
    if situation_refs:
        from situations.repository import SituationRepository

        def location_failure(code, message):
            return CapabilityOutcome(
                status="unavailable", observation=message,
                provenance=ResultProvenance(
                    source_class="internal_observation", capability="weather.read",
                    source_refs=source_refs or situation_refs[:8], freshness="unknown",
                ),
                error_type=code, retryable=False,
            )

        if len(situation_refs) != 1 or getattr(goal, "owner_id", None) != owner_id:
            return location_failure("situation_location_required", "Il controllo non identifica una sola situazione di questa persona.")
        situation = await SituationRepository(db).get(owner_id, situation_refs[0].split(":", 1)[1])
        revision = str((getattr(goal, "source_situation", None) or {}).get("situation_revision") or "")
        if (situation is None or situation.status not in ("active", "changed")
                or revision and revision != str(situation.revision)):
            return location_failure("situation_source_changed", "La situazione è cambiata o non è più attiva: occorre rileggerla.")
        source_refs = [f"situation:{situation.id}:revision:{situation.revision}"]
        linked = [ref for ref in situation.linked_object_refs if ref.startswith("place:")]
        if pinned_ref and pinned_ref not in linked:
            return location_failure("situation_place_mismatch", "Il luogo proposto non è quello associato alla situazione.")
        if not pinned_ref and len(linked) == 1:
            pinned_ref = linked[0]
        if not pinned_ref and linked:
            return location_failure("situation_location_required", "La situazione ha più luoghi: manca l'ancora univoca per questo controllo.")
        if not pinned_ref:
            # Resolve the named location without inventing a saved Home or
            # moving the thing to the person's current device position.
            label = str(situation.location_label or "").strip()
            location_event = next((event for event in reversed(situation.history)
                                   if "location_label" in event.changes), None)
            if (not label or location_event is None or location_event.source == "inferred"
                    or str(location_event.changes.get("location_label") or "").strip() != label):
                return location_failure("situation_location_required", "Per il meteo serve il luogo della situazione confermato nella sua fonte.")
            from places import lookup
            from places.models import Coordinates

            def normalized(value):
                return " ".join(str(value or "").casefold().split())

            try:
                suggestions = await lookup.suggest(label)
                place_id = (lookup.unique_locality_match(suggestions, label)
                            if suggestions.get("available") else None)
                if not place_id:
                    return location_failure("situation_location_unresolved", "Il servizio luoghi non ha risolto in modo univoco la località della situazione.")
                resolved = await lookup.resolve(place_id)
                if (not resolved.get("available") or str(resolved.get("place_id") or "") != place_id
                        or normalized(label) not in {normalized(resolved.get("locality")), normalized(resolved.get("address"))}):
                    return location_failure("situation_location_unresolved", "La località restituita dal servizio non conferma quella della situazione.")
                coordinates = Coordinates(latitude=resolved["latitude"], longitude=resolved["longitude"])
                point = (coordinates.latitude, coordinates.longitude, label)
                source_refs.append(f"google_place:{place_id}")
            except Exception as exc:
                logger.info("weather Situation location soft-fail: %s", type(exc).__name__)
                return location_failure("situation_location_unresolved", "Il servizio luoghi non ha permesso di verificare la località della situazione.")
    if pinned_ref:
        try:
            from places.service import PlacesService

            place_id = pinned_ref.split(":", 1)[1]
            saved = await PlacesService(db).get_place(owner_id, place_id)
            if saved and saved.coordinates is not None and saved.state == "confirmed":
                point = (
                    float(saved.coordinates.latitude),
                    float(saved.coordinates.longitude),
                    str(saved.locality or saved.label or "").strip(),
                )
                if situation:
                    source_refs.append(f"place_snapshot:{saved.id}:{saved.updated_at}")
        except Exception as exc:
            logger.info("weather pinned-place soft-fail: %s", type(exc).__name__)
        if point is None:
            return CapabilityOutcome(
                status="unavailable",
                observation="Il luogo fissato per questo controllo non è più disponibile.",
                provenance=ResultProvenance(
                    source_class="internal_observation",
                    capability="weather.read",
                    source_refs=[pinned_ref],
                    freshness="unknown",
                    certainty_note="place ref non risolvibile o senza coordinate",
                ),
                error_type="place_unavailable",
                retryable=False,
            )
    elif point is None:
        try:
            point = await HomeService(db)._where_they_are(owner_id)
        except Exception as exc:
            logger.info("weather location soft-fail: %s", type(exc).__name__)
            point = None
        if point is None:
            return CapabilityOutcome(
                status="unavailable",
                observation=(
                    "Non posso leggere il meteo del posto in cui sei perché non ho "
                    "una posizione corrente autorizzata e abbastanza recente."
                ),
                provenance=ResultProvenance(
                    source_class="internal_observation",
                    capability="weather.read",
                    freshness="unknown",
                    certainty_note="nessun punto corrente utilizzabile per il meteo",
                ),
                error_type="location_unavailable",
                retryable=False,
            )

    lat, lon, place = point
    source_refs = ([pinned_ref] if pinned_ref else []) + source_refs
    try:
        data = await weather_service.forecast_at(lat=lat, lon=lon, place=place)
    except Exception as exc:
        logger.info("weather provider soft-fail: %s", type(exc).__name__)
        return CapabilityOutcome(
            status="failed",
            observation="Il servizio meteo non ha risposto.",
            provenance=ResultProvenance(
                source_class="external_research",
                capability="weather.read",
                provider=str(weather_service.configured_provider() or "weather")[:60],
            ),
            error_type="weather_read_failed",
            retryable=True,
        )

    if situation:
        latest = await SituationRepository(db).get(owner_id, situation.id)
        if latest is None or latest.revision != situation.revision or latest.status not in ("active", "changed"):
            return location_failure("situation_source_changed", "La situazione è cambiata durante la lettura meteo: questa risposta non è più pertinente.")
        if saved:
            latest_place = await PlacesService(db).get_place(owner_id, saved.id)
            if (latest_place is None or latest_place.state != "confirmed"
                    or latest_place.updated_at != saved.updated_at):
                return location_failure("situation_source_changed", "Il luogo è cambiato durante la lettura meteo: serve una nuova verifica.")

    if not data.get("available"):
        return CapabilityOutcome(
            status="unavailable",
            observation=str(data.get("why_unavailable") or "Meteo non disponibile.")[:400],
            provenance=ResultProvenance(
                source_class="external_research",
                capability="weather.read",
                provider=str(weather_service.configured_provider() or "weather")[:60],
                freshness="unknown",
            ),
            error_type="weather_unavailable",
            retryable=True,
        )

    # A recent HTTP response is not a recent weather observation. These are
    # operational reuse limits for time-sensitive advice, not a drying model.
    from zoneinfo import ZoneInfo

    provider = str(data.get("provider") or weather_service.configured_provider() or "weather")[:60]
    zone_name = str(data.get("timezone") or "")[:64]
    raw_offset = data.get("utc_offset_seconds")
    offset = raw_offset if isinstance(raw_offset, int) and not isinstance(raw_offset, bool) and abs(raw_offset) <= 14 * 3600 else None
    try:
        provider_zone = ZoneInfo(zone_name) if zone_name else None
    except (ValueError, KeyError):
        provider_zone = None

    def provider_moment(value, *, observation=False):
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
        if parsed.tzinfo is not None:
            if provider_zone and parsed.utcoffset() != parsed.astimezone(provider_zone).utcoffset():
                return None
            return parsed
        if provider_zone is None:
            # A provider offset can anchor its current reading, but is not a
            # licence to assign that offset across future DST transitions.
            return parsed.replace(tzinfo=timezone(timedelta(seconds=offset))) if observation and not zone_name and offset is not None else None
        candidates = []
        for fold in (0, 1):
            candidate = parsed.replace(tzinfo=provider_zone, fold=fold)
            roundtrip = candidate.astimezone(timezone.utc).astimezone(provider_zone)
            if roundtrip.replace(tzinfo=None) != parsed:
                continue  # Non-existent local hour during the spring change.
            if observation and offset is not None and candidate.utcoffset().total_seconds() != offset:
                continue
            if all(candidate.utcoffset() != item.utcoffset() for item in candidates):
                candidates.append(candidate)
        # An ambiguous hourly forecast stays ambiguous; don't pick a fold.
        return candidates[0] if len(candidates) == 1 else None

    observed = provider_moment(data.get("observed_at"), observation=True)
    now = _now()
    age_seconds = (now - observed).total_seconds() if observed else None
    freshness = (
        "unknown" if age_seconds is None or age_seconds < 0
        else "fresh" if age_seconds <= 90 * 60
        else "recent" if age_seconds <= 3 * 3600
        else "stale"
    )
    observed_at = observed.isoformat() if observed else ""
    retrieved_at = str(data.get("retrieved_at") or "")[:64]
    place_label = str(place or data.get("place") or "").strip()
    reported_place = str(data.get("place") or "").strip()
    if place and reported_place and place.casefold().strip() != reported_place.casefold():
        return CapabilityOutcome(
            status="unavailable", observation="La risposta meteo indica un luogo diverso da quello richiesto.",
            provenance=ResultProvenance(
                source_class="external_research", capability="weather.read", provider=provider,
                source_refs=source_refs, observed_at=observed_at,
                freshness="unknown", certainty_note="luogo della risposta non coerente con il luogo richiesto",
            ),
            error_type="weather_place_mismatch", retryable=True,
        )
    claims: List[Claim] = [Claim(
        text=(f"Fonte meteo: {provider}; luogo richiesto: {place_label or 'non etichettato'}; "
              f"osservazione: {observed_at or 'data/fuso non verificabili'}; "
              f"fuso provider: {zone_name or 'non indicato'}; "
              f"risposta letta da ORA: {retrieved_at or 'orario non indicato'}. "
              "L'ora di lettura non aggiorna l'osservazione e la previsione non misura l'esito fisico.")[:600],
        supports="provenienza, luogo e validità temporale del meteo",
    )]
    current_bits = []
    if data.get("condition_label"):
        current_bits.append(str(data["condition_label"]))
    if data.get("temperature_c") is not None:
        current_bits.append(f"{data['temperature_c']} °C")
    if data.get("humidity_pct") is not None:
        current_bits.append(f"umidità {data['humidity_pct']}%")
    if data.get("wind_kmh") is not None:
        current_bits.append(f"vento {data['wind_kmh']} km/h")
    if data.get("precipitation_mm") is not None:
        current_bits.append(f"precipitazioni {data['precipitation_mm']} mm")
    if current_bits:
        claims.append(Claim(
            text=(f"Condizioni riportate{f' a {place_label}' if place_label else ''} "
                  f"all'osservazione {observed_at or 'di orario non verificabile'}: " + ", ".join(current_bits))[:600],
            supports="condizioni meteo all'orario dell'osservazione",
            measures={key: float(data[key]) for key in
                      ("temperature_c", "humidity_pct", "wind_kmh", "precipitation_mm")
                      if isinstance(data.get(key), (int, float)) and not isinstance(data.get(key), bool)},
        ))

    hours = [hour for hour in list(data.get("hours") or [])[:12] if isinstance(hour, dict)]
    dated_hours = [(hour, provider_moment(hour.get("datetime"))) for hour in hours]
    future_hours = [(hour, moment) for hour, moment in dated_hours
                    if moment is not None and moment.astimezone(timezone.utc) + timedelta(hours=1) > now]
    rain_values = [
        h.get("rain_chance_pct") for h in hours
        if isinstance(h, dict) and isinstance(h.get("rain_chance_pct"), (int, float))
    ]
    temps = [
        h.get("temperature_c") for h in hours
        if isinstance(h, dict) and isinstance(h.get("temperature_c"), (int, float))
    ]
    if rain_values:
        claims.append(Claim(
            text=(
                "Nel profilo orario del provider la probabilità massima di pioggia "
                f"indicata dal provider è {round(max(rain_values))}%."
            ),
            supports="probabilità di pioggia nel profilo orario, distinta dall'intensità",
            measures={"rain_chance_max_pct": float(max(rain_values))},
        ))
    if temps:
        claims.append(Claim(
            text=(
                "Nel profilo orario del provider la temperatura prevista va circa da "
                f"{round(min(temps))} a {round(max(temps))} °C."
            ),
            supports="temperatura nel profilo orario del provider",
        ))

    # Keep a short chronological profile when the provider supplied it.
    # This is deliberately domain-neutral: the agent may need the trend for
    # any temporary life outcome. No coordinates or raw provider payload are
    # persisted.
    hourly_profile = []
    for hour, moment in dated_hours[:12]:
        clock = moment.isoformat() if moment else str(hour.get("datetime") or hour.get("time") or "")[:64]
        bits = [clock + (" (data/fuso non verificabili)" if moment is None else "")]
        if hour.get("temperature_c") is not None:
            bits.append(f"{hour['temperature_c']}°C")
        if hour.get("humidity_pct") is not None:
            bits.append(f"umidità {hour['humidity_pct']}%")
        if hour.get("wind_kmh") is not None:
            bits.append(f"vento {hour['wind_kmh']} km/h")
        if hour.get("rain_chance_pct") is not None:
            bits.append(f"pioggia {hour['rain_chance_pct']}%")
        if len(bits) > 1:
            hourly_profile.append(", ".join(bits))
    for start in range(0, len(hourly_profile), 3):
        claims.append(Claim(
            text=("Profilo previsto: " + " | ".join(hourly_profile[start:start + 3]))[:600],
            supports="andamento orario delle condizioni ambientali",
        ))

    # Daylight bounds what ambient conditions can do: the hours after sunset
    # are cooler and damper. Production 24/10 (Tarquinia, 16 °C, 65%): a
    # completion estimate ran into the evening without knowing it was evening.
    sunrise, sunset = str(data.get("sunrise") or "")[:5], str(data.get("sunset") or "")[:5]
    if sunrise and sunset:
        claims.append(Claim(
            text=(f"Luce del giorno oggi{f' a {place_label}' if place_label else ''}: "
                  f"alba {sunrise}, tramonto {sunset} (ora locale del luogo)."),
            supports="ore di luce del giorno nel luogo",
        ))

    for day in list(data.get("days") or [])[:2]:
        if not isinstance(day, dict):
            continue
        bits = []
        if day.get("condition_label"):
            bits.append(str(day["condition_label"]))
        if day.get("min_c") is not None and day.get("max_c") is not None:
            bits.append(f"{day['min_c']}–{day['max_c']} °C")
        if day.get("rain_chance_pct") is not None:
            bits.append(f"pioggia max {day['rain_chance_pct']}%")
        if bits:
            claims.append(Claim(
                text=f"{str(day.get('label') or day.get('date') or 'Giorno')}: {', '.join(bits)}"[:500],
                supports="previsione meteo giornaliera",
            ))

    valid_until = None
    if freshness == "fresh" and (current_bits or future_hours):
        # Re-read current conditions at the checkpoint. A far-future forecast
        # horizon must not prolong the validity of an old current reading.
        valid_until = observed.astimezone(timezone.utc) + timedelta(minutes=90)
        if future_hours:
            valid_until = min(valid_until, max(moment.astimezone(timezone.utc) + timedelta(hours=1)
                                                for _, moment in future_hours))
    provenance = ResultProvenance(
        source_class="external_research", capability="weather.read", provider=provider,
        source_refs=source_refs, observed_at=observed_at,
        freshness=freshness, weather_valid_until=valid_until.isoformat() if valid_until else None,
        certainty_note=(f"Osservazione del provider; fuso {zone_name or 'non indicato'}. "
                        "Il recupero della risposta non prova l'attualità dei dati né l'esito fisico.")[:200],
    )
    if len(claims) == 1:
        return CapabilityOutcome(
            status="partial",
            observation="Il provider meteo ha risposto, ma senza dati utili per questo passo.",
            provenance=provenance,
            error_type="weather_insufficient",
            retryable=True,
        )

    return CapabilityOutcome(
        status="succeeded",
        observation=(
            f"Ho letto la risposta meteo{f' per {place_label}' if place_label else ''}: "
            f"{len(claims) - 1} elementi; "
            + ("osservazione recente del provider." if freshness == "fresh" else
               "dati non convalidati per una decisione attuale: occorre una lettura aggiornata.")
        ),
        provenance=provenance,
        claims=claims[:WEATHER_MAX_CLAIMS],
        data_ref="weather:forecast",
    )


async def read_route(db, owner_id: str, goal, *, step=None) -> CapabilityOutcome:
    """Read one real route without persisting its endpoint coordinates.

    Two exact place refs mean [origin, destination]. One place ref means the
    destination and the origin may only be the current/recent device position
    already authorized by the user. Labels and canonical refs may persist as
    evidence; coordinate pairs never do.
    """
    try:
        from home.service import HomeService
        from places import routing
        from places.service import PlacesService
    except Exception as exc:
        logger.info("route read import soft-fail: %s", type(exc).__name__)
        return _unavailable(
            "route.read", "not_wired", "Il routing live non è collegato al runtime."
        )

    capabilities = routing.capabilities()
    if not capabilities.get("available"):
        return _unavailable(
            "route.read",
            "provider_unavailable",
            "Il servizio di routing live non è disponibile.",
        )

    refs = [
        str(ref).strip()
        for ref in (getattr(step, "input_refs", None) or [])
        if str(ref).strip().startswith("place:")
    ]
    if not refs:
        return _unavailable(
            "route.read",
            "route_destination_required",
            "Manca un luogo esatto da usare come destinazione del percorso.",
        )
    if len(refs) > 2:
        return _unavailable(
            "route.read",
            "route_refs_ambiguous",
            "Il percorso cita più di due luoghi e non è chiaro quali siano origine e destinazione.",
        )

    places = PlacesService(db)

    async def saved_point(ref: str):
        place_id = ref.split(":", 1)[1].strip()
        if not place_id:
            return None
        item = await places.get_place(owner_id, place_id)
        if not item or item.state == "dismissed" or item.coordinates is None:
            return None
        return (
            {
                "latitude": float(item.coordinates.latitude),
                "longitude": float(item.coordinates.longitude),
            },
            str(item.label or item.locality or "luogo salvato")[:120],
        )

    source_refs: List[str] = []
    if len(refs) == 2:
        origin_saved = await saved_point(refs[0])
        destination_saved = await saved_point(refs[1])
        if origin_saved is None or destination_saved is None:
            return CapabilityOutcome(
                status="unavailable",
                observation="Uno dei luoghi fissati per il percorso non è disponibile per questo utente.",
                provenance=ResultProvenance(
                    source_class="internal_observation",
                    capability="route.read",
                    source_refs=refs[:2],
                    freshness="unknown",
                ),
                error_type="place_unavailable",
                retryable=False,
            )
        origin, origin_label = origin_saved
        destination, destination_label = destination_saved
        source_refs = refs[:2]
    else:
        destination_saved = await saved_point(refs[0])
        if destination_saved is None:
            return CapabilityOutcome(
                status="unavailable",
                observation="La destinazione fissata per il percorso non è disponibile per questo utente.",
                provenance=ResultProvenance(
                    source_class="internal_observation",
                    capability="route.read",
                    source_refs=refs[:1],
                    freshness="unknown",
                ),
                error_type="place_unavailable",
                retryable=False,
            )
        destination, destination_label = destination_saved
        try:
            current = await HomeService(db)._where_they_are(owner_id)
        except Exception as exc:
            logger.info("route current-location soft-fail: %s", type(exc).__name__)
            current = None
        if current is None:
            return CapabilityOutcome(
                status="unavailable",
                observation=(
                    "Ho la destinazione, ma non una posizione corrente autorizzata "
                    "e abbastanza recente da usare come origine."
                ),
                provenance=ResultProvenance(
                    source_class="internal_observation",
                    capability="route.read",
                    source_refs=refs[:1],
                    freshness="unknown",
                ),
                error_type="location_unavailable",
                retryable=True,
            )
        lat, lon, label = current
        origin = {"latitude": float(lat), "longitude": float(lon)}
        origin_label = str(label or "posizione corrente")[:120]
        source_refs = ["location:presence", refs[0]]

    mode = str(
        ((getattr(step, "parameters", None) or {}).get("travel_mode") or "drive")
    ).strip().lower()
    if mode not in ("drive", "walk", "bicycle", "transit"):
        mode = "drive"

    try:
        route = await routing.get_route(
            origin=origin,
            destination=destination,
            travel_mode=mode,
            alternatives=False,
        )
    except Exception as exc:
        logger.info("route provider soft-fail: %s", type(exc).__name__)
        return CapabilityOutcome(
            status="failed",
            observation="Il provider di routing non ha restituito un percorso utilizzabile.",
            provenance=ResultProvenance(
                source_class="external_research",
                capability="route.read",
                provider=str(capabilities.get("provider") or "routing")[:60],
                source_refs=source_refs,
                freshness="unknown",
            ),
            error_type="route_read_failed",
            retryable=True,
        )

    if not route.get("available"):
        return CapabilityOutcome(
            status="unavailable",
            observation=str(
                route.get("why_unavailable") or "Percorso live non disponibile."
            )[:500],
            provenance=ResultProvenance(
                source_class="external_research",
                capability="route.read",
                provider=str(route.get("provider") or capabilities.get("provider") or "routing")[:60],
                source_refs=source_refs,
                freshness="unknown",
            ),
            error_type="route_unavailable",
            retryable=True,
        )

    duration = route.get("duration_seconds")
    distance = route.get("distance_meters")
    if not isinstance(duration, (int, float)) or duration < 0:
        return CapabilityOutcome(
            status="partial",
            observation="Il provider ha risposto senza una durata verificabile.",
            provenance=ResultProvenance(
                source_class="external_research",
                capability="route.read",
                provider=str(route.get("provider") or capabilities.get("provider") or "routing")[:60],
                source_refs=source_refs,
                freshness="fresh",
            ),
            error_type="route_duration_missing",
            retryable=True,
        )

    minutes = max(1, round(float(duration) / 60.0))
    bits = [f"circa {minutes} min"]
    if isinstance(distance, (int, float)) and distance >= 0:
        km = float(distance) / 1000.0
        bits.append(f"{km:.1f} km")

    traffic = bool(route.get("reflects_current_traffic"))
    claim = (
        f"Percorso {origin_label} → {destination_label}: "
        + ", ".join(bits)
        + ("; tiene conto del traffico attuale." if traffic else "; traffico live non dichiarato dal provider.")
    )

    extra_claims: List[Claim] = []
    without_traffic = route.get("duration_without_traffic_seconds")
    if (
        traffic
        and isinstance(without_traffic, (int, float))
        and without_traffic >= 0
        and float(duration) >= float(without_traffic)
    ):
        delay = max(0, round((float(duration) - float(without_traffic)) / 60.0))
        extra_claims.append(Claim(
            text=f"Il traffico aggiunge circa {delay} min rispetto alla durata senza traffico indicata dal provider.",
            supports="impatto del traffico sul tempo di percorrenza",
        ))

    return CapabilityOutcome(
        status="succeeded",
        observation=(
            "Ho letto un percorso reale dal provider configurato. "
            "Le coordinate degli estremi non sono state salvate nell'evidenza del goal."
        ),
        provenance=ResultProvenance(
            source_class="external_research",
            capability="route.read",
            provider=str(route.get("provider") or capabilities.get("provider") or "routing")[:60],
            source_refs=source_refs,
            freshness="fresh",
            certainty_note=(
                "percorso live con traffico"
                if traffic
                else "percorso live; il provider non dichiara traffico corrente"
            ),
        ),
        claims=[
            Claim(
                text=claim[:500],
                supports="tempo e distanza del percorso da verificare",
            ),
            *extra_claims,
        ][:3],
        data_ref="route:live",
    )


async def read_location(db, owner_id: str, goal) -> CapabilityOutcome:
    """Read current/recent presence without persisting raw coordinates as evidence."""
    try:
        from location.service import LocationService
        presence = await LocationService(db).build_presence(owner_id)
    except Exception as exc:
        logger.info("location read soft-fail: %s", type(exc).__name__)
        return CapabilityOutcome(
            status="failed",
            observation="Non sono riuscita a rileggere la posizione disponibile.",
            provenance=ResultProvenance(
                source_class="internal_observation",
                capability="location.read",
                provider="device_presence",
            ),
            error_type="location_read_failed",
            retryable=True,
        )

    if presence.preference != "while_using":
        return _unavailable(
            "location.read",
            "requires_connection",
            "La posizione non è stata autorizzata per ORA.",
        )

    label = (
        presence.place_label
        or presence.place_locality
        or presence.place_municipality
        or presence.place_region
    )
    freshness = str(presence.freshness or "UNKNOWN")
    evidence_freshness = {
        "CURRENT": "fresh",
        "RECENT": "recent",
        "STALE": "stale",
        "UNKNOWN": "unknown",
    }.get(freshness, "unknown")
    if freshness not in ("CURRENT", "RECENT"):
        # Native background presence is stored by Places, not by the older
        # foreground-location repository. Prefer that semantic fact when it is
        # current: it says "at Casa", never exposes the coordinates that woke
        # the phone up.
        try:
            from agent.evidence import freshness_of
            from places.service import PlacesService

            monitoring = await db.users.find_one(
                {"user_id": owner_id},
                {"_id": 0, "preferences.place_monitoring_enabled": 1},
            )
            enabled = bool(
                ((monitoring or {}).get("preferences") or {}).get(
                    "place_monitoring_enabled"
                )
            )
            where = await PlacesService(db).where_now(owner_id) if enabled else {}
            seen = str(where.get("last_seen_at") or "")
            place_freshness = freshness_of(seen) if seen else "unknown"
            if where.get("at_a_known_place") and place_freshness in ("fresh", "recent"):
                place_id = str(where.get("place_id") or "")
                place_name = str(where.get("place") or "luogo conosciuto")
                return CapabilityOutcome(
                    status="succeeded",
                    observation="Ho verificato la presenza osservata dal dispositivo in background.",
                    provenance=ResultProvenance(
                        source_class="internal_observation",
                        capability="location.read",
                        provider="native_place_presence",
                        source_refs=[f"place:{place_id}"] if place_id else [],
                        freshness=place_freshness,
                        certainty_note="luogo semantico da presenza nativa; coordinate non incluse nell'evidenza",
                    ),
                    claims=[Claim(
                        text=f"Presenza {place_freshness}: {place_name}"[:400],
                        supports=f"place:{place_id}" if place_id else "device_location",
                    )],
                    data_ref=f"place:{place_id}" if place_id else "location:presence",
                )
        except Exception as exc:
            logger.info("background place presence read soft-fail: %s", type(exc).__name__)

        return CapabilityOutcome(
            status="partial",
            observation="L'ultima posizione disponibile non è abbastanza recente per presentarla come attuale.",
            provenance=ResultProvenance(
                source_class="internal_observation",
                capability="location.read",
                provider="device_presence",
                freshness=evidence_freshness,
            ),
            claims=[Claim(
                text=f"Ultima posizione disponibile: stato={freshness}; luogo non considerato attuale.",
                supports="device_location",
            )],
            data_ref="location:presence",
            error_type="stale_location",
            retryable=True,
        )

    text = f"Posizione {freshness.lower()}: {label or 'luogo non etichettato'}"
    if presence.last_seen_at:
        text += f"; osservata={presence.last_seen_at}"
    return CapabilityOutcome(
        status="succeeded",
        observation="Ho verificato la posizione disponibile sul dispositivo.",
        provenance=ResultProvenance(
            source_class="internal_observation",
            capability="location.read",
            provider="device_presence",
            freshness=evidence_freshness,
        ),
        claims=[Claim(text=text[:400], supports="device_location")],
        data_ref="location:presence",
    )


async def read_calendar(db, owner_id: str, goal) -> CapabilityOutcome:
    """
    What is actually on the calendar — if one is actually connected.

        NEVER SIMULATE A CONNECTION TO DECLARE IT WORKING.

    The distinction that earns its keep here is between "nothing is coming
    up" and "there is no calendar". They look identical in the data and mean
    opposite things to a plan, so this reports the missing connection rather
    than an empty week.
    """
    try:
        from agent.connector_reads import authorized_instances, sync_provenance
        connected = await authorized_instances(db, owner_id, "calendar_google", "calendar.read", audit=True)
    except Exception as e:
        logger.info("calendar connection check soft-fail: %s", type(e).__name__)
        return CapabilityOutcome(
            status="failed", observation="Non riesco a verificare la connessione al calendario in questo momento.",
            provenance=ResultProvenance(source_class="internal_observation", capability="calendar.read"),
            error_type="calendar_connection_check_failed", retryable=True,
        )

    if not connected:
        return CapabilityOutcome(
            status="unavailable",
            observation="Non c'è un calendario collegato con il permesso di lettura, quindi non posso guardarci.",
            provenance=ResultProvenance(
                source_class="connected_provider", capability="calendar.read"
            ),
            error_type="requires_connection",
            retryable=False,
        )

    try:
        from home.adapters.google_calendar import load_google_calendar_events
        events, warnings = await load_google_calendar_events(db, owner_id, instances=connected)
        synced_at, freshness = sync_provenance(connected)
    except Exception:
        return CapabilityOutcome(
            status="failed", observation="Non sono riuscita a leggere il calendario sincronizzato.",
            provenance=ResultProvenance(source_class="internal_observation", capability="calendar.read"),
            error_type="calendar_read_failed", retryable=True,
        )
    claims = [Claim(
        text=f"In calendario: {event.title} — {event.start_at}"[:400],
        supports="appuntamento presente nell'ultima sincronizzazione",
    ) for event in events[:MAX_EVENTS]]
    return CapabilityOutcome(
        status="succeeded" if claims else "partial",
        observation=(f"Ho letto {len(claims)} appuntamenti dal calendario sincronizzato. "
                     if claims else "Non ho trovato appuntamenti nella finestra letta. ")
                    + (f"Ultima sincronizzazione: {synced_at}. " if synced_at else "Data dell'ultima sincronizzazione non disponibile. ")
                    + "La lettura è limitata ai calendari selezionati e ai prossimi 14 giorni; non conferma cancellazioni di viaggi o prenotazioni.",
        provenance=ResultProvenance(
            source_class="internal_observation", capability="calendar.read",
            provider="google_calendar_sync", freshness=freshness,
        ),
        claims=claims[:MAX_CLAIMS], data_ref="calendar",
    )


# --- looking things up in the world ----------------------------------------

async def do_research(
    db, owner_id: str, goal, step, *, reuse: bool = True
) -> CapabilityOutcome:
    """
    Find something out, through the research engine that already exists.

        DO NOT DUPLICATE THE RESEARCH ENGINE.

    V3.4 already knows how to plan queries, weigh sources, notice conflicts
    and decide whether what it has is enough. All this does is ask it the
    step's question and translate what comes back into claims — including
    sufficiency and any conflict, because a planner told only the answer will
    treat a contested answer as settled.
    """
    try:
        from research.models import ResearchNeed
        from research.service import ResearchService
    except Exception as e:
        logger.info("research import soft-fail: %s", type(e).__name__)
        return _unavailable("web.research", "not_wired", "La ricerca non e collegata.")

    question = (step.expected_result or step.intent or "").strip()
    if not question:
        return _unavailable(
            "web.research", "nothing_to_ask", "Non c'era una domanda da porre."
        )

    known = [str(c)[:200] for c in (goal.success_criteria or [])][:12]
    situation_refs = list(dict.fromkeys(
        str(ref) for ref in (goal.source_refs or [])[:8]
        if str(ref).startswith("situation:")
    ))[:4]
    context_unavailable = False
    if situation_refs:
        # Re-read the same owner-scoped context the agent planner sees. Opaque
        # goal refs and success criteria alone lose the subject of the search.
        # No profile/current-position fallback: an absent location stays absent.
        from situations.repository import SituationRepository

        source_context = []
        for ref in situation_refs:
            try:
                state = await SituationRepository(db).get(owner_id, ref.split(":", 1)[1])
            except Exception as exc:
                logger.info("research situation context unavailable: %s", type(exc).__name__)
                state = None
            if state is None:
                context_unavailable = True
                continue
            source_context.append({"ref": ref, "source": "situation", **state.context_preview()})
        known = [json.dumps({
            "source_context": source_context,
            "source_context_unavailable": context_unavailable,
        }, ensure_ascii=False), *known[:11]]

    need = ResearchNeed(
        question=question[:400],
        purpose=(goal.desired_outcome or "")[:300],
        already_known=known,
    )

    try:
        run = await ResearchService(db).run(
            owner_id, need, situation_ref=f"goal:{goal.id}", allow_reuse=reuse
        )
    except Exception as e:
        logger.info("research run soft-fail: %s", type(e).__name__)
        return CapabilityOutcome(
            status="failed",
            observation="La ricerca non e andata a buon fine.",
            provenance=ResultProvenance(
                source_class="external_research", capability="web.research"
            ),
            error_type="provider_unavailable",
            retryable=True,
        )

    synthesis = getattr(run, "synthesis", None)
    assessments = list(getattr(run, "assessments", None) or [])
    assessment = assessments[-1] if assessments else None
    sufficiency = getattr(assessment, "sufficiency", "insufficient") if assessment else "insufficient"
    conflicts = list(getattr(assessment, "conflicts", None) or []) if assessment else []

    # Research's free-text answer is not a substitute for source-validated
    # claims, including older cached runs whose claims were never validated.
    source_ids = {
        str(source.source_id) for source in (getattr(run, "sources", None) or [])
        if str(getattr(source, "url", "") or "").strip()
    }
    claims: List[Claim] = []
    rejected_claims = False
    for claim in (getattr(synthesis, "claims", None) or []):
        text = (getattr(claim, "statement", "") or "").strip()
        cited = set(getattr(claim, "supported_by", None) or []) & source_ids
        if not text or not cited:
            rejected_claims = True
            continue
        if (getattr(claim, "scope", "") == "person_specific"
                and not getattr(claim, "person_evidence_used", None)):
            rejected_claims = True
            continue
        claims.append(Claim(text=text[:600], supports=question[:300]))
    validated_claims = bool(claims)

    # A conflict is a finding, not a failure. It goes in as a claim of its own
    # so the planner has to reckon with it rather than read past it.
    for conflict in conflicts[:2]:
        about = getattr(conflict, "about", "") or ""
        if about:
            claims.append(Claim(
                text=f"Le fonti non concordano su: {about}"[:600],
                supports="disaccordo fra le fonti",
            ))

    from agent.evidence import freshness_of

    run_id = getattr(run, "id", "")
    observed_at = str(getattr(run, "completed_at", None) or getattr(run, "started_at", "") or "")
    freshness = freshness_of(observed_at)
    try:
        valid_until = datetime.fromisoformat(str(getattr(run, "valid_until", "") or ""))
        still_valid = valid_until.tzinfo is not None and valid_until > _now()
    except (TypeError, ValueError):
        still_valid = False
    enough = (
        getattr(run, "user_id", None) == owner_id
        and getattr(run, "status", "") == "completed"
        and sufficiency == "sufficient" and validated_claims and not rejected_claims
        and not context_unavailable
        and not getattr(assessment, "missing_evidence", None)
        and not any(not getattr(c, "resolved", False) for c in conflicts)
    )
    # What the synthesis leaves open is a caveat, not a veto. Production
    # 23/10: a sufficient, fully cited drying-time baseline was refused
    # because it noted that the evening's drizzle was still uncertain — which
    # is exactly what the live weather reading is for. Missing evidence and
    # unresolved conflicts still refuse it.
    open_points = [str(u)[:120] for u in (getattr(synthesis, "unresolved", None) or [])][:2]
    provenance = ResultProvenance(
        source_class="external_research", capability="web.research", provider="research",
        source_refs=[run_id] if run_id else [],
        observed_at=observed_at, freshness=freshness,
        research_sufficient=bool(enough and run_id and still_valid and freshness in ("fresh", "recent")),
        research_valid_until=str(getattr(run, "valid_until", "") or "") or None,
        certainty_note=(
            f"quanto bastano le fonti: {sufficiency}; claim citate verificate: {validated_claims}"
            + (f"; resta aperto: {'; '.join(open_points)}" if open_points else "")
        )[:200],
    )
    if getattr(run, "status", "") == "failed" or not claims:
        return CapabilityOutcome(
            status="partial" if claims else "failed",
            observation=(
                getattr(run, "outcome_note", "") or "Non ho trovato niente di utilizzabile."
            )[:600],
            provenance=provenance,
            claims=claims,
            data_ref=run_id,
            error_type="research_insufficient",
            retryable=True,
        )

    return CapabilityOutcome(
        status="succeeded" if enough else "partial",
        observation=(
            f"Ho cercato: {question[:120]}. "
            + " ".join(claim.text for claim in claims)[:300]
        ).strip()[:600],
        provenance=provenance,
        claims=claims[:MAX_CLAIMS],
        data_ref=run_id,
        error_type="" if enough else "not_enough_yet",
    )


async def do_comparison(
    db, owner_id: str, goal, step, *, research_refs: List[str]
) -> CapabilityOutcome:
    """
    Weigh alternatives, through the comparison engine that already exists.

    V3.5 owns the arithmetic and the constraint checking, which is exactly
    the part that must not be a model's job. This hands it what research
    already found and returns the recommendation state — including when it
    declines to recommend, because a comparison that always picks a winner is
    not comparing.
    """
    try:
        from comparison.models import ComparisonNeed
        from comparison.service import ComparisonService
    except Exception as e:
        logger.info("comparison import soft-fail: %s", type(e).__name__)
        return _unavailable(
            "comparison.run", "not_wired", "Il confronto non e collegato."
        )

    if not research_refs:
        # Nothing to compare is not a failed comparison. It is a plan that
        # asked for one too early, and it should be told so.
        return CapabilityOutcome(
            status="partial",
            observation="Non ho ancora abbastanza per mettere a confronto le opzioni.",
            provenance=ResultProvenance(
                source_class="deterministic_computation", capability="comparison.run"
            ),
            error_type="nothing_to_compare",
            retryable=False,
        )

    need = ComparisonNeed(
        decision=(step.intent or goal.objective)[:400],
        purpose=(goal.desired_outcome or "")[:300],
    )
    try:
        run = await ComparisonService(db).run(
            owner_id,
            need,
            [],
            situation_ref=f"goal:{goal.id}",
            research_run_ids=list(research_refs)[:4],
            allow_research=False,
        )
    except Exception as e:
        logger.info("comparison run soft-fail: %s", type(e).__name__)
        return CapabilityOutcome(
            status="failed",
            observation="Il confronto non e andato a buon fine.",
            provenance=ResultProvenance(
                source_class="deterministic_computation", capability="comparison.run"
            ),
            error_type="provider_unavailable",
            retryable=True,
        )

    recommendation = getattr(run, "recommendation", None)
    chosen = str(getattr(recommendation, "recommended", "") or "") if recommendation else ""
    note = (getattr(run, "outcome_note", "") or "")[:400]
    run_id = getattr(run, "id", "")

    claims: List[Claim] = []
    if chosen:
        claims.append(Claim(
            text=f"Fra le opzioni, la piu adatta risulta: {chosen}"[:600],
            supports="quale scegliere",
        ))
    if note:
        claims.append(Claim(text=note[:600], supports="come e andato il confronto"))

    return CapabilityOutcome(
        status="succeeded" if chosen else "partial",
        observation=note or "Ho messo a confronto quello che avevo.",
        provenance=ResultProvenance(
            source_class="deterministic_computation",
            capability="comparison.run",
            provider="comparison",
            source_refs=([run_id] if run_id else []) + list(research_refs)[:4],
            freshness="fresh",
        ),
        claims=claims[:MAX_CLAIMS],
        data_ref=run_id,
        error_type="" if chosen else "no_clear_choice",
    )


# --- preparing, which changes nothing --------------------------------------

async def prepare_locally(db, owner_id: str, goal, step) -> CapabilityOutcome:
    """Return success only after a source-grounded draft has been persisted."""
    from agent.preparation import prepare
    return await prepare(db, owner_id, goal, step)


async def open_navigation(db, owner_id: str, goal, step) -> CapabilityOutcome:
    """
    The one world-changing capability with a stand-in behind it.

    It stays a stand-in, and says so. Sprint 1 used it to show that the
    "there is already a grant, so proceed" path exists; Sprint 2 must not let
    it be mistaken for evidence that anything happened, so its provenance is
    `simulated` and the completion gate refuses to close a goal on it.
    """
    return CapabilityOutcome(
        status="succeeded",
        observation=(
            f"Fatto (simulato): {step.intent}. "
            "Niente ha davvero raggiunto un servizio esterno."
        )[:600],
        provenance=ResultProvenance(
            source_class="simulated",
            capability="navigation.open",
            certainty_note="non e successo davvero: e una simulazione",
        ),
        claims=[Claim(text=f"Simulato: {step.intent}"[:600])],
        data_ref=f"sim:{step.id}",
    )
