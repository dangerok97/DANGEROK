"""Document Schema Registry — Iterazione 22.

Central, extensible registry that maps ``type_key`` → ``DocumentSchema``.
Each schema declares the semantic fields the Document Understanding Engine
should try to resolve from a document of that type, plus classifier hints
(keywords with weights) and coherence-required fields.

Fully deterministic — NO LLM. Extending the engine with a new document
type is a matter of ``register_document_type(schema, resolver=…)`` — no
existing code needs to change.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

# Semantic field types recognised by the resolver.
FieldType = str  # date|time|amount|iban|tax_id|phone|email|url|person|place|number|text


@dataclass
class SchemaField:
    key: str                                  # canonical key ("event_date")
    label: str                                # italian UI label ("Data evento")
    type: FieldType                           # semantic type driving candidate matching
    aliases: List[str] = field(default_factory=list)  # labels seen in real docs
    context_labels: List[str] = field(default_factory=list)  # words biasing selection
    priority: int = 50                        # 0..100, higher = shown earlier
    required: bool = False                    # required for a "coherent" specific type


@dataclass
class DocumentSchema:
    type_key: str
    type_label: str
    fields: List[SchemaField]
    info_order: List[str] = field(default_factory=list)         # Info tab ordering
    classifier_keywords: Dict[str, float] = field(default_factory=dict)  # kw→weight
    coherence_required: List[str] = field(default_factory=list) # subset of field keys
    version: int = 1


# ---------------------------------------------------------------------
# Registry — module-level, populated lazily via _init_default_schemas().
# ---------------------------------------------------------------------
_SCHEMAS: Dict[str, DocumentSchema] = {}
_RESOLVERS: Dict[str, Callable[..., Any]] = {}


def register_document_type(
    schema: DocumentSchema,
    resolver: Optional[Callable[..., Any]] = None,
) -> None:
    _SCHEMAS[schema.type_key] = schema
    if resolver is not None:
        _RESOLVERS[schema.type_key] = resolver


def get_schema(type_key: str) -> Optional[DocumentSchema]:
    return _SCHEMAS.get(type_key)


def all_schemas() -> Dict[str, DocumentSchema]:
    return dict(_SCHEMAS)


def get_resolver(type_key: str) -> Optional[Callable[..., Any]]:
    return _RESOLVERS.get(type_key)


# ---------------------------------------------------------------------
# Initial schemas
# ---------------------------------------------------------------------
def _init_default_schemas() -> None:
    # ---- BIGLIETTO ----------------------------------------------------
    register_document_type(DocumentSchema(
        type_key="ticket",
        type_label="Biglietto",
        fields=[
            SchemaField("event_title", "Evento", "text",
                        ["evento", "concerto", "spettacolo", "tour", "manifestazione"],
                        context_labels=["evento", "concerto", "spettacolo", "tour"], priority=90),
            SchemaField("artist", "Artista", "person",
                        ["artista", "gruppo", "band", "performer"], priority=85),
            SchemaField("event_date", "Data evento", "date",
                        ["data evento", "data concerto", "data spettacolo",
                         "data manifestazione", "evento del", "in data"],
                        context_labels=["evento", "concerto", "spettacolo", "tour", "inizio"],
                        priority=80),
            SchemaField("event_time", "Ora evento", "time",
                        ["ora evento", "ora inizio", "inizio concerto",
                         "inizio spettacolo", "orario inizio", "show starts", "ora concerto"],
                        context_labels=["evento", "inizio", "concerto", "spettacolo"],
                        priority=78),
            SchemaField("doors_open", "Apertura porte", "time",
                        ["apertura porte", "porte", "gate", "gates open",
                         "doors open", "apertura ingresso"],
                        context_labels=["apertura", "porte", "gate"], priority=75),
            SchemaField("venue", "Luogo", "place",
                        ["luogo", "venue", "sede", "location", "presso"],
                        priority=72),
            SchemaField("city", "Città", "place", ["città", "city"], priority=70),
            SchemaField("seat", "Posto", "text",
                        ["posto", "settore", "fila", "gradinata", "tribuna", "platea"],
                        priority=65),
            SchemaField("holder", "Intestatario", "person",
                        ["intestatario", "titolare", "beneficiario"], priority=60),
            SchemaField("order_number", "Numero ordine", "number",
                        ["numero ordine", "ordine", "n. ordine", "order id",
                         "order number", "codice ordine"],
                        context_labels=["ordine", "order"], priority=55),
            SchemaField("ticket_number", "Numero biglietto", "number",
                        ["numero biglietto", "biglietto n", "ticket number",
                         "n. biglietto", "codice biglietto"],
                        context_labels=["biglietto", "ticket"], priority=50),
            SchemaField("price", "Prezzo", "amount",
                        ["prezzo", "importo", "totale"], priority=45),
        ],
        info_order=["event_title", "artist", "event_date", "event_time",
                    "doors_open", "venue", "city", "seat", "holder",
                    "price", "order_number", "ticket_number"],
        classifier_keywords={
            "biglietto": 3.0, "concerto": 2.5, "evento": 1.4, "spettacolo": 2.0,
            "apertura porte": 3.5, "porte": 0.6, "gate": 0.7, "posto": 1.2,
            "settore": 1.3, "fila": 1.0, "tribuna": 1.6, "platea": 1.6,
            "parterre": 1.6, "volo": 1.8, "boarding": 1.5,
            "carta d'imbarco": 2.5, "treno": 1.4, "italo": 1.5,
            "trenitalia": 1.8, "flight": 1.5, "ticket": 1.5,
        },
        coherence_required=[],
    ))

    # ---- FATTURA -------------------------------------------------------
    register_document_type(DocumentSchema(
        type_key="invoice",
        type_label="Fattura",
        fields=[
            SchemaField("issuer", "Emittente", "text",
                        ["emittente", "fornitore", "cedente prestatore", "cedente"],
                        priority=90),
            SchemaField("client", "Cliente", "text",
                        ["cliente", "committente", "destinatario",
                         "cessionario committente", "cessionario"],
                        priority=85),
            SchemaField("invoice_number", "Numero fattura", "number",
                        ["numero fattura", "fattura n", "n. fattura",
                         "invoice number", "fattura numero", "numero documento"],
                        context_labels=["fattura", "invoice"], priority=80),
            SchemaField("issue_date", "Data emissione", "date",
                        ["data emissione", "data fattura", "emessa il", "emissione",
                         "data documento"],
                        context_labels=["emissione", "fattura", "emessa"], priority=75),
            SchemaField("due_date", "Data scadenza", "date",
                        ["data scadenza", "scadenza", "termine pagamento",
                         "entro il", "pagabile entro"],
                        context_labels=["scadenza", "pagamento"], priority=70),
            SchemaField("subtotal", "Imponibile", "amount",
                        ["imponibile", "totale imponibile"],
                        context_labels=["imponibile"], priority=65),
            SchemaField("vat", "IVA", "amount",
                        ["iva", "vat", "imposta"],
                        context_labels=["iva", "imposta"], priority=60),
            SchemaField("total", "Totale", "amount",
                        ["totale", "totale fattura", "totale documento",
                         "importo dovuto", "totale a pagare", "da pagare"],
                        context_labels=["totale", "dovuto", "pagare"], priority=55),
            SchemaField("iban", "IBAN", "iban", ["iban"], priority=50),
            SchemaField("tax_id", "P.IVA / CF", "tax_id",
                        ["p.iva", "partita iva", "codice fiscale", "cf"], priority=45),
        ],
        info_order=["issuer", "client", "invoice_number", "issue_date",
                    "due_date", "subtotal", "vat", "total", "iban", "tax_id"],
        classifier_keywords={
            "fattura": 4.0, "invoice": 3.0, "totale imponibile": 3.0, "iva": 1.5,
            "p.iva": 2.5, "partita iva": 3.0, "imponibile": 2.5, "iban": 1.2,
            "codice destinatario": 2.5, "cedente": 2.0, "cessionario": 2.0,
            "fattura elettronica": 3.5, "committente": 1.8,
        },
        coherence_required=["total"],
    ))

    # ---- RICEVUTA / SCONTRINO ------------------------------------------
    register_document_type(DocumentSchema(
        type_key="receipt",
        type_label="Ricevuta",
        fields=[
            SchemaField("issuer", "Esercente", "text",
                        ["esercente", "negozio", "punto vendita", "emittente"], priority=85),
            SchemaField("receipt_number", "Numero ricevuta", "number",
                        ["numero ricevuta", "n. scontrino", "scontrino n",
                         "ricevuta n", "documento n"],
                        context_labels=["scontrino", "ricevuta"], priority=75),
            SchemaField("issue_date", "Data", "date",
                        ["data", "data emissione", "data ricevuta"], priority=70),
            SchemaField("total", "Totale", "amount",
                        ["totale", "totale complessivo", "importo", "totale euro"],
                        context_labels=["totale"], priority=65),
        ],
        info_order=["issuer", "issue_date", "total", "receipt_number"],
        classifier_keywords={
            "scontrino": 4.0, "ricevuta fiscale": 3.5, "ricevuta": 2.0,
            "totale complessivo": 3.0, "esercente": 2.0, "pos": 0.8,
            "documento commerciale": 3.0,
        },
        coherence_required=["total"],
    ))

    # ---- CONTRATTO -----------------------------------------------------
    register_document_type(DocumentSchema(
        type_key="contract",
        type_label="Contratto",
        fields=[
            SchemaField("party_a", "Contraente A", "person",
                        ["contraente", "parte", "sottoscrittore",
                         "il presente contratto viene stipulato tra"],
                        priority=90),
            SchemaField("party_b", "Contraente B", "person",
                        ["seconda parte", "controparte", "altra parte", "e"],
                        priority=85),
            SchemaField("subject", "Oggetto", "text",
                        ["oggetto", "prestazione", "servizio",
                         "oggetto del contratto"],
                        priority=80),
            SchemaField("effective_date", "Decorrenza", "date",
                        ["decorrenza", "data inizio", "efficace dal",
                         "con decorrenza dal", "a decorrere dal"],
                        context_labels=["decorrenza", "inizio"], priority=75),
            SchemaField("expiry_date", "Scadenza", "date",
                        ["scadenza", "termine", "fino al", "termine del contratto"],
                        context_labels=["scadenza", "termine"], priority=70),
            SchemaField("signature_date", "Data firma", "date",
                        ["data firma", "firmato il", "sottoscritto il"],
                        context_labels=["firma", "sottoscritto"], priority=65),
        ],
        info_order=["party_a", "party_b", "subject",
                    "effective_date", "expiry_date", "signature_date"],
        classifier_keywords={
            "contratto": 4.0, "agreement": 3.0, "sottoscritto": 2.0, "clausola": 2.5,
            "articolo 1": 2.5, "articolo 2": 1.0, "contraente": 2.5,
            "risoluzione": 1.5, "recesso": 1.8, "premesso che": 2.5,
        },
        coherence_required=[],
    ))

    # ---- BOLLETTA ------------------------------------------------------
    register_document_type(DocumentSchema(
        type_key="bill",
        type_label="Bolletta",
        fields=[
            SchemaField("supplier", "Fornitore", "text",
                        ["fornitore", "distributore", "gestore"], priority=85),
            SchemaField("client", "Cliente", "text",
                        ["cliente", "intestatario"], priority=80),
            SchemaField("pod", "POD/PDR", "text",
                        ["pod", "pdr", "matricola"], priority=75),
            SchemaField("period", "Periodo", "text",
                        ["periodo di riferimento", "periodo fatturato", "periodo"],
                        priority=70),
            SchemaField("consumption", "Consumo", "text",
                        ["consumo", "kwh", "smc"], priority=65),
            SchemaField("total", "Importo", "amount",
                        ["totale", "importo da pagare", "totale bolletta",
                         "totale a pagare"], priority=60),
            SchemaField("due_date", "Scadenza", "date",
                        ["scadenza", "termine pagamento", "entro il",
                         "scadenza pagamento"],
                        context_labels=["scadenza", "pagamento"], priority=55),
        ],
        info_order=["supplier", "client", "period", "consumption",
                    "total", "due_date", "pod"],
        classifier_keywords={
            "bolletta": 4.0, "utenza": 2.5, "consumo": 2.0, "kwh": 2.5,
            "importo da pagare": 3.0, "scadenza pagamento": 2.5,
            "pod": 2.0, "pdr": 2.0, "smc": 2.0, "gas naturale": 2.5,
            "energia elettrica": 2.5, "fornitura": 2.0,
        },
        coherence_required=["total"],
    ))

    # ---- REFERTO MEDICO -----------------------------------------------
    register_document_type(DocumentSchema(
        type_key="medical",
        type_label="Referto medico",
        fields=[
            SchemaField("patient", "Paziente", "person",
                        ["paziente", "assistito", "nome paziente", "cognome e nome"],
                        priority=90),
            SchemaField("issue_date", "Data referto", "date",
                        ["data referto", "data esame", "eseguito il", "data prelievo"],
                        context_labels=["referto", "esame", "prelievo"], priority=80),
            SchemaField("doctor", "Medico", "person",
                        ["medico", "dott", "dr.", "specialista", "refertante"],
                        priority=75),
            SchemaField("exam", "Esame", "text",
                        ["esame", "prestazione", "tipo esame", "indagine"],
                        priority=70),
        ],
        info_order=["patient", "issue_date", "doctor", "exam"],
        classifier_keywords={
            "referto": 4.0, "analisi cliniche": 3.0, "diagnosi": 2.5,
            "prestazione sanitaria": 2.5, "paziente": 1.0, "esame": 0.8,
            "radiologia": 2.5, "ecografia": 2.5, "ematocrito": 2.5,
            "risonanza magnetica": 3.0, "tac": 2.5, "azienda ospedaliera": 2.5,
        },
        coherence_required=[],
    ))

    # ---- CERTIFICATO --------------------------------------------------
    register_document_type(DocumentSchema(
        type_key="certificate",
        type_label="Certificato",
        fields=[
            SchemaField("holder", "Intestatario", "person",
                        ["intestatario", "titolare", "beneficiario"], priority=85),
            SchemaField("issue_date", "Data emissione", "date",
                        ["data emissione", "rilasciato il", "data rilascio"],
                        priority=75),
            SchemaField("subject", "Oggetto", "text",
                        ["oggetto", "certifica che", "attesta che"], priority=70),
            SchemaField("issuer", "Ente emittente", "text",
                        ["ente", "emittente", "rilasciato da"], priority=65),
        ],
        info_order=["subject", "holder", "issuer", "issue_date"],
        classifier_keywords={
            "certificato": 4.0, "attestato": 3.5, "certifica che": 3.5,
            "attesta che": 3.0, "rilasciato": 1.5, "diploma": 2.5,
        },
        coherence_required=[],
    ))

    # ---- CARTA IDENTITÀ ----------------------------------------------
    register_document_type(DocumentSchema(
        type_key="id_card",
        type_label="Carta d'identità",
        fields=[
            SchemaField("surname", "Cognome", "person",
                        ["cognome", "surname"], priority=95),
            SchemaField("name", "Nome", "person",
                        ["nome", "given name"], priority=94),
            SchemaField("birth_date", "Data nascita", "date",
                        ["data di nascita", "nato il", "date of birth"], priority=80),
            SchemaField("birth_place", "Luogo nascita", "place",
                        ["luogo di nascita", "nato a", "place of birth"], priority=75),
            SchemaField("document_number", "Numero documento", "number",
                        ["numero documento", "n° carta", "document no", "nr carta",
                         "numero carta"], priority=70),
            SchemaField("issue_date", "Rilascio", "date",
                        ["data rilascio", "rilasciata il", "date of issue"], priority=65),
            SchemaField("expiry_date", "Scadenza", "date",
                        ["data scadenza", "scade il", "date of expiry"], priority=60),
        ],
        info_order=["name", "surname", "birth_date", "birth_place",
                    "document_number", "issue_date", "expiry_date"],
        classifier_keywords={
            "carta d'identità": 4.5, "carta di identita": 4.5,
            "identity card": 3.5, "repubblica italiana": 2.5,
            "ministero dell'interno": 3.0, "comune di": 1.2,
            "cittadinanza": 1.5, "statura": 2.5, "sesso": 1.0,
        },
        coherence_required=[],
    ))

    # ---- PASSAPORTO ---------------------------------------------------
    register_document_type(DocumentSchema(
        type_key="passport",
        type_label="Passaporto",
        fields=[
            SchemaField("surname", "Cognome", "person",
                        ["surname", "cognome"], priority=95),
            SchemaField("name", "Nome", "person",
                        ["given names", "nome"], priority=94),
            SchemaField("birth_date", "Data nascita", "date",
                        ["date of birth", "data di nascita"], priority=80),
            SchemaField("nationality", "Nazionalità", "text",
                        ["nationality", "nazionalità", "cittadinanza"], priority=75),
            SchemaField("document_number", "Numero passaporto", "number",
                        ["passport no", "n° passaporto", "numero passaporto"], priority=70),
            SchemaField("issue_date", "Data rilascio", "date",
                        ["date of issue", "data rilascio"], priority=65),
            SchemaField("expiry_date", "Scadenza", "date",
                        ["date of expiry", "data scadenza"], priority=60),
        ],
        info_order=["name", "surname", "nationality", "birth_date",
                    "document_number", "issue_date", "expiry_date"],
        classifier_keywords={
            "passaporto": 4.5, "passport": 4.5, "type/tipo": 1.5,
            "code/codice": 1.0, "nationality": 2.5, "biometric": 2.0,
        },
        coherence_required=[],
    ))

    # ---- CURRICULUM ---------------------------------------------------
    register_document_type(DocumentSchema(
        type_key="cv",
        type_label="Curriculum",
        fields=[
            SchemaField("name", "Nome e cognome", "person",
                        ["nome", "candidato"], priority=90),
            SchemaField("email", "Email", "email",
                        ["email", "e-mail"], priority=80),
            SchemaField("phone", "Telefono", "phone",
                        ["tel", "telefono", "cellulare", "mobile"], priority=75),
            SchemaField("birth_date", "Data nascita", "date",
                        ["data di nascita", "nato il"], priority=70),
            SchemaField("city", "Città", "place",
                        ["città", "residenza", "domicilio"], priority=65),
        ],
        info_order=["name", "email", "phone", "birth_date", "city"],
        classifier_keywords={
            "curriculum": 4.0, "curriculum vitae": 4.5, "cv": 1.5,
            "esperienza lavorativa": 3.0, "esperienze professionali": 3.0,
            "istruzione": 1.8, "istruzione e formazione": 2.5,
            "competenze": 1.5, "resume": 3.0,
            "profilo professionale": 2.5, "obiettivi": 1.0,
        },
        coherence_required=[],
    ))

    # ---- ESTRATTO CONTO -----------------------------------------------
    register_document_type(DocumentSchema(
        type_key="bank_statement",
        type_label="Estratto conto",
        fields=[
            SchemaField("bank", "Banca", "text",
                        ["banca", "istituto"], priority=85),
            SchemaField("holder", "Intestatario", "person",
                        ["intestatario", "titolare", "cliente"], priority=80),
            SchemaField("iban", "IBAN", "iban", ["iban"], priority=75),
            SchemaField("period", "Periodo", "text",
                        ["periodo", "estratto al", "movimenti dal"], priority=70),
            SchemaField("balance", "Saldo", "amount",
                        ["saldo", "saldo contabile", "saldo disponibile", "saldo finale"],
                        priority=65),
        ],
        info_order=["bank", "holder", "iban", "period", "balance"],
        classifier_keywords={
            "estratto conto": 4.5, "saldo contabile": 3.5,
            "saldo disponibile": 3.5, "movimenti": 2.0, "operazioni": 1.0,
            "coordinate bancarie": 2.5, "codice abi": 2.5, "abi": 1.5,
            "cab": 1.5, "bancomat": 1.2,
        },
        coherence_required=[],
    ))

    # ---- DOCUMENTO FISCALE (730, dichiarazione, CU…) -------------------
    register_document_type(DocumentSchema(
        type_key="tax_doc",
        type_label="Documento fiscale",
        fields=[
            SchemaField("taxpayer", "Contribuente", "person",
                        ["contribuente", "dichiarante"], priority=85),
            SchemaField("year", "Anno", "text",
                        ["anno d'imposta", "anno di riferimento",
                         "periodo d'imposta"], priority=80),
            SchemaField("tax_id", "Codice fiscale", "tax_id",
                        ["codice fiscale", "cf"], priority=75),
        ],
        info_order=["taxpayer", "year", "tax_id"],
        classifier_keywords={
            "dichiarazione dei redditi": 4.0, "730": 2.5, "modello unico": 3.5,
            "cud": 3.0, "certificazione unica": 3.5,
            "agenzia delle entrate": 3.0, "anno d'imposta": 3.0,
        },
        coherence_required=[],
    ))

    # ---- GENERIC -------------------------------------------------------
    register_document_type(DocumentSchema(
        type_key="generic",
        type_label="Documento generico",
        fields=[],
        info_order=[],
        classifier_keywords={},
        coherence_required=[],
    ))


_init_default_schemas()
