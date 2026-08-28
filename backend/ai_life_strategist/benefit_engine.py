"""Benefit Engine — every question maps to a concrete Italian user benefit."""
from __future__ import annotations

from typing import Dict, List, Optional, Set

from ai_life_strategist.models import BenefitDescriptor, DomainId

# Benefit catalog: information → what ORA can actually do (Italian Home/Proactive copy).
# Chains: Casa→mutuo→scadenze→calendar→goal→proactive;
# Auto→libretto→assicurazione→revisione→bollo→reminder;
# Università→piano studi→esami→docs→study plan.
BENEFITS: Dict[str, BenefitDescriptor] = {
    "casa_mutuo_scadenze": BenefitDescriptor(
        code="casa_mutuo_scadenze",
        grounded_by=['casa.mutuo_scadenza', 'casa.mutuo_rata', 'doc.mutuo'],
        domain="casa",
        title="Mutuo sotto controllo",
        user_benefit="ORA può ricordarti le rate del mutuo e evitare sorprese di pagamento.",
        requires=["casa.owned"],
        activates_when=["casa.mutuo", "casa.mutuo_scadenza", "casa.mutuo_importo"],
        home_signal="Adesso posso seguire il tuo mutuo.",
        proactive_signal="Posso ricordarti la prossima rata del mutuo — così non arriva a sorpresa.",
        chain="casa→mutuo→scadenze→calendar→goal→proactive",
    ),
    "casa_bollette": BenefitDescriptor(
        code="casa_bollette",
        grounded_by=['doc.bolletta', 'casa.fornitore_energia', 'casa.bolletta_scadenza'],
        domain="casa",
        title="Bollette organizzate",
        user_benefit="ORA può collegare bollette alla casa e segnalarti scadenze utili.",
        requires=["casa.owned"],
        activates_when=["casa.utenze", "doc.bolletta"],
        home_signal="Adesso posso tenere d’occhio le bollette di casa.",
        proactive_signal="Posso segnalarti una bolletta in scadenza collegata alla tua casa.",
        chain="casa→utenze→bollette→scadenze",
    ),
    "casa_assicurazione": BenefitDescriptor(
        code="casa_assicurazione",
        grounded_by=['doc.polizza_casa', 'casa.assicurazione_scadenza'],
        domain="casa",
        title="Casa protetta",
        user_benefit="ORA può tenere d’occhio la polizza casa e la scadenza.",
        requires=["casa.owned"],
        activates_when=["casa.assicurazione", "doc.polizza_casa"],
        home_signal="Adesso posso monitorare la polizza della casa.",
        proactive_signal="Posso avvisarti prima del rinnovo della polizza casa.",
        chain="casa→assicurazione→rinnovo",
    ),
    "casa_documenti": BenefitDescriptor(
        code="casa_documenti",
        domain="casa",
        title="Documenti casa a portata",
        user_benefit="Con il rogito ORA estrae dati utili e crea il profilo Casa senza form.",
        # Owning a home makes this worth offering; only an actual document
        # makes it true. Home used to say "adesso posso usare i documenti della
        # tua casa" to somebody who had never uploaded one — ORA claiming a
        # capability it did not have, which is the one thing a page about trust
        # cannot do.
        requires=["casa.owned"],
        activates_when=["doc.rogito"],
        home_signal="Adesso posso usare i documenti della tua casa.",
        proactive_signal="Se vuoi, puoi aggiungere il rogito: posso collegare scadenze e obiettivi alla tua casa.",
        chain="casa→rogito→profilo→scadenze",
    ),
    "auto_scadenze": BenefitDescriptor(
        code="auto_scadenze",
        grounded_by=['auto.assicurazione_scadenza', 'auto.revisione_scadenza', 'auto.bollo_scadenza', 'doc.libretto'],
        domain="auto",
        title="Auto in regola",
        user_benefit="ORA può avvisarti su revisione, bollo e assicurazione auto.",
        requires=["auto.owned"],
        activates_when=["auto.assicurazione_scadenza", "auto.targa", "doc.libretto"],
        home_signal="Adesso posso seguire le scadenze della tua auto.",
        proactive_signal="Posso ricordarti revisione, bollo o assicurazione auto.",
        chain="auto→libretto→assicurazione→revisione→bollo→reminder",
    ),
    "auto_documenti": BenefitDescriptor(
        code="auto_documenti",
        domain="auto",
        title="Libretto e polizza",
        user_benefit="Caricando libretto o polizza, ORA organizza i dati auto senza digitare tutto.",
        requires=["auto.owned"],
        activates_when=["doc.libretto", "doc.polizza_auto"],
        home_signal="Adesso posso organizzare i documenti della tua auto.",
        proactive_signal="Con libretto e polizza posso tenerti in regola senza moduli.",
        chain="auto→libretto→polizza→scadenze",
    ),
    "finanze_budget": BenefitDescriptor(
        code="finanze_budget",
        domain="finanze",
        title="Spese ricorrenti chiare",
        user_benefit="ORA può evidenziare abbonamenti e uscite ricorrenti (senza accedere al conto).",
        requires=[],
        activates_when=["finanze.spese_ricorrenti", "abbonamenti.list"],
        home_signal="Adesso posso aiutarti con le spese ricorrenti.",
        proactive_signal="Posso segnalarti un’uscita ricorrente importante — senza accedere al conto.",
        chain="finanze→spese→promemoria",
    ),
    "studio_esami": BenefitDescriptor(
        code="studio_esami",
        grounded_by=['studio.esame', 'doc.piano_di_studi'],
        domain="studio",
        title="Esami sotto controllo",
        user_benefit="ORA può creare un piano di studio e ricordarti le scadenze d’esame.",
        requires=["studio.active"],
        activates_when=["studio.esame", "studio.data_esame", "doc.piano_di_studi", "doc.dispensa"],
        home_signal="Adesso posso aiutarti a preparare gli esami.",
        proactive_signal="Posso proporti una sessione di studio in base al tuo piano.",
        chain="università→piano studi→esami→docs→study plan",
    ),
    "studio_universita": BenefitDescriptor(
        code="studio_universita",
        grounded_by=["studio.universita", "studio.corso", "doc.piano_di_studi"],
        domain="studio",
        title="Percorso universitario",
        user_benefit="ORA collega università, esami e documenti senza un questionario.",
        requires=[],
        activates_when=["studio.universita", "studio.active", "studio.corso"],
        home_signal="Adesso posso seguire il tuo percorso di studio.",
        proactive_signal="Posso collegare università, esami e documenti al tuo piano.",
        chain="università→piano studi→esami→docs→study plan",
    ),
    "salute_visite": BenefitDescriptor(
        code="salute_visite",
        grounded_by=['salute.visita_data', 'doc.referti'],
        domain="salute",
        title="Visite e controlli",
        user_benefit="ORA può ricordarti visite mediche e scadenze utili (senza cartelle cliniche complete).",
        requires=[],
        activates_when=["salute.visita", "salute.data"],
        home_signal="Adesso posso ricordarti le visite mediche.",
        proactive_signal="Posso ricordarti una visita in arrivo — senza dati clinici sensibili.",
        chain="salute→visita→promemoria",
    ),
    "assicurazioni_rinnovi": BenefitDescriptor(
        code="assicurazioni_rinnovi",
        grounded_by=['doc.polizza', 'doc.polizza_casa', 'doc.polizza_auto', 'assicurazioni.scadenza'],
        domain="assicurazioni",
        title="Polizze in scadenza",
        user_benefit="ORA segnala rinnovi polizza così non resti scoperto.",
        requires=[],
        activates_when=["assicurazioni.tipo", "assicurazioni.scadenza"],
        home_signal="Adesso posso monitorare i rinnovi delle polizze.",
        proactive_signal="Posso avvisarti prima che scada una polizza.",
        chain="assicurazioni→scadenza→rinnovo",
    ),
    "famiglia_contatti": BenefitDescriptor(
        code="famiglia_contatti",
        domain="famiglia",
        title="Famiglia nel contesto",
        user_benefit="ORA può collegare eventi e documenti ai familiari che indichi tu.",
        requires=[],
        activates_when=["famiglia.membri"],
        home_signal="Adesso posso collegare eventi alla tua famiglia.",
        proactive_signal=None,
        chain="famiglia→contatti→eventi",
    ),
    "lavoro_scadenze": BenefitDescriptor(
        code="lavoro_scadenze",
        grounded_by=['lavoro.scadenza', 'doc.contratto_lavoro'],
        domain="lavoro",
        title="Lavoro organizzato",
        user_benefit="ORA tiene traccia di scadenze e documenti lavorativi che condividi.",
        requires=[],
        activates_when=["lavoro.ruolo", "lavoro.datore"],
        home_signal="Adesso posso tenere d’occhio le scadenze di lavoro.",
        proactive_signal=None,
        chain="lavoro→scadenze",
    ),
    "viaggi_prep": BenefitDescriptor(
        code="viaggi_prep",
        domain="viaggi",
        title="Viaggi preparati",
        user_benefit="ORA può organizzare destinazione, date e checklist viaggio.",
        requires=[],
        activates_when=["viaggi.destinazione", "viaggi.date"],
        home_signal="Adesso posso aiutarti a preparare i viaggi.",
        proactive_signal="Posso proporti una checklist per il tuo prossimo viaggio.",
        chain="viaggi→checklist→date",
    ),
    "animali_cure": BenefitDescriptor(
        code="animali_cure",
        grounded_by=['animali.vaccino_scadenza', 'doc.libretto_animale'],
        domain="animali",
        title="Animali seguiti",
        user_benefit="ORA può ricordarti vaccinazioni e visite veterinarie.",
        requires=[],
        activates_when=["animali.pet"],
        home_signal="Adesso posso ricordarti le cure dei tuoi animali.",
        proactive_signal="Posso ricordarti una visita veterinaria in arrivo.",
        chain="animali→visite→promemoria",
    ),
    "abbonamenti_scadenze": BenefitDescriptor(
        code="abbonamenti_scadenze",
        grounded_by=['abbonamenti.scadenza', 'doc.abbonamento'],
        domain="abbonamenti",
        title="Abbonamenti sotto controllo",
        user_benefit="ORA può segnalarti rinnovi e costi di abbonamenti che indichi tu.",
        requires=[],
        activates_when=["abbonamenti.list"],
        home_signal="Adesso posso seguire i tuoi abbonamenti.",
        proactive_signal="Posso segnalarti un abbonamento in rinnovo.",
        chain="abbonamenti→rinnovi",
    ),
}


def benefit_for(field_or_code: str) -> Optional[BenefitDescriptor]:
    return BENEFITS.get(field_or_code)


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
    """Benefits ORA can already deliver — used for Home / Proactive Italian cards."""
    out: List[BenefitDescriptor] = []
    for b in BENEFITS.values():
        if domain and b.domain != domain:
            continue
        act = set(b.activates_when)
        if not act:
            continue
        hit = act & known_keys
        if not hit:
            continue
        # A claim needs the knowledge it rests on.
        #
        # Found live: somebody answered “sì” to “hai una polizza sulla casa?” and
        # Home announced “adesso posso monitorare la polizza casa e la scadenza” —
        # while ORA held one boolean and no company, no premium, no date. The
        # existence of a thing is not the same as knowing enough about it to
        # watch it, and a benefit that says what it rests on is only claimed
        # once that is there.
        if b.grounded_by and not (set(b.grounded_by) & known_keys):
            continue
        # Activate if any activate key present and requires satisfied
        if set(b.requires).issubset(known_keys):
            out.append(b)
            continue
        # Or majority of activate keys
        if len(hit) >= max(1, (len(act) + 1) // 2):
            out.append(b)
    return out


def pick_best_benefit_for_gap(gap_key: str, domain: DomainId) -> BenefitDescriptor:
    """Map a missing info key to the strongest concrete benefit."""
    domain_bens = benefits_for_domain(domain)
    for b in domain_bens:
        if gap_key in b.requires or gap_key in b.activates_when:
            return b
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
        home_signal="Adesso posso aiutarti meglio con ciò che mi hai raccontato.",
    )


def explain_benefit(code: str) -> str:
    b = benefit_for(code)
    if not b:
        return "Questa informazione aiuta ORA a proporti azioni più utili."
    return b.user_benefit


def home_benefit_cards(known_keys: Set[str], *, limit: int = 6) -> List[BenefitDescriptor]:
    """Benefits ready for Home — Italian home_signal required."""
    active = active_benefits(known_keys)
    cards = [b for b in active if b.home_signal]
    # Prefer chain-relevant order: casa, auto, studio first if present
    priority = {"casa": 0, "auto": 1, "studio": 2, "assicurazioni": 3, "finanze": 4}
    cards.sort(key=lambda b: (priority.get(b.domain, 9), b.code))
    return cards[:limit]


def proactive_benefit_suggestions(known_keys: Set[str], *, limit: int = 4) -> List[BenefitDescriptor]:
    active = active_benefits(known_keys)
    cards = [b for b in active if b.proactive_signal]
    return cards[:limit]
