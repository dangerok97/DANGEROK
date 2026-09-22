"""
Come si dicono, a una persona, le cose che ORA sa di lei.

    «SITUAZIONE: UN PARTNER» NON È UN RICORDO. È UNA RIGA DI DATABASE.

«Quello che ORA sa già» deve leggersi come memoria: *hai un partner*, *lavori
nella Guardia di Finanza*, *hai un'auto*. Il magazzino — `famiglia.situazione`,
`car_ownership`, `true` — resta dov'è.

Qui c'è un posto solo dove questo si decide, perché la stessa cosa compare in
più schermate e una traduzione sparsa nei componenti diventa dieci traduzioni
diverse della stessa parola. Tre livelli, in ordine:

1. **la frase** (`FRASI`), quando la cosa si dice bene in italiano;
2. **l'etichetta** (`ETICHETTE`), quando serve «Nome: valore»;
3. **il valore** (`come_si_dice_il_valore`), che toglie `true`, `null` e
   `unknown` dalla faccia di chi legge.

E una regola che non è di stile ma di verità: un fatto si mostra in un'area
solo se **appartiene** a quell'area. Vedi `appartiene_all_area`.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

#     I NOMI DELLE COSE, IN ITALIANO.
# Nessun campo interno deve arrivare sotto gli occhi di qualcuno: né `citta`
# senza accento, né `family_core`, né il nome della colonna.
ETICHETTE: Dict[str, str] = {
    # Casa
    "mlc.life_places.home": "Dove vivi",
    "casa.situazione": "Situazione abitativa",
    "casa.citta": "Città",
    "casa.convivenza": "Con chi vivi",
    "casa.mutuo": "Mutuo",
    "casa.mutuo_rata": "Rata del mutuo",
    "casa.affitto_canone": "Affitto",
    "casa.spazio_auto": "Posto auto",
    "casa.utenze": "Utenze",
    "casa.assicurazione": "Assicurazione casa",
    "casa.owned": "Casa di proprietà",
    "doc.bolletta": "Bolletta",
    "doc.rogito": "Rogito",
    # Lavoro
    "mlc.current_situation": "Di cosa ti occupi",
    "lavoro.active": "Lavori",
    "lavoro.tipo": "Tipo di lavoro",
    "lavoro.contratto": "Contratto",
    "lavoro.orario": "Orario",
    "lavoro.modalita": "Dove lavori",
    "lavoro.ruolo": "Ruolo",
    # Studio
    "studio.active": "Studi",
    "studio.tipo": "Percorso",
    "studio.ambito": "Ambito",
    "studio.fase": "A che punto sei",
    "studio.universita": "Università",
    "studio.esame": "Prossimo esame",
    "doc.piano_di_studi": "Piano di studi",
    # Mobilità
    "mobilita.mezzi": "Come ti muovi",
    "auto.rapporto": "Auto",
    "auto.rata": "Rata dell'auto",
    "auto.owned": "Auto di proprietà",
    "auto.assicurazione_scadenza": "Scadenza assicurazione auto",
    "doc.libretto": "Libretto",
    # Famiglia e relazioni
    "mlc.responsibilities": "Di chi ti prendi cura",
    "famiglia.situazione": "Situazione affettiva",
    "famiglia.figli_numero": "Figli",
    "famiglia.membri": "Nucleo familiare",
    "famiglia.partner": "Partner",
    "animali.pet": "Animali",
    # Patrimonio e finanze
    "patrimonio.beni": "Beni",
    "patrimonio.immobili_dettaglio": "Immobili",
    "patrimonio.immobili_altri": "Altri immobili",
    "patrimonio.finanziamenti": "Finanziamenti",
    "patrimonio.risparmi": "Risparmi",
    "finanze.reddito": "Reddito",
    "finanze.spese_ricorrenti": "Spese ricorrenti",
    # Assicurazioni, servizi, salute
    "assicurazioni.tipo": "Polizze",
    "doc.polizza": "Polizza",
    "servizi.fornitori": "Fornitori",
    "abbonamenti.list": "Abbonamenti",
    "salute.obiettivi": "Obiettivi di benessere",
    "salute.visita": "Visite",
}

#     E QUANDO SI PUÒ DIRE MEGLIO, SI DICE MEGLIO.
# `{v}` è il valore già reso in italiano. Una frase qui dentro vince
# sull'etichetta: «Lavori nella Guardia di Finanza» è un ricordo, «Ruolo: nella
# Guardia di Finanza» è un campo.
FRASI: Dict[str, str] = {
    "mlc.life_places.home": "Vivi a {v}",
    "casa.citta": "Vivi a {v}",
    "casa.affitto_canone": "Paghi {v} € di affitto al mese",
    "casa.mutuo_rata": "Paghi {v} € di mutuo al mese",
    "lavoro.ruolo": "Lavori {v}",
    "studio.ambito": "Studi {v}",
    "studio.universita": "Vai all'università",
    "mobilita.mezzi": "Ti muovi {v}",
    "auto.rata": "Paghi {v} € al mese per l'auto",
    "famiglia.membri": "Nucleo familiare: {v}",
    "finanze.reddito": "Reddito {v} al mese",
}

#     E ALCUNE SCELTE SI DICONO MEGLIO UNA PER UNA.
# «Situazione affettiva: Un partner» è un modulo compilato; «Hai un partner» è
# una cosa che qualcuno si ricorda di te. Qui stanno solo le scelte che si
# possono dire in modo naturale **e** neutro: dove servirebbe sapere il genere
# di chi legge — «sposato/a» — non si scrive niente e resta l'etichetta, che è
# meno bella ma non sbaglia.
FRASI_SCELTA: Dict[str, Dict[str, str]] = {
    "famiglia.situazione": {
        "Un partner": "Hai un partner",
        "Figli": "Hai figli",
        "Genitori di cui ti occupi": "Ti occupi dei tuoi genitori",
        "Altri familiari vicini": "Hai altri familiari vicini",
    },
    "casa.situazione": {
        "Casa di proprietà": "Vivi in una casa di proprietà",
        "Casa in affitto": "Vivi in affitto",
        "Vivo con familiari": "Vivi con familiari",
        "Ospite / uso gratuito": "Vivi in una casa in uso gratuito",
    },
    "casa.convivenza": {
        "Da solo": "Vivi da solo",
        "Con il partner": "Vivi con il partner",
        "Con la famiglia": "Vivi con la famiglia",
        "Con coinquilini": "Vivi con coinquilini",
    },
    "lavoro.modalita": {
        "In sede": "Lavori in sede",
        "Ibrido": "Lavori in modalità ibrida",
        "Da remoto": "Lavori da remoto",
        "In giro / presso clienti": "Lavori in giro, dai clienti",
    },
    "auto.rapporto": {
        "Di proprietà": "L'auto è di tua proprietà",
        "Leasing": "Hai l'auto in leasing",
        "Noleggio a lungo termine": "Hai l'auto a noleggio a lungo termine",
        "Aziendale": "Hai un'auto aziendale",
        "Di un familiare": "Usi l'auto di un familiare",
    },
    "mobilita.mezzi": {
        "Auto": "Hai un'auto",
        "Moto o scooter": "Ti muovi in moto o scooter",
        "Trasporto pubblico": "Ti muovi con i mezzi pubblici",
        "Bicicletta": "Ti muovi in bicicletta",
        "A piedi": "Ti muovi a piedi",
    },
}

#     I SÌ E I NO CHE SI DICONO CON UNA FRASE INTERA.
# «Lavori: Sì» è una riga di modulo. Quando un sì vuol dire una cosa sola, la
# cosa si dice per intero — e quando è un no si dice il no, non si nasconde.
FRASI_SI_NO: Dict[str, Tuple[str, str]] = {
    "lavoro.active": ("Lavori", "Non lavori in questo periodo"),
    "studio.active": ("Stai studiando", "Non stai studiando"),
    "studio.universita": ("Vai all'università", "Non vai all'università"),
    "famiglia.partner": ("Hai un partner", "Non hai un partner"),
    "casa.owned": ("La casa è di tua proprietà", "La casa non è di tua proprietà"),
    "auto.owned": ("Hai un'auto", "Non hai un'auto"),
    "casa.mutuo": ("Hai un mutuo", "Non hai un mutuo"),
    "casa.assicurazione": (
        "Hai un'assicurazione sulla casa",
        "Non hai un'assicurazione sulla casa",
    ),
    "patrimonio.finanziamenti": ("Hai finanziamenti in corso", "Non hai finanziamenti"),
}

#     QUELLO CHE NON SI MOSTRA MAI.
# Un valore tecnico non diventa un fatto solo perché è arrivato fin qui: se non
# si sa che cosa vuol dire, non lo si dice. Meglio una riga in meno che una
# riga che chi legge non può né capire né correggere.
VALORI_MUTI = {
    "", "none", "null", "nan", "unknown", "sconosciuto", "n/a", "na",
    "undefined", "other", "altro_non_specificato",
}

_SI = "Sì"
_NO = "No"


def come_si_dice_il_valore(valore: Any) -> str:
    """Il valore come lo legge una persona, o vuoto se non si può dire."""
    if valore is None:
        return ""
    if isinstance(valore, bool):
        return _SI if valore else _NO
    if isinstance(valore, (int, float)):
        return str(valore)
    if isinstance(valore, str):
        pulito = valore.strip()
        if pulito.lower() in VALORI_MUTI:
            return ""
        # `true`/`false` arrivano anche come stringhe, da chi li ha scritti
        # leggendo un modulo.
        if pulito.lower() in ("true", "vero"):
            return _SI
        if pulito.lower() in ("false", "falso"):
            return _NO
        return pulito[:120]
    if isinstance(valore, (list, tuple, set)):
        pezzi = [come_si_dice_il_valore(v) for v in valore]
        return ", ".join(p for p in pezzi if p)[:120]
    if isinstance(valore, dict):
        for chiave in ("label", "name", "title", "value", "city"):
            if valore.get(chiave):
                return come_si_dice_il_valore(valore[chiave])
    return ""


#     UN DOCUMENTO NON SI MOSTRA CON IL SUO CODICE.
# «Polizza: doc_bd558d6789de» non dice niente a nessuno: il fatto vero è che
# quel documento c'è, e quello si può dire. L'identificativo resta dove serve,
# cioè dentro.
FRASI_DOCUMENTO: Dict[str, str] = {
    "doc.polizza": "Hai caricato una polizza",
    "doc.polizza_casa": "Hai caricato la polizza della casa",
    "doc.polizza_auto": "Hai caricato la polizza dell'auto",
    "doc.bolletta": "Hai caricato una bolletta",
    "doc.rogito": "Hai caricato il rogito",
    "doc.libretto": "Hai caricato il libretto dell'auto",
    "doc.piano_di_studi": "Hai caricato il piano di studi",
    "doc.referti": "Hai caricato dei referti",
    "doc.fattura": "Hai caricato una fattura",
}


def _pare_un_codice(valore: str) -> bool:
    """Un identificativo interno travestito da fatto: `doc_…`, `gol_…`, un UUID."""
    pulito = (valore or "").strip()
    if not pulito or " " in pulito:
        return False
    return (
        "_" in pulito and len(pulito) >= 12 and any(c.isdigit() for c in pulito)
    ) or (len(pulito) >= 24 and pulito.isalnum())


#     LO ZERO È UNA NOTIZIA, NON UN CAMPO VUOTO.
# «Figli: 0» si legge come un modulo; «Non hai figli» è quello che ORA sa.
FRASI_ZERO: Dict[str, str] = {
    "famiglia.figli_numero": "Non hai figli",
    "patrimonio.immobili_altri": "Non hai altri immobili",
}


def come_si_dice_il_fatto(ref: str, valore_detto: str) -> Optional[str]:
    """
    La frase intera per questo fatto, quando esiste. Altrimenti `None`.

    Non si inventa: se per questo riferimento non c'è una frase scritta, chi
    chiama ripiega su «Etichetta: valore», che è meno bello ma vero.
    """
    if not valore_detto:
        return None
    documento = FRASI_DOCUMENTO.get(ref)
    if documento:
        return documento

    if valore_detto.strip() in ("0", "0.0") and ref in FRASI_ZERO:
        return FRASI_ZERO[ref]

    #     UNA SCELTA SOLA SI DICE PER INTERO; DUE RESTANO UN ELENCO.
    # «Hai un'auto» funziona quando l'auto è tutto quello che c'è; con «Auto,
    # Bicicletta» la frase diventerebbe una bugia per metà, e allora si elenca.
    scelte = FRASI_SCELTA.get(ref)
    if scelte and "," not in valore_detto:
        detta = scelte.get(valore_detto)
        if detta:
            return detta

    si_no = FRASI_SI_NO.get(ref)
    if si_no and valore_detto in (_SI, _NO):
        return si_no[0] if valore_detto == _SI else si_no[1]
    modello = FRASI.get(ref)
    if modello:
        return modello.format(v=valore_detto)
    return None


def come_si_chiama(ref: str, ripiego: str = "") -> str:
    """L'etichetta umana di un riferimento, o il ripiego di chi chiama."""
    etichetta = ETICHETTE.get(ref)
    if etichetta:
        return etichetta
    return ripiego


#     L'APPARTENENZA: UN FATTO DI LAVORO NON È UN FATTO DI FAMIGLIA.
#
# Misurato in app (V3.21.3d): sotto «Famiglia e relazioni» compariva «Di chi ti
# prendi cura: nella Guardia di Finanza». Il valore era giusto — quello che
# l'estrattore aveva scritto — ma la cosa, letta lì, diceva una falsità sulla
# vita di qualcuno.
#
# La regola non guarda le parole: guarda chi possiede il riferimento. Un
# riferimento appartiene all'area il cui dominio è il suo primo pezzo
# (`famiglia.*` → Famiglia). I riferimenti trasversali — il Minimum Life
# Context, i documenti — non appartengono a nessuna area da soli: si mostrano
# solo dove una relazione canonica li lega, e quella relazione è scritta qui.
RELAZIONI_CANONICHE: Dict[str, str] = {
    # Dove una persona vive *è* la sua casa: relazione forte, non una somiglianza.
    "mlc.life_places.home": "casa",
    "doc.bolletta": "casa",
    "doc.rogito": "casa",
    "doc.piano_di_studi": "studio",
    "doc.libretto": "mobilita",
    "doc.polizza": "assicurazioni",
}

# I domini che un'area possiede, oltre al suo stesso identificativo.
DOMINI_DI_AREA: Dict[str, Tuple[str, ...]] = {
    "casa": ("casa",),
    "lavoro": ("lavoro",),
    "studio": ("studio",),
    "mobilita": ("mobilita", "auto"),
    "famiglia": ("famiglia", "animali"),
    "patrimonio": ("patrimonio",),
    "finanze": ("finanze",),
    "assicurazioni": ("assicurazioni",),
    "servizi": ("servizi", "abbonamenti"),
    "salute": ("salute",),
}


def appartiene_all_area(ref: str, area_id: str) -> bool:
    """
    Se questo fatto si può mostrare sotto quest'area.

        NEL DUBBIO, NON SI MOSTRA.

    Appartiene quando il dominio del riferimento è uno dei domini dell'area, o
    quando una relazione canonica lo lega a quell'area. Tutto il resto — un
    riferimento trasversale senza relazione scritta, un dominio che non si
    riconosce — resta fuori: una riga in meno non ha mai detto una bugia.
    """
    pulito = (ref or "").strip()
    if not pulito or not area_id:
        return False
    legato = RELAZIONI_CANONICHE.get(pulito)
    if legato:
        return legato == area_id
    dominio = pulito.split(".", 1)[0]
    return dominio in DOMINI_DI_AREA.get(area_id, ())
