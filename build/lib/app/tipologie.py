"""Tipologie di controllo e documenti da richiedere con l'invito a presentarsi.

Le liste documenti derivano dalla prassi del Reparto (inviti d'esempio) e vanno confrontate con la
normativa in vigore. NB: la Circolare 1/2018 e' del 2017 e non tratta i bonus edilizi/superbonus:
per quelle tipologie servono le fonti normative successive, da fornire e versionare.
"""
from __future__ import annotations

TIPOLOGIE: dict[str, dict] = {
    "generica": {"nome": "Generica", "documenti": ["Libri, registri, scritture e documenti attinenti all'attivita' esercitata"]},
    "verifica_contabilita": {
        "nome": "Verifica con esame della contabilita' (invito a presentarsi)",
        "base_normativa_invito": "art. 32, c. 1, nn. 2) e 3) DPR 600/1973 e art. 51, c. 2, nn. 2) e 3) DPR 633/1972 e art. 2 D.Lgs. 68/2001",
        "documenti": ["Registri IVA degli acquisti e delle fatture emesse", "Registri degli incassi e dei pagamenti",
                      "Fatture di acquisto", "Fatture di vendita", "Registro dei beni ammortizzabili"],
    },
    "inversione_contabile": {
        "nome": "Inversione contabile (reverse charge)",
        "documenti": ["Copia cartacea ovvero in formato .pdf delle fatture elettroniche di acquisto e di vendita "
                      "relative ai periodi d'imposta oggetto di controllo"],
    },
    "regime_forfettario": {
        "nome": "Verifica requisiti regime forfettario",
        "documenti": ["Fatture di vendita e di acquisto dei periodi d'imposta oggetto di controllo",
                      "Dichiarazioni dei redditi presentate"],
    },
    "crediti_bonus_edilizi": {
        "nome": "Crediti d'imposta da cessione di bonus edilizi (es. Superbonus)",
        "documenti": [
            "Contratto di cessione dei crediti oggetto del controllo",
            "Prova del pagamento del corrispettivo",
            "Ricevuta della comunicazione telematica all'Agenzia delle Entrate relativa alla cessione del credito",
            "Ricevuta di accettazione del credito nel cassetto fiscale del cessionario",
            "Estratto conto del cassetto fiscale (presa in carico, disponibilita', utilizzo in compensazione con F24)",
            "Modelli F24 con i codici tributo utilizzati e relative ricevute telematiche",
            "Documentazione identificativa del credito acquistato (codice identificativo, annualita', importo residuo)",
            "Scritture contabili che registrano l'acquisto del credito e il successivo utilizzo in compensazione",
            "Titolo edilizio abilitativo o dichiarazione sostitutiva (edilizia libera), con data di inizio lavori",
            "Notifica preliminare all'ASL o dichiarazione sostitutiva nei casi di esclusione",
            "Visura catastale ante operam o storica, o domanda di accatastamento",
            "Fatture, ricevute e documenti comprovanti spese e pagamenti",
            "Asseverazioni dei tecnici abilitati (requisiti tecnici e congruita' delle spese) con ricevute di deposito",
            "Per parti comuni condominiali: delibera di approvazione e tabella di ripartizione delle spese",
            "Documentazione tecnica specifica (efficienza energetica / rischio sismico) o dichiarazione sostitutiva",
            "Visto di conformita'",
            "Attestazioni di osservanza degli obblighi antiriciclaggio (artt. 35 e 42 D.Lgs. 231/2007)",
            "Contratto di appalto tra esecutore dei lavori e committente",
            "Fatture di vendita con oggetto 'sconto in fattura' relative al Superbonus, inerenti ai crediti citati",
        ],
    },
}


def elenco() -> list[tuple[str, str]]:
    return [(k, v["nome"]) for k, v in TIPOLOGIE.items()]
