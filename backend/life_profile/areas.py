"""
The parts of a life ORA tries to understand.

An area is a *grouping for a person to recognise*, not a flow and not a schema.
It says which parts of life are worth knowing something about and roughly how
much each one helps; it says nothing about what to ask, in what order, or how
many questions there are. That belongs to guidance, one turn at a time.

The knowledge itself is not defined here either. `ai_life_strategist`'s
`DOMAIN_GAPS` has been the declarative catalogue of what is worth knowing since
long before this module existed — with weights and dependencies already on it —
and a second catalogue would be a second truth. Areas map onto those domains
and nothing more.

Two domains are deliberately unmapped. `documenti` is a surface, not a part of
a life: its gaps are prompts to upload things, and counting them would make the
profile look emptier the more ORA already knows. `viaggi` is an activity rather
than a standing fact about someone, and a trip that ended does not leave a hole
in a life profile.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

# How personal an area is. It changes how ORA opens the subject — never
# whether the person is allowed to skip it, which is always.
Sensitivity = str  # "normal" | "sensitive"


class LifeArea(BaseModel):
    """What ORA tries to understand about one part of someone's life."""

    id: str
    title: str
    description: str
    # A presentation key, not an asset path: the interface owns its own icons.
    icon_key: str
    # Which gap domains this area draws its knowledge objectives from.
    domains: Tuple[str, ...]
    sensitivity: Sensitivity = "normal"
    # Relative contribution to the overall figure. A life is not evenly
    # weighted: where someone lives explains more than which streaming
    # services they pay for.
    weight: float = 1.0
    order: int = 0


LIFE_AREAS: Tuple[LifeArea, ...] = (
    LifeArea(
        id="casa",
        title="Casa",
        description="Dove vivi, con chi, e come la gestisci.",
        icon_key="home",
        domains=("casa",),
        weight=1.3,
        order=1,
    ),
    LifeArea(
        id="lavoro",
        title="Lavoro",
        description="Cosa fai e come lavori.",
        icon_key="work",
        domains=("lavoro",),
        weight=1.2,
        order=2,
    ),
    LifeArea(
        # Its own part of a life, not a footnote of work: somebody can study
        # without working and work without studying, and each needs its own
        # "no" for the other's questions to stop.
        id="studio",
        title="Studio",
        description="Il percorso che stai seguendo.",
        icon_key="study",
        domains=("studio",),
        weight=0.9,
        order=3,
    ),
    LifeArea(
        id="mobilita",
        title="Mobilità",
        description="Come ti sposti e cosa serve per farlo.",
        icon_key="car",
        domains=("auto",),
        weight=1.0,
        order=4,
    ),
    LifeArea(
        id="famiglia",
        title="Famiglia e relazioni",
        description="Le persone che contano nella tua vita.",
        icon_key="people",
        domains=("famiglia", "animali"),
        weight=1.1,
        order=5,
    ),
    LifeArea(
        # Money as it moves: what goes out every month. Standing possessions
        # live next door in Patrimonio, because they change what is realistic
        # in a different way — and because somebody willing to talk about their
        # bills is not necessarily willing to talk about their savings.
        id="finanze",
        title="Finanze",
        description="Le spese ricorrenti, per consigli realistici.",
        icon_key="finance",
        domains=("finanze",),
        sensitivity="sensitive",
        weight=1.0,
        order=7,
    ),
    LifeArea(
        id="patrimonio",
        title="Patrimonio",
        description="Quello che possiedi oltre alla casa in cui vivi.",
        icon_key="assets",
        domains=("patrimonio",),
        sensitivity="sensitive",
        weight=0.9,
        order=6,
    ),
    LifeArea(
        id="assicurazioni",
        title="Assicurazioni",
        description="Cosa è coperto, e fino a quando.",
        icon_key="shield",
        domains=("assicurazioni",),
        weight=0.9,
        order=8,
    ),
    LifeArea(
        id="servizi",
        title="Utenze e servizi",
        description="Luce, gas, internet e gli abbonamenti che paghi ogni mese.",
        icon_key="services",
        domains=("abbonamenti",),
        weight=0.8,
        order=9,
    ),
    LifeArea(
        id="salute",
        title="Salute e benessere",
        description="Quello che ti aiuta a prenderti cura di te.",
        icon_key="health",
        domains=("salute",),
        sensitivity="sensitive",
        weight=0.9,
        order=10,
    ),
)

_BY_ID: Dict[str, LifeArea] = {a.id: a for a in LIFE_AREAS}
_BY_DOMAIN: Dict[str, LifeArea] = {d: a for a in LIFE_AREAS for d in a.domains}


def all_areas() -> List[LifeArea]:
    return sorted(LIFE_AREAS, key=lambda a: a.order)


def area(area_id: str) -> Optional[LifeArea]:
    return _BY_ID.get((area_id or "").strip().lower())


def area_for_domain(domain: str) -> Optional[LifeArea]:
    """Which area a piece of knowledge belongs to, or None when it belongs to none."""
    return _BY_DOMAIN.get((domain or "").strip().lower())
