"""Fasi di controllo e verifica, NELL'ORDINE della Circolare 1/2018.

Ogni fase cita il punto della circolare da cui deriva. Le fasi "applicabili" possono essere
dichiarate non applicabili solo con motivazione; l'ordine tra quelle applicabili resta vincolante.
Riferimenti: Vol. II, Parte III (capitoli 1-5) e Vol. IV (allegati).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Fase:
    chiave: str
    titolo: str
    rif: str                       # riferimento alla circolare
    modello: str = ""              # allegato del Vol. IV, se previsto
    atto: str = ""                 # tipo di atto redigibile in questa fase (PVOC, PVV, PVC, CNR)
    facoltativa: bool = False      # puo' essere "non applicabile" con motivazione
    condizionale: bool = False     # scatta solo al verificarsi di una condizione (fuori dal percorso lineare)
    checklist: tuple[str, ...] = field(default_factory=tuple)
    note: str = ""


FASI_CONTROLLO: tuple[Fase, ...] = (
    Fase("prep_autorizzazione", "Preparazione e autorizzazione del controllo",
         "Vol. II, P. III, cap. 4 §3", "All. 23",
         checklist=("Sezioni A (dati identificativi), B (posizione fiscale) e C (selezione e strategie) compilate",
                    "Ragioni giustificative e fonte di innesco indicate (C3)",
                    "Oggetto, arco temporale e tributi indicati (C4)",
                    "Esiti delle banche dati e adesione a istituti di compliance (B5)",
                    "Firme: Capo Pattuglia, Direttore del Controllo (se designato), visto di autorizzazione"),
         note="Il controllo non e' oggetto di programmazione nominativa ma richiede questa scheda."),
    Fase("foglio_servizio", "Foglio di servizio e ordine di controllo",
         "Vol. II, P. III, cap. 4 §4", "All. 8/A-8/B",
         checklist=("Ordine circostanziato ('eseguire un controllo') e, se con accesso, ordine di accedere",
                    "Articoli di legge che legittimano l'esecuzione",
                    "Luogo di esecuzione gia' indicato nella scheda di autorizzazione")),
    Fase("invito", "Invito a presentarsi (se il controllo si svolge presso il Reparto)",
         "Vol. IV, All. 14", "All. 14/A-14/B", atto="INVITO", facoltativa=True,
         checklist=("Destinatario, periodi d'imposta, data e ora",
                    "Documentazione da recare, specifica per la tipologia di controllo",
                    "Ragioni giustificative e diritti art. 12 L. 212/2000",
                    "Sanzioni per inottemperanza e relazione di notificazione (art. 60 DPR 600/73)")),
    Fase("avvio", "Avvio: PVOC del primo giorno",
         "Vol. II, P. III, cap. 4 §4 (rinvio al cap. 3 §1 e §3)", "Fac-simile All. 11-13 adattati", atto="PVOC",
         checklist=("Ordine di controllo notificato; esibizione tessera",
                    "Ragioni e oggetto; informativa diritti e obblighi (art. 12 L. 212/2000, art. 6-bis)",
                    "Possibilita' di delega (art. 63 DPR 600/73) e di assistenza",
                    "Ravvedimento operoso e precisazione che non inibisce la verbalizzazione",
                    "Reparto/articolazione per informazioni e nominativo del Direttore del controllo (art. 7 c.2 lett. a L. 212/2000)",
                    "Documenti esibiti e acquisiti; dichiarazioni della parte")),
    Fase("controllo_contabile", "Controllo contabile", "Vol. II, P. III, cap. 3 §7 (richiamato dal cap. 4 §4)",
         atto="PVOC", facoltativa=True,
         checklist=("Regolare istituzione, formazione, tenuta e conservazione di scritture e registri obbligatori",)),
    Fase("riscontro_materiale", "Controllo sostanziale - riscontro materiale",
         "Vol. II, P. III, cap. 3 §8.a", atto="PVOC", facoltativa=True),
    Fase("coerenza_interna", "Controllo sostanziale - riscontro di coerenza interna",
         "Vol. II, P. III, cap. 3 §8.b.(1)", atto="PVOC", facoltativa=True),
    Fase("coerenza_esterna", "Controllo sostanziale - riscontro di coerenza esterna",
         "Vol. II, P. III, cap. 3 §8.b.(2)", atto="PVOC", facoltativa=True),
    Fase("indiretto_presuntivo", "Controllo sostanziale - riscontro indiretto-presuntivo",
         "Vol. II, P. III, cap. 3 §8.c; Vol. III, P. V, cap. 1", atto="PVOC", facoltativa=True,
         checklist=("Contraddittorio con la parte prima di utilizzare elementi presuntivi",)),
    Fase("analitico_normativo", "Controllo sostanziale - riscontro analitico-normativo",
         "Vol. II, P. III, cap. 3 §8.d; Vol. III, P. V, cap. 3-6", atto="PVOC", facoltativa=True),
    Fase("versamenti", "Riscontro su obblighi di effettuazione/versamento ritenute e liquidazione/versamento imposte",
         "Vol. II, P. III, cap. 3 §8.e", atto="PVOC", facoltativa=True),
    Fase("contraddittorio", "Contraddittorio con il contribuente", "Vol. II, P. III, cap. 3 §4", atto="PVOC",
         checklist=("Consegna dei PVOC redatti in assenza della parte",
                    "Dichiarazioni della parte trascritte")),
    Fase("conclusione_pvc", "Conclusione: processo verbale di constatazione",
         "Vol. II, P. III, cap. 3 §10.a; cap. 4 §5", "All. 19", atto="PVC",
         checklist=("Motivazione dei rilievi; stima dell'imposta evasa (cap. 3 §13)",
                    "Sottoscrizione, rilascio copia al contribuente, trasmissione all'Agenzia delle Entrate")),
    Fase("adempimenti_statistici", "Adempimenti statistici", "Vol. II, P. III, cap. 4 §6"),
    Fase("cnr", "Comunicazione di notizia di reato (se emergono indizi di reato)",
         "Vol. II, P. III, cap. 5 §2-3; art. 220 disp. att. c.p.p.", atto="CNR", condizionale=True,
         checklist=("Atti di p.g. con le forme del c.p.p. dove necessario (art. 357 c.p.p.)",
                    "Comunicazione ex art. 347 c.p.p. con analitica rappresentazione dei fatti")),
)

FASI_VERIFICA: tuple[Fase, ...] = (
    Fase("prep_verifica", "Preparazione: scheda, piano di verifica, foglio di servizio e ordine d'accesso",
         "Vol. II, P. III, cap. 1", "All. 7, 8/A-8/D"),
    Fase("avvio", "Avvio: PVV del primo giorno", "Vol. II, P. III, cap. 3 §1 e §3", "All. 11-13, 14, 16",
         atto="PVV"),
    Fase("aggiorna_piano", "Aggiornamento del piano di verifica", "Vol. II, P. III, cap. 3 §2", atto="PVV",
         facoltativa=True),
    Fase("controllo_contabile", "Controllo contabile", "Vol. II, P. III, cap. 3 §7", atto="PVV", facoltativa=True),
    Fase("riscontro_materiale", "Controllo sostanziale - riscontro materiale",
         "Vol. II, P. III, cap. 3 §8.a", atto="PVV", facoltativa=True),
    Fase("coerenza_interna", "Controllo sostanziale - riscontro di coerenza interna",
         "Vol. II, P. III, cap. 3 §8.b.(1)", atto="PVV", facoltativa=True),
    Fase("coerenza_esterna", "Controllo sostanziale - riscontro di coerenza esterna",
         "Vol. II, P. III, cap. 3 §8.b.(2)", atto="PVV", facoltativa=True),
    Fase("indiretto_presuntivo", "Controllo sostanziale - riscontro indiretto-presuntivo",
         "Vol. II, P. III, cap. 3 §8.c", atto="PVV", facoltativa=True),
    Fase("analitico_normativo", "Controllo sostanziale - riscontro analitico-normativo",
         "Vol. II, P. III, cap. 3 §8.d", atto="PVV", facoltativa=True),
    Fase("versamenti", "Riscontro su obblighi di effettuazione/versamento ritenute e liquidazione/versamento imposte",
         "Vol. II, P. III, cap. 3 §8.e", atto="PVV", facoltativa=True),
    Fase("coordinamento_ade", "Coordinamento tecnico-operativo con l'Agenzia delle Entrate",
         "Vol. II, P. III, cap. 3 §9", facoltativa=True),
    Fase("contraddittorio", "Contraddittorio con il contribuente", "Vol. II, P. III, cap. 3 §4", atto="PVV"),
    Fase("conclusione_pvc", "Conclusione: processo verbale di constatazione",
         "Vol. II, P. III, cap. 3 §10.a", "All. 19", atto="PVC"),
    Fase("stima_imposta", "Stima dell'imposta evasa", "Vol. II, P. III, cap. 3 §13"),
    Fase("adempimenti_statistici", "Adempimenti statistici", "Vol. II, P. III, cap. 3 §12"),
    Fase("misure_cautelari", "Misure cautelari amministrative (se ricorrono i presupposti)",
         "Vol. II, P. III, cap. 3 §11", "All. 22", condizionale=True, facoltativa=True),
    Fase("cnr", "Comunicazione di notizia di reato (se emergono indizi di reato)",
         "Vol. II, P. III, cap. 5 §2-3; art. 220 disp. att. c.p.p.", atto="CNR", condizionale=True),
)

PERCORSI = {"controllo": FASI_CONTROLLO, "verifica": FASI_VERIFICA}
STATI = ("da_fare", "in_corso", "completata", "non_applicabile")


def fasi_per(tipo: str) -> tuple[Fase, ...]:
    return PERCORSI[tipo]


def fase_per_chiave(tipo: str, chiave: str) -> Fase:
    for f in fasi_per(tipo):
        if f.chiave == chiave:
            return f
    raise KeyError(chiave)


class OrdineViolato(Exception):
    pass


def puo_avviare(tipo: str, chiave: str, stati: dict[str, str]) -> None:
    """Solleva OrdineViolato se una fase lineare precedente non e' conclusa (completata o non applicabile)."""
    fase = fase_per_chiave(tipo, chiave)
    if fase.condizionale:
        return
    for f in fasi_per(tipo):
        if f.chiave == chiave:
            return
        if f.condizionale:
            continue
        if stati.get(f.chiave, "da_fare") not in ("completata", "non_applicabile"):
            raise OrdineViolato(f"Prima di «{fase.titolo}» occorre concludere «{f.titolo}» ({f.rif}).")


def puo_dichiarare_non_applicabile(tipo: str, chiave: str) -> bool:
    return fase_per_chiave(tipo, chiave).facoltativa


def prossima_fase(tipo: str, stati: dict[str, str]) -> Fase | None:
    for f in fasi_per(tipo):
        if f.condizionale:
            continue
        if stati.get(f.chiave, "da_fare") not in ("completata", "non_applicabile"):
            return f
    return None
