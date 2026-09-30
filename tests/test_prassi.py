import httpx
import pytest
from sqlalchemy import select

from app import chat, prassi
from app.db import crea_engine, crea_sessionmaker
from app.models import PrassiDocumento
from tests.test_app import csrf, ctx, entra  # noqa: F401  (fixture ctx)

TESTO = ("CIRCOLARE N. 99/E\n\n3. SCONTO IN FATTURA\n\n3.1 Credito spettante al fornitore\n\n"
         "Il fornitore che applica lo sconto in fattura acquisisce un credito d'imposta pari al 110 per cento dello sconto praticato; "
         "la differenza tra il credito e il corrispettivo incassato costituisce per il fornitore un componente positivo di reddito secondo le regole ordinarie.\n\n"
         "4. ALTRI CHIARIMENTI\n\nLe spese sostenute dal contribuente per gli interventi sulle parti comuni dell'edificio condominiale sono ripartite tra i condomini "
         "in base ai millesimi di proprieta' e ciascun condomino esercita l'opzione per la propria quota di spesa.\n" + "Testo di riempimento normativo. " * 40)


@pytest.fixture()
def sess(tmp_path):
    SM = crea_sessionmaker(crea_engine(f"sqlite:///{tmp_path}/p.db"))
    with SM() as s:
        yield s


def test_temi_del_caso():
    assert "superbonus" in prassi.temi_del_caso("sconto in fattura superbonus 110% credito cessione")
    assert prassi.temi_del_caso("controllo su una ditta di pulizie") == []


def test_indice_ha_documenti_ufficiali():
    docs = prassi.indice()["documenti"]
    assert any(d["codice"] == "CIRC-23E-2022" for d in docs)
    assert all(prassi.host_ammesso(d["url"]) for d in docs)
    assert not prassi.host_ammesso("https://evil.example.com/a.pdf") and not prassi.host_ammesso("file:///etc/passwd")


def test_sincronizza_cerca_e_citazione(sess):
    chiamate = []

    def finto(url):
        chiamate.append(url)
        if "Circolare+n.+24" in url:
            raise ValueError("Sito non raggiungibile")
        return TESTO
    e = prassi.sincronizza(sess, ["superbonus"], finto)
    assert e["scaricati"] >= 5 and e["errori"] == 1
    bad = sess.scalar(select(PrassiDocumento).where(PrassiDocumento.codice == "CIRC-24E-2020"))
    assert bad.stato == "errore" and "raggiungibile" in bad.errore
    n = len(chiamate)
    prassi.sincronizza(sess, ["superbonus"], finto)
    assert len(chiamate) == n                                   # gli errori recenti non si ritentano subito, i pronti non si riscaricano
    r = prassi.cerca(sess, "fornitore sconto in fattura credito 110 per cento differenza corrispettivo componente positivo di reddito", ["superbonus"])
    assert r and "componente positivo di reddito" in r[0]["testo"] and r[0]["sezione"].startswith("3.1")
    t = prassi.passaggi_testo(r, "BIBLIOTECA: prova")
    assert "CIRC-" in t and "sez. 3.1" in t
    ctx_txt = chat.contesto("controllo", "x", [], {}, [], [], {}, prassi=t)
    assert "PRASSI DELL'AGENZIA DELLE ENTRATE" in ctx_txt and "sez. 3.1" in ctx_txt
    assert "PRASSI." in chat.system() and "cita" in chat.system()


def test_scarica_solo_host_ufficiali_e_reindirizzamenti():
    def h(request):
        if request.url.host == "www.agenziaentrate.gov.it" and request.url.path.endswith("ok.pdf/"):
            return httpx.Response(200, content=("<html><body><p>" + "testo ufficiale esteso " * 60 + "</p></body></html>").encode(), headers={"content-type": "text/html"})
        if request.url.path.endswith("redir/"):
            return httpx.Response(302, headers={"location": "https://evil.example.com/x"})
        return httpx.Response(404)
    cl = httpx.Client(transport=httpx.MockTransport(h), follow_redirects=False)
    assert "testo ufficiale" in prassi.scarica("https://www.agenziaentrate.gov.it/portale/documents/ok.pdf/", cl)
    with pytest.raises(ValueError, match="non ufficiale"):
        prassi.scarica("https://evil.example.com/a.pdf", cl)
    with pytest.raises(ValueError, match="non ufficiale"):
        prassi.scarica("https://www.agenziaentrate.gov.it/portale/documents/redir/", cl)
    with pytest.raises(ValueError, match="404"):
        prassi.scarica("https://www.agenziaentrate.gov.it/portale/documents/manca/", cl)


def test_scopri_da_fonti_ricerche(sess):
    base = [{"id": "Q1", "quesito": "maggior credito 10% fornitore sconto in fattura superbonus", "fonti": [
        {"titolo": "CIRCOLARE N. 23/E Roma, 23 giugno 2022", "url": "https://www.agenziaentrate.gov.it/portale/documents/20143/1/altra.pdf/", "ufficiale": True},
        {"titolo": "Blog", "url": "https://blog.example.com/x", "ufficiale": False}]}]
    assert prassi.scopri_da_fonti(sess, base) == 1
    assert prassi.scopri_da_fonti(sess, base) == 0
    d = sess.scalar(select(PrassiDocumento).where(PrassiDocumento.origine == "scoperto"))
    assert d.numero.startswith("23") and "superbonus" in d.temi


def test_pagina_prassi_e_aggiunta(ctx):          # noqa: F811
    c = entra(ctx)
    r = c.get("/prassi")
    assert r.status_code == 200 and "Biblioteca della prassi" in r.text and "CIRC-23E-2022" not in r.text.replace("23/E", "") or "23/E" in r.text
    tok = csrf(c, "/prassi")
    r = c.post("/prassi/aggiungi", data={"csrf": tok, "url": "https://evil.example.com/a.pdf"})
    assert r.status_code == 303 and "non+ufficiale" in r.headers["location"]


def test_carica_pdf_a_mano_entra_in_biblioteca(ctx, sess):          # noqa: F811
    c = entra(ctx)
    tok = csrf(c, "/prassi")
    r = c.post("/prassi/carica", data={"csrf": tok, "codice": "CIRC-23E-2022", "temi": "superbonus"},
               files={"file": ("c23.txt", TESTO.encode(), "text/plain")})
    assert r.status_code == 303 and "caricato" in r.headers["location"]
    with ctx.SM() as s:
        d = s.scalar(select(PrassiDocumento).where(PrassiDocumento.codice == "CIRC-23E-2022"))
        assert d.stato == "pronto" and "componente positivo di reddito" in d.testo
        r2 = prassi.cerca(s, "fornitore sconto in fattura credito 110 per cento componente positivo di reddito corrispettivo incassato", ["superbonus"])
        assert r2 and r2[0]["codice"] == "CIRC-23E-2022"
