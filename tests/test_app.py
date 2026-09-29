import re
from types import SimpleNamespace

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app import security
from app.config import Settings
from app.db import crea_engine, crea_sessionmaker
from app.main import create_app
from app.models import LogAI, Pratica, Utente
from tests.conftest import cf_fittizio, piva_fittizia

PW = "password-di-prova-123"


class FakeAI:
    """Finto client Anthropic: registra la richiesta e risponde riusando i segnaposto ricevuti."""
    def __init__(self):
        self.richieste = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.richieste.append(kw)
        user = kw["messages"][0]["content"]
        m = re.search(r"\[PERSONA_1\]", user)
        testo = f"Il giorno odierno {m.group(0) if m else '[DA COMPILARE: soggetto]'} ha esibito la documentazione."
        return SimpleNamespace(stop_reason="end_turn", model=kw["model"],
                               content=[SimpleNamespace(type="text", text=testo)])


@pytest.fixture()
def ctx(tmp_path):
    st = Settings(database_url=f"sqlite:///{tmp_path}/t.db", data_key=security.nuova_chiave_fernet(),
                  session_secret="x" * 40, https_only=False, anthropic_model="claude-opus-5-5")
    SM = crea_sessionmaker(crea_engine(st.database_url))
    cif = security.Cifratore(st.data_key)
    segreto = security.nuovo_segreto_totp()
    with SM() as s:
        s.add(Utente(nome="u", password_hash=security.hash_password(PW), totp_cifrato=cif.cifra_testo(segreto)))
        s.commit()
    fake = FakeAI()
    app = create_app(st, SM, ai_client=fake)
    c = TestClient(app, follow_redirects=False)
    return SimpleNamespace(c=c, SM=SM, segreto=segreto, fake=fake, st=st)


def csrf(c, path="/login"):
    return re.search(r'name="csrf" value="([^"]+)"', c.get(path).text).group(1)


def entra(x):
    tok = csrf(x.c)
    r = x.c.post("/login", data={"password": PW, "codice": pyotp.TOTP(x.segreto).now(), "csrf": tok})
    assert r.status_code == 303
    return x.c


def test_pagine_protette(ctx):
    r = ctx.c.get("/pratiche")
    assert r.status_code == 303 and r.headers["location"] == "/login"


def test_login_richiede_password_e_totp(ctx):
    tok = csrf(ctx.c)
    r = ctx.c.post("/login", data={"password": PW, "codice": "000000", "csrf": tok})
    assert r.status_code == 200 and "Credenziali non valide" in r.text
    r = ctx.c.post("/login", data={"password": "sbagliata", "codice": pyotp.TOTP(ctx.segreto).now(), "csrf": tok})
    assert "Credenziali non valide" in r.text


def test_blocco_dopo_troppi_tentativi(ctx):
    tok = csrf(ctx.c)
    for _ in range(ctx.st.max_login_failures):
        ctx.c.post("/login", data={"password": "no", "codice": "000000", "csrf": tok})
    r = ctx.c.post("/login", data={"password": PW, "codice": pyotp.TOTP(ctx.segreto).now(), "csrf": tok})
    assert r.status_code == 200 and "bloccato" in r.text


def test_csrf_obbligatorio(ctx):
    r = ctx.c.post("/login", data={"password": PW, "codice": "123456", "csrf": "finto"})
    assert r.status_code == 403


def nuova_pratica(c, **extra):
    tok = csrf(c, "/pratiche/nuova")
    data = {"tipo": "controllo", "tipologia": "generica", "persone": "Mario Rossi", "enti": "Alfa Costruzioni S.r.l.",
            "codici_fiscali": cf_fittizio(), "partite_iva": piva_fittizia(), "indirizzi": "via dei Test n. 27",
            "verbalizzanti": "Mar. Giulia Bianchi", "csrf": tok, **extra}
    r = c.post("/pratiche/nuova", data=data)
    assert r.status_code == 303
    return int(r.headers["location"].rsplit("/", 1)[1])


def test_dati_soggetto_cifrati_a_riposo(ctx):
    c = entra(ctx)
    nuova_pratica(c)
    with ctx.SM() as s:
        raw = s.execute(text("select codice, dati_cifrati from pratica")).one()
    assert raw.codice.startswith("C-") and "Rossi" not in raw.dati_cifrati and "Alfa" not in raw.dati_cifrati


def test_ordine_fasi_rispettato(ctx):
    c = entra(ctx)
    pid = nuova_pratica(c)
    tok = csrf(c, f"/pratiche/{pid}")
    r = c.post(f"/pratiche/{pid}/fase/avvio", data={"azione": "completa", "csrf": tok})
    assert r.status_code == 409 and "Prima di" in r.text
    r = c.post(f"/pratiche/{pid}/fase/prep_autorizzazione", data={"azione": "completa", "csrf": tok})
    assert r.status_code == 303


def test_fase_obbligatoria_non_puo_essere_non_applicabile(ctx):
    c = entra(ctx)
    pid = nuova_pratica(c)
    tok = csrf(c, f"/pratiche/{pid}")
    r = c.post(f"/pratiche/{pid}/fase/prep_autorizzazione",
               data={"azione": "non_applicabile", "motivo": "x", "csrf": tok})
    assert r.status_code == 400


def test_scheda_salvataggio(ctx):
    c = entra(ctx)
    pid = nuova_pratica(c)
    tok = csrf(c, f"/pratiche/{pid}/scheda")
    r = c.post(f"/pratiche/{pid}/scheda", data={"csrf": tok, "C3": "d'iniziativa", "ZZ": "ignorato"})
    assert r.status_code == 303
    assert "d&#39;iniziativa" in c.get(f"/pratiche/{pid}/scheda").text


def test_ai_invia_solo_dati_pseudonimizzati_e_ripristina(ctx):
    c = entra(ctx)
    pid = nuova_pratica(c)
    tok = csrf(c, f"/pratiche/{pid}/atto/nuovo?fase=avvio")
    base = {"fase": "avvio", "appunti": "Il Sig. Mario Rossi ha esibito le fatture. Alfa Costruzioni S.r.l. presente.",
            "giornata": "01/01/2026", "csrf": tok}
    r = c.post(f"/pratiche/{pid}/atto/nuovo", data={**base, "azione": "anteprima"})
    assert "[PERSONA_1]" in r.text and "Rossi" not in r.text.split("Testo che sara")[1]
    r = c.post(f"/pratiche/{pid}/atto/nuovo", data={**base, "azione": "genera"})
    assert "Conferma di aver controllato" in r.text and not ctx.fake.richieste
    r = c.post(f"/pratiche/{pid}/atto/nuovo", data={**base, "azione": "genera", "conferma": "1"})
    assert r.status_code == 303
    inviato = ctx.fake.richieste[0]["messages"][0]["content"] + ctx.fake.richieste[0]["system"]
    for dato in ("Rossi", "Alfa", cf_fittizio(), piva_fittizia(), "dei Test", "Bianchi"):
        assert dato not in inviato
    req = ctx.fake.richieste[0]
    assert req["model"] == "claude-opus-5-5" and req["thinking"] == {"type": "adaptive"}
    atto = c.get(r.headers["location"])
    assert "Mario Rossi ha esibito" in atto.text        # dati reali ripristinati nella bozza
    with ctx.SM() as s:
        log = s.scalars(select(LogAI)).all()
    assert log and all("Rossi" not in l.testo_inviato for l in log)


def test_email_non_in_anagrafica_viene_sostituita(ctx):
    c = entra(ctx)
    pid = nuova_pratica(c)
    tok = csrf(c, f"/pratiche/{pid}/atto/nuovo?fase=avvio")
    r = c.post(f"/pratiche/{pid}/atto/nuovo", data={
        "fase": "avvio", "azione": "genera", "conferma": "1", "giornata": "", "csrf": tok,
        "appunti": "Scrivere a terzo@esempio.it per il documento."})
    assert r.status_code == 303
    inviato = ctx.fake.richieste[0]["messages"][0]["content"]
    assert "terzo@esempio.it" not in inviato and "[EMAIL_1]" in inviato


def test_blocco_invio_se_il_filtro_lascia_residui(ctx, monkeypatch):
    """Rete di sicurezza: se per un difetto il filtro non ripulisce, l'invio si ferma."""
    from app.privacy.pseudonymizer import Pseudonymizer
    monkeypatch.setattr(Pseudonymizer, "anonimizza", lambda self, t: t)
    c = entra(ctx)
    pid = nuova_pratica(c)
    tok = csrf(c, f"/pratiche/{pid}/atto/nuovo?fase=avvio")
    r = c.post(f"/pratiche/{pid}/atto/nuovo", data={
        "fase": "avvio", "azione": "genera", "conferma": "1", "giornata": "", "csrf": tok, "appunti": "Mario Rossi"})
    assert "BLOCCATO" in r.text and not ctx.fake.richieste
    with ctx.SM() as s:
        assert s.scalars(select(LogAI)).all()[-1].esito == "bloccato"


def test_ai_disattivata_senza_chiave(ctx, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    app = create_app(ctx.st, ctx.SM, ai_client=None)
    c = TestClient(app, follow_redirects=False)
    x = SimpleNamespace(c=c, segreto=ctx.segreto)
    entra(x)
    pid = nuova_pratica(c)
    tok = csrf(c, f"/pratiche/{pid}/atto/nuovo?fase=avvio")
    r = c.post(f"/pratiche/{pid}/atto/nuovo", data={"fase": "avvio", "azione": "genera", "conferma": "1",
                                                     "appunti": "x", "giornata": "", "csrf": tok})
    assert "disattivato" in r.text


def test_intestazioni_sicurezza(ctx):
    r = ctx.c.get("/login")
    assert r.headers["cache-control"] == "no-store" and "frame-ancestors 'none'" in r.headers["content-security-policy"]
