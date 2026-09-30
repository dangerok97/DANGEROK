import io
from types import SimpleNamespace

import docx
from sqlalchemy import text

from app import metodo
from app.models import Pratica
from tests.conftest import cf_fittizio
from tests.test_app import csrf, ctx, ctx_dati, entra, nuova_pratica  # noqa: F401


def _voce(tipo="precedente", atto="PVOC", titolo="Forfettario reverse charge", tag="regime forfettario reverse charge",
          testo="Il giorno X in Tarquinia. La parte esibiva le fatture. Constatato il superamento della soglia.", scheda="RAGIONAMENTO: prima le fatture"):
    return {"id": 1, "tipo": tipo, "atto": atto, "stato": "pronto", "titolo": titolo, "tag": tag, "testo": testo, "scheda": scheda, "sospetti": []}


def test_ripulisci_sostituisce_dati_con_segnaposto_generici():
    t, sosp = metodo.ripulisci(f"Il Sig. Mario Rossi, C.F. {cf_fittizio()}, residente in via dei Test n. 27, mail m.rossi@esempio.it. "
                               "Ditta Gamma Edilizia Srl ha esibito.")
    assert "Rossi" not in t and cf_fittizio() not in t and "m.rossi" not in t and "via dei Test" not in t
    assert "«persona»" in t and "«codice fiscale»" in t and "«indirizzo»" in t and "[PERSONA" not in t      # niente numeri: non si confondono
    assert any("Gamma Edilizia" in s for s in sosp)


def test_applica_nomi():
    t = metodo.applica_nomi("La Gamma Edilizia ha emesso; parla Luca Verdi.", {"Gamma Edilizia": "ente", "Luca Verdi": "persona", "Altro Nome": "ignora"})
    assert t == "La «ente» ha emesso; parla «persona»."


def test_selezione_per_pertinenza_e_bonus_atto():
    voci = [_voce(), {**_voce(titolo="Bonus edilizi", tag="superbonus cessione credito", atto="PVV"), "id": 2},
            {**_voce(tipo="spunto", atto="", titolo="Forfettari: prime verifiche", tag="forfettario cause di esclusione", testo="Controlla le cause di esclusione"), "id": 3}]
    sel = metodo.seleziona(voci, "Controllo su regime forfettario con acquisti in reverse charge", "PVOC")
    assert [v["id"] for v in sel] == [3, 1]                               # prima gli spunti, poi i precedenti; il bonus non c'entra
    assert metodo.seleziona(voci, "argomento del tutto diverso xyzzy", "PVOC") == []


def test_metodo_testo_e_esempi_di_stile():
    v = _voce()
    assert "PRECEDENTE PVOC: Forfettario reverse charge" in metodo.metodo_testo([v]) and "RAGIONAMENTO: prima le fatture" in metodo.metodo_testo([v])
    ex = metodo.esempi_di_stile([v], "forfettario soglia", "PVOC")
    assert len(ex) == 1 and "Constatato il superamento della soglia" in ex[0]
    assert metodo.esempi_di_stile([v], "forfettario", "PVC") == []


def _docx(paragrafi):
    d = docx.Document()
    for p in paragrafi:
        d.add_paragraph(p)
    b = io.BytesIO()
    d.save(b)
    return b.getvalue()


def _fake(ctx, scheda="FATTISPECIE: forfettario\nRAGIONAMENTO OPERATIVO: si parte dalle fatture"):
    visti = []

    def crea(**kw):
        visti.append(kw)
        t = scheda if "METODO" in str(kw.get("system", "")) and "FATTISPECIE" in str(kw.get("system", "")) else "Testo dell'atto. {{SPIEGA: x}}"
        return SimpleNamespace(stop_reason="end_turn", model="finto", content=[SimpleNamespace(type="text", text=t)])
    ctx.fake.beta.messages.create = crea
    return visti


def test_libreria_precedente_ripulito_distillato_e_riusato_nella_generazione(ctx):
    c = entra(ctx)
    visti = _fake(ctx)
    tok = csrf(c, "/libreria")
    cf = cf_fittizio()
    f = _docx([f"Il giorno 06/03/2026 il Sig. Mario Rossi, C.F. {cf}, si presentava presso il Reparto.",
               "Constatato il superamento della soglia di ricavi per il regime forfettario nel periodo d'imposta 2023."])
    r = c.post("/libreria/precedente", data={"csrf": tok, "atto": "PVOC", "titolo": "Forfettario soglia", "tag": "regime forfettario soglia ricavi"},
               files={"file": ("atto.docx", f, "application/octet-stream")})
    assert r.status_code == 200 and "Atto caricato e ripulito" in r.text and "Ragionamento estratto" in r.text
    inviato = str(visti[0]["messages"])
    assert "Rossi" not in inviato and cf not in inviato and "«persona»" in inviato          # all'AI esce solo il testo ripulito
    with ctx.SM() as s:
        raw = s.execute(text("select dati_cifrati from conoscenza_reparto")).scalar()
    assert "soglia" not in raw and "Rossi" not in raw                                        # cifrato a riposo

    # spunto operativo
    tok = csrf(c, "/libreria")
    r = c.post("/libreria/spunto", data={"csrf": tok, "titolo": "Forfettari", "tag": "regime forfettario", "atto": "", "testo": "Sui forfettari si controlla prima la soglia di ricavi."})
    assert "Spunto salvato" in r.text

    # generazione di una giornata: metodo + stile + regola di conciliazione
    pid = nuova_pratica(c, tipologia="regime_forfettario")
    tk = csrf(c, f"/pratiche/{pid}/chat")
    for fase in ("prep_autorizzazione", "foglio_servizio", "invito", "avvio"):
        c.post(f"/pratiche/{pid}/fase/{fase}", data={"azione": "completa", "csrf": tk})
    n = len(visti)
    resp = c.post(f"/pratiche/{pid}/chat/genera", data={"csrf": tk, "fase": "controllo_contabile", "giornata": "12/03/2026"})
    assert resp.status_code == 303
    user = str(visti[n]["messages"])
    sistema = str(visti[n]["system"])
    assert "METODO DEL REPARTO PERTINENTE" in user and "SINTESI DELLE DUE FONTI" in user
    assert "si parte dalle fatture" in user and "Sui forfettari si controlla prima la soglia" in user      # scheda del precedente + spunto
    assert "Constatato il superamento della soglia di ricavi" in user                                        # brano di stile
    assert "Rossi" not in user and "«persona»" in user


def test_libreria_nomi_dubbi_richiedono_conferma(ctx):
    c = entra(ctx)
    visti = _fake(ctx)
    tok = csrf(c, "/libreria")
    f = _docx(["La societa' Gamma Edilizia Srl ha emesso le fatture al contribuente. Constatata la violazione dell'obbligo di registrazione."])
    r = c.post("/libreria/precedente", data={"csrf": tok, "atto": "PVC", "titolo": "Reg", "tag": "registrazione"},
               files={"file": ("a.docx", f, "application/octet-stream")})
    assert "Da controllare prima dell'uso" in r.text and "Gamma Edilizia" in r.text and not visti        # nulla parte verso l'AI
    with ctx.SM() as s:
        vid = s.execute(text("select id from conoscenza_reparto")).scalar()
    r = c.post(f"/libreria/{vid}/revisione", data={"csrf": tok, "nome": "Gamma Edilizia", "tipo": "ente"})
    assert "Testo pronto" in r.text and visti and "Gamma" not in str(visti[0]["messages"]) and "«ente»" in str(visti[0]["messages"])


def test_chat_riceve_il_metodo_del_reparto(ctx):
    c = entra(ctx)
    tok = csrf(c, "/libreria")
    visti = _fake(ctx, scheda="ok")
    c.post("/libreria/spunto", data={"csrf": tok, "titolo": "Forfettari", "tag": "forfettario", "atto": "", "testo": "Sui forfettari si controlla prima la soglia."})
    pid = nuova_pratica(c)
    tk = csrf(c, f"/pratiche/{pid}/chat")
    c.post(f"/pratiche/{pid}/chat", data={"csrf": tk, "messaggio": "Controllo su un forfettario"})
    # la tipologia della pratica e' generica: lo spunto con atto vuoto entra comunque con il bonus generale se c'e' pertinenza
    sist = str(visti[-1]["system"])
    assert "METODO DEL REPARTO PERTINENTE" in sist and "SINTESI DELLE DUE FONTI" in sist
