"""
Canonical vocabulary for the Life Graph.

Kept as plain string enums (subclassing `str, Enum`) so they are JSON-serializable
and comparable to raw strings coming from HTTP. Any string outside these sets
is still tolerated (we normalize into `generic`), keeping the graph forward-
compatible with future integrations.
"""
from __future__ import annotations

from enum import Enum


class NodeType(str, Enum):
    HOME = "home"                # Casa
    CAR = "car"                  # Auto
    PERSON = "person"            # Persona
    JOB = "job"                  # Lavoro
    UNIVERSITY = "university"    # Università / studi
    TRIP = "trip"                # Viaggio
    SUBSCRIPTION = "subscription"  # Abbonamento
    CONTRACT = "contract"        # Contratto
    DOCUMENT = "document"        # Documento
    PURCHASE = "purchase"        # Acquisto
    HEALTH = "health"            # Salute
    PET = "pet"                  # Animale
    GOAL = "goal"                # Obiettivo
    EVENT = "event"              # Evento
    FINANCE = "finance"          # Conto / carta / banca
    GENERIC = "generic"


class RelationType(str, Enum):
    """Semantic type of an edge between two nodes."""
    OWNS = "owns"                # Person → Home, Person → Car
    LIVES_AT = "lives_at"        # Person → Home
    BELONGS_TO = "belongs_to"    # Bill → Home  (a "part-of" relation)
    PAYS_FOR = "pays_for"        # Person → Subscription
    DOCUMENTS = "documents"      # Document → anything (evidences it)
    ASSIGNED_TO = "assigned_to"  # Contract → Person
    HAS_MEMBER = "has_member"    # Job → Person
    RELATED_TO = "related_to"    # symmetric generic link
    PARENT_OF = "parent_of"      # tree edge: Home → Bill
    GENERIC = "generic"


NODE_TYPES = {t.value for t in NodeType}
RELATION_TYPES = {t.value for t in RelationType}


def normalize_node_type(value: str | None) -> str:
    if not value:
        return NodeType.GENERIC.value
    v = value.lower().strip()
    return v if v in NODE_TYPES else NodeType.GENERIC.value


def normalize_relation_type(value: str | None) -> str:
    if not value:
        return RelationType.GENERIC.value
    v = value.lower().strip()
    return v if v in RELATION_TYPES else RelationType.GENERIC.value
