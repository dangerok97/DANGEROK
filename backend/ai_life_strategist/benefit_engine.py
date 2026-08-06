"""Benefit Engine — every question maps to a concrete user benefit."""
from __future__ import annotations

from typing import Dict, List, Optional, Set

from ai_life_strategist.models import BenefitDescriptor, DomainId

# Benefit catalog: information → what ORA can actually do for the user.
BENEFITS: Dict[str, BenefitDescriptor] = {
    "casa_mutuo_scadenze": BenefitDescriptor(
        code="casa_mutuo_scadenze",
        domain="casa",
        title="Mutuo sotto controllo",
        user_benefit="ORA può ricordarti le rate del mutuo e evitare sorprese di pagamento.",
        requires=["casa.owned", "casa.mutuo"],
        activates_when=["casa.mutuo_importo", "casa.mutuo_scadenza"],
        home_signal="Promemoria rata mutuo",
        proactive_signal="Rata mutuo in arrivo",
    ),
    "casa_bollette": BenefitDescriptor(
        code="casa_bollette",
        domain="casa",
        title="Bollette organizzate",
        user_benefit="ORA può collegare bollette alla casa e segnalarti scadenze utili.",
        requires=["casa.owned"],
        activates_when=["casa.utenze", "doc.bolletta"],
        home_signal="Bollette casa",
        proactive_signal="Bolletta in scadenza",
    ),
    "casa_assicurazione": BenefitDescriptor(
        code="casa_assicurazione",
        domain="casa",
        title="Casa protetta",
        user_benefit="ORA può tenere d’occhio la polizza casa e la scadenza.",
        requires=["casa.owned"],
        activates_when=["casa.assicurazione", "doc.polizza_casa"],
        home_signal="Polizza casa",
        proactive_signal="Rinnovo polizza casa",
    ),
    "casa_documenti": BenefitDescriptor(
        code="casa_documenti",
        domain="casa",
        title="Documenti casa a portata",
        user_benefit="Con il rogito ORA estrae dati utili e crea il profilo Casa senza form.",
        requires=[],
        activates_when=["doc.rogito", "casa.indirizzo"],
        home_signal="Profilo Casa",
        proactive_signal=None,
    ),
    "auto_scadenze": BenefitDescriptor(
        code="auto_scadenze",
        domain="auto",
        title="Auto in regola",
        user_benefit="ORA può avvisarti su revisione, bollo e assicurazione auto.",
        requires=["auto.owned"],
        activates_when=["auto.targa", "auto.assicurazione_scadenza"],
        home_signal="Scadenze auto",
        proactive_signal="Revisione o bollo in arrivo",
    ),
    "auto_documenti": BenefitDescriptor(
        code="auto_documenti",
        domain="auto",
        title="Libretto e polizza",
        user_benefit="Caricando libretto o polizza, ORA organizza i dati auto senza digitare tutto.",
        requires=["auto.owned"],
        activates_when=["doc.libretto", "doc.polizza_auto"],
        home_signal="Documenti auto",
        proactive_signal=None,
    ),
    "finanze_budget": BenefitDescriptor(
        code="finanze_budget",
        domain="finanze",
        title="Spese ricorrenti chiare",
        user_benefit="ORA può evidenziare abbonamenti e uscite ricorrenti (senza accedere al conto).",
        requires=[],
        activates_when=["finanze.spese_ricorrenti", "abbonamenti.list"],
        home_signal="Spese ricorrenti",
        proactive_signal="Uscita ricorrente",
    ),
    "studio_esami": BenefitDescriptor(
        code="studio_esami",
        domain="studio",
        title="Esami sotto controllo",
        user_benefit="ORA può creare un piano di studio e ricordarti le scadenze d’esame.",
        requires=["studio.active"],
        activates_when=["studio.esame", "studio.data_esame"],
        home_signal="Preparazione esame",
        proactive_signal="Sessione di studio suggerita",
    ),
    "studio_universita": BenefitDescriptor(
        code="studio_universita",
        domain="studio",
        title="Percorso universitario",
        user_benefit="ORA collega università, esami e documenti senza un questionario.",
        requires=[],
        activates_when=["studio.universita", "studio.corso"],
        home_signal="Studio",
        proactive_signal=None,
    ),
    "salute_visite": BenefitDescriptor(
        code="salute_visite",
        domain="salute",
        title="Visite e controlli",
        user_benefit="ORA può ricordarti visite mediche e scadenze utili (senza cartelle cliniche complete).",
        requires=[],
        activates_when=["salute.visita", "salute.data"],
        home_signal="Visita medica",
        proactive_signal="Promemoria visita",
    ),
    "assicurazioni_rinnovi": BenefitDescriptor(
        code="assicurazioni_rinnovi",
        domain="assicurazioni",
        title="Polizze in scadenza",
        user_benefit="ORA segnala rinnovi polizza così non resti scoperto.",
        requires=[],
        activates_when=["assicurazioni.tipo", "assicurazioni.scadenza"],
        home_signal="Rinnovo assicurazione",
        proactive_signal="Polizza in scadenza",
    ),
    "famiglia_contatti": BenefitDescriptor(
        code="famiglia_contatti",
        domain="famiglia",
        title="Famiglia nel contesto",
        user_benefit="ORA può collegare eventi e documenti ai familiari che indichi tu.",
        requires=[],
        activates_when=["famiglia.membri"],
        home_signal="Famiglia",
        proactive_signal=None,
    ),
    "lavoro_scadenze": BenefitDescriptor(
        code="lavoro_scadenze",
        domain="lavoro",
        title="Lavoro organizzato",
        user_benefit="ORA tiene traccia di scadenze e documenti lavorativi che condividi.",
        requires=[],
        activates_when=["lavoro.ruolo", "lavoro.datore"],
        home_signal="Lavoro",
        proactive_signal=None,
    ),
    "viaggi_prep": BenefitDescriptor(
        code="viaggi_prep",
        domain="viaggi",
        title="Viaggi preparati",
        user_benefit="ORA può organizzare destinazione, date e checklist viaggio.",
        requires=[],
        activates_when=["viaggi.destinazione", "viaggi.date"],
        home_signal="Preparazione viaggio",
        proactive_signal="Checklist viaggio",
    ),
}


def benefit_for(code: str) -> Optional[BenefitDescriptor]:
    return BENEFITS.get(code)


def benefits_for_domain(domain: str) -> List[BenefitDescriptor]:
    return [b for b in BENEFITS.values() if b.domain == domain]


def available_benefits(known_keys: Set[str], domain: Optional[str] = None) -> List[BenefitDescriptor]:
    out: List[BenefitDescriptor] = []
    for b in BENEFITS.values():
        if domain and b.domain != domain:
            continue
        req = set(b.requires)
        if req and not req.issubset(known_keys):
            continue
        out.append(b)
    return out


def active_benefits(known_keys: Set[str], domain: Optional[str] = None) -> List[BenefitDescriptor]:
    out: List[BenefitDescriptor] = []
    for b in BENEFITS.values():
        if domain and b.domain != domain:
            continue
        act = set(b.activates_when)
        if act and act.issubset(known_keys):
            out.append(b)
            continue
        # Partial activation if majority of activate keys present
        if act and len(act & known_keys) >= max(1, len(act) // 2 + (1 if len(act) > 1 else 0)):
            if set(b.requires).issubset(known_keys):
                out.append(b)
    return out


def pick_best_benefit_for_gap(gap_key: str, domain: DomainId) -> BenefitDescriptor:
    """Map a missing info key to the strongest concrete benefit."""
    domain_bens = benefits_for_domain(domain)
    for b in domain_bens:
        if gap_key in b.requires or gap_key in b.activates_when:
            return b
    # Heuristic by substring
    gk = gap_key.lower()
    for b in domain_bens:
        if any(part in gk for part in b.code.split("_")):
            return b
    if domain_bens:
        return domain_bens[0]
    return BenefitDescriptor(
        code=f"{domain}_generic",
        domain=domain,  # type: ignore[arg-type]
        title="Più contesto per aiutarti",
        user_benefit="Con questa informazione ORA può proporti azioni più utili e meno generiche.",
        requires=[],
        activates_when=[gap_key],
    )


def explain_benefit(code: str) -> str:
    b = benefit_for(code)
    if not b:
        return "Questa informazione aiuta ORA a proporti azioni più utili."
    return b.user_benefit
