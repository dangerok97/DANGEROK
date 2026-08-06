"""Life Object type catalog — stable string literals."""
from __future__ import annotations

from typing import Literal, Tuple

LifeObjectType = Literal[
    "HOME",
    "VEHICLE",
    "PERSON",
    "JOB",
    "UNIVERSITY",
    "COURSE",
    "PET",
    "UTILITY",
    "INSURANCE",
    "BANK_ACCOUNT",
    "MORTGAGE",
    "SUBSCRIPTION",
    "TRAVEL",
    "DEVICE",
    "INVESTMENT",
    "HEALTH_PROVIDER",
    "COMPANY",
    "FAMILY_MEMBER",
    "CUSTOM",
]

LIFE_OBJECT_TYPES: Tuple[str, ...] = (
    "HOME",
    "VEHICLE",
    "PERSON",
    "JOB",
    "UNIVERSITY",
    "COURSE",
    "PET",
    "UTILITY",
    "INSURANCE",
    "BANK_ACCOUNT",
    "MORTGAGE",
    "SUBSCRIPTION",
    "TRAVEL",
    "DEVICE",
    "INVESTMENT",
    "HEALTH_PROVIDER",
    "COMPANY",
    "FAMILY_MEMBER",
    "CUSTOM",
)

LifeObjectStatus = Literal[
    "active",
    "inactive",
    "archived",
    "merged",
    "proposed",
    "uncertain",
]

# Document type → preferred Life Object type(s) for deterministic reasoning.
DOC_TYPE_TO_OBJECT: dict[str, str] = {
    "rogito": "HOME",
    "contratto_locazione": "HOME",
    "mutuo": "HOME",
    "bolletta": "HOME",
    "contratto_luce": "HOME",
    "polizza_casa": "HOME",
    "libretto": "VEHICLE",
    "polizza_auto": "VEHICLE",
    "prestito_auto": "VEHICLE",
    "piano_di_studi": "UNIVERSITY",
    "calendario_esami": "COURSE",
    "dispensa": "COURSE",
    "busta_paga": "JOB",
    "contratto": "JOB",
}

DOMAIN_TO_OBJECT: dict[str, str] = {
    "casa": "HOME",
    "auto": "VEHICLE",
    "studio": "UNIVERSITY",
    "finanze": "BANK_ACCOUNT",
    "assicurazioni": "INSURANCE",
}
