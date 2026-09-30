from decimal import Decimal

from app import calcoli as _calcoli
from app.models import Pratica
from tests.conftest import piva_fittizia
from tests.test_app import _chat_ai, _invia, csrf, ctx, ctx_dati, entra, nuova_pratica  # noqa: F401  (ctx e' una fixture)


def _xml_fattura(numero, data, imponibile, piva_ced, cf_com="RSSMRA80A01H501U"):
    iva = round(imponibile * 0.22, 2)
    return (f'<?xml version="1.0"?><p:FatturaElettronica xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2">'
            f'<FatturaElettronicaHeader><CedentePrestatore><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>{piva_ced}</IdCodice></IdFiscaleIVA>'
            '<Anagrafica><Denominazione>Alfa Costruzioni S.r.l.</Denominazione></Anagrafica></DatiAnagrafici></CedentePrestatore>'
            f'<CessionarioCommittente><DatiAnagrafici><CodiceFiscale>{cf_com}</CodiceFiscale><Anagrafica><Denominazione>Cliente Beta S.r.l.</Denominazione></Anagrafica></DatiAnagrafici></CessionarioCommittente></FatturaElettronicaHeader>'
            f'<FatturaElettronicaBody><DatiGenerali><DatiGeneraliDocumento><TipoDocumento>TD01</TipoDocumento><Data>{data}</Data><Numero>{numero}</Numero>'
            f'<ImportoTotaleDocumento>{imponibile + iva:.2f}</ImportoTotaleDocumento></DatiGeneraliDocumento></DatiGenerali><DatiBeniServizi><DatiRiepilogo><AliquotaIVA>22.00</AliquotaIVA>'
            f'<ImponibileImporto>{imponibile:.2f}</ImponibileImporto><Imposta>{iva:.2f}</Imposta></DatiRiepilogo></DatiBeniServizi></FatturaElettronicaBody></p:FatturaElettronica>').encode()


def _carica_due_fatture(c, pid, piva):
    tok = csrf(c, f"/pratiche/{pid}/chat")
    r = None
    for n in ("1", "3"):
        r = c.post(f"/pratiche/{pid}/chat/documento", data={"csrf": tok},
                   files={"file": (f"f{n}.xml", _xml_fattura(n, "2023-03-0" + n, 1000.0, piva), "text/xml")})
        assert r.status_code == 200
    return tok, r


def _avanza(c, pid, tok):
    for f in ("prep_autorizzazione", "foglio_servizio", "invito", "avvio"):
        c.post(f"/pratiche/{pid}/fase/{f}", data={"azione": "completa", "csrf": tok})


def test_riscontri_da_fatture_conferma_e_constatazione_nel_pvoc(ctx):
    c = entra(ctx)
    piva = piva_fittizia()
    pid = nuova_pratica(c, partite_iva=piva)
    visti = _chat_ai(ctx, ["Ho letto le fatture. Il numero 2 manca."])
    tok, r = _carica_due_fatture(c, pid, piva)
    assert "numeri mancanti: 2" in r.text and "Riscontri e violazioni" in r.text
    ultimo = str(visti[-1]["system"])
    assert "F_V2023_IMP" in ultimo and "PROSPETTO DELLE FATTURE" in ultimo and "Alfa Costruzioni" not in ultimo
    with ctx.SM() as s:
        d = ctx_dati(ctx, s.get(Pratica, pid))
    rid = next(x["id"] for x in d["riscontri"] if x["chiave"].startswith("num:"))
    r = c.post(f"/pratiche/{pid}/chat/riscontro", data={"csrf": tok, "rid": rid, "azione": "conferma"})
    assert "confermato" in r.text
    _avanza(c, pid, tok)
    visti = _chat_ai(ctx, ["Constatata la violazione. {{SPIEGA: x}}"])
    r = c.post(f"/pratiche/{pid}/chat/genera", data={"csrf": tok, "fase": "controllo_contabile", "giornata": "12/10/2023"})
    assert r.status_code == 303
    prompt = str(visti[0]["messages"])
    assert "RISCONTRI CONFERMATI DA CONSTATARE" in prompt and "numeri mancanti: 2" in prompt and "art. 21" in prompt
    assert "Alfa Costruzioni" not in prompt and "CONSTATA, una per una" in prompt


def test_riscontri_non_confermati_non_vanno_nell_atto(ctx):
    c = entra(ctx)
    piva = piva_fittizia()
    pid = nuova_pratica(c, partite_iva=piva)
    _chat_ai(ctx, ["ok"])
    tok, _ = _carica_due_fatture(c, pid, piva)
    _avanza(c, pid, tok)
    visti = _chat_ai(ctx, ["Testo dell'atto."])
    c.post(f"/pratiche/{pid}/chat/genera", data={"csrf": tok, "fase": "controllo_contabile", "giornata": "12/10/2023"})
    assert visti and "RISCONTRI CONFERMATI" not in str(visti[0]["messages"])


def test_chat_ai_propone_riscontri_e_calcoli_validati(ctx):
    c = entra(ctx)
    piva = piva_fittizia()
    pid = nuova_pratica(c, partite_iva=piva)
    _chat_ai(ctx, ["ok"])
    tok = csrf(c, f"/pratiche/{pid}/chat")
    c.post(f"/pratiche/{pid}/chat/documento", data={"csrf": tok},
           files={"file": ("f1.xml", _xml_fattura("1", "2023-03-01", 1000.0, piva), "text/xml")})
    az = ('Analisi fatta.\n<<AZIONI>>\n{"riscontri": [{"fase": "coerenza_interna", "periodo": "2023", "tipo": "sostanziale", '
          '"descrizione": "Acquisti in reverse charge non integrati", "norma": "art. 17 DPR 633/72", "importi": ["F_V2023_IMP", "NONESISTE"]}, '
          '{"fase": "fase_falsa", "descrizione": "x"}], "calcoli": [{"tipo": "percentuale", "etichetta": "IVA dovuta 22%", '
          '"operandi": ["F_V2023_IMP"], "param": "22"}, {"tipo": "somma", "etichetta": "rotto", "operandi": ["NONESISTE"]}]}\n<<FINE>>')
    _chat_ai(ctx, [az])
    r = _invia(c, pid, "Analizza.")
    assert "Acquisti in reverse charge non integrati" in r.text and "fase_falsa" not in r.text
    with ctx.SM() as s:
        d = ctx_dati(ctx, s.get(Pratica, pid))
    ai = [x for x in d["riscontri"] if x["origine"] == "ai"]
    assert len(ai) == 1 and ai[0]["importi"] == ["F_V2023_IMP"] and ai[0]["stato"] == "proposto"
    assert len(d["calcoli"]["calcoli"]) == 1 and d["calcoli"]["calcoli"][0]["tipo"] == "percentuale"
    assert _calcoli.registro_da_dati(d["calcoli"]).voci["C1"].valore == Decimal("220.00")
