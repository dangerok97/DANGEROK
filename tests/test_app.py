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
        self.messages = SimpleNamespace(create=self._web)
        self.web = []

    def _web(self, **kw):
        self.web.append(kw)
        cit = SimpleNamespace(type="web_search_result_location", url="https://www.agenziaentrate.gov.it/c24e",
                              title="Circolare 24/E", cited_text="Il credito concorre al reddito")
        return SimpleNamespace(stop_reason="end_turn", content=[
            SimpleNamespace(type="text", text="Sintesi normativa.", citations=[cit])])

    def _create(self, **kw):
        self.richieste.append(kw)
        user = kw["messages"][0]["content"]
        m = re.search(r"\[PERSONA_1\]", user)
        testo = f"Il giorno odierno {m.group(0) if m else '[DA COMPILARE: soggetto]'} ha esibito la documentazione."
        if "SEZIONE C" in str(kw.get("system", "")):
            import json as _j
            testo = _j.dumps({c: {"testo": f"Testo proposto {c} su [PERSONA_1]", "spiegazione": f"Derivato dai dati A/B per {c}"}
                              for c in ("C1", "C2", "C3", "C4", "C5", "C6")})
        elif "PROMPT" in str(kw.get("system", "")) or "piano di fasi" in str(kw.get("system", "")):
            testo = '[{"chiave":"indiretto_presuntivo","esito":"consigliata","motivo":"Ragione basata su movimenti."}]'
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


def test_piano_suggerito_e_applicato(ctx):
    c = entra(ctx)
    pid = nuova_pratica(c, forma="professionista", regime="forfettario", modalita="reparto", ragione="Soglia 85.000")
    tok = csrf(c, f"/pratiche/{pid}")
    assert c.post(f"/pratiche/{pid}/piano/suggerisci", data={"csrf": tok, "con_ai": "1"}).status_code == 303
    pagina = c.get(f"/pratiche/{pid}").text
    assert "non pertinente" in pagina and "Ragione basata su movimenti" in pagina and "(AI)" in pagina
    assert c.post(f"/pratiche/{pid}/piano/applica", data={"csrf": tok}).status_code == 303
    with ctx.SM() as s:
        stati = {f.chiave: f.stato for f in s.get(Pratica, pid).fasi}
    assert stati["riscontro_materiale"] == "non_applicabile" and stati["avvio"] == "da_fare"
    # l'AI ha ricevuto il profilo senza dati reali
    assert all("Rossi" not in str(r["messages"]) for r in ctx.fake.richieste)


def test_ricerca_normativa_registra_le_fonti(ctx):
    c = entra(ctx)
    pid = nuova_pratica(c)
    tok = csrf(c, f"/pratiche/{pid}/norme")
    r = c.post(f"/pratiche/{pid}/norme", data={"csrf": tok, "periodo": "2023",
                                              "quesito": "Trattamento reddituale del credito da sconto in fattura"})
    assert r.status_code == 200 and "Sintesi normativa." in r.text and "agenziaentrate.gov.it/c24e" in r.text
    assert "ufficiale" in r.text and "Circolare 24/E" in r.text
    r = c.get(f"/pratiche/{pid}/norme")
    assert "Circolare 24/E" in r.text


def test_ricerca_normativa_non_invia_dati_del_caso(ctx):
    c = entra(ctx)
    pid = nuova_pratica(c)
    tok = csrf(c, f"/pratiche/{pid}/norme")
    c.post(f"/pratiche/{pid}/norme", data={"csrf": tok, "periodo": "2023",
                                          "quesito": f"Situazione di Mario Rossi, {cf_fittizio()}, via dei Test n. 27"})
    inviato = str(ctx.fake.web[0]["messages"])
    assert "Rossi" not in inviato and cf_fittizio() not in inviato and "dei Test" not in inviato


def test_download_word_con_e_senza_spiegazioni(ctx):
    c = entra(ctx)
    pid = nuova_pratica(c)
    with ctx.SM() as s:
        from app.models import Atto
        cif = security.Cifratore(ctx.st.data_key)
        a = Atto(pratica_id=pid, tipo="PVOC", giornata="01/01/2026", generato_da_ai=1,
                 contenuto_cifrato=cif.cifra_testo("Testo. {{SPIEGA: motivo}}"))
        s.add(a); s.commit(); aid = a.id
    r1 = c.get(f"/pratiche/{pid}/atto/{aid}/word?spiegazioni=1")
    r0 = c.get(f"/pratiche/{pid}/atto/{aid}/word?spiegazioni=0")
    assert r1.status_code == 200 and "con-spiegazioni" in r1.headers["content-disposition"]
    assert b"Spiegazione" in __import__("zipfile").ZipFile(__import__("io").BytesIO(r1.content)).read("word/document.xml")
    assert b"Spiegazione" not in __import__("zipfile").ZipFile(__import__("io").BytesIO(r0.content)).read("word/document.xml")
    assert c.get(f"/pratiche/{pid}/atto/{aid}/word").status_code == 200


def test_calcoli_da_interfaccia_fino_al_word(ctx):
    c = entra(ctx)
    pid = nuova_pratica(c)
    tok = csrf(c, f"/pratiche/{pid}/calcoli")
    for et, val, fonte in [("Fatturato 2023", "96.400,00", "fatture, all. 2"), ("Dichiarato 2023", "93.000,00", "rigo LM22, all. 3")]:
        assert c.post(f"/pratiche/{pid}/calcoli/dato", data={"csrf": tok, "etichetta": et, "valore": val, "fonte": fonte}).status_code == 303
    assert c.post(f"/pratiche/{pid}/calcoli/dato", data={"csrf": tok, "etichetta": "x", "valore": "abc", "fonte": "f"}).status_code == 400
    assert c.post(f"/pratiche/{pid}/calcoli/op", data={"csrf": tok, "tipo": "differenza", "etichetta": "Differenza",
                                                       "operandi": "D1, D2"}).status_code == 303
    assert c.post(f"/pratiche/{pid}/calcoli/op", data={"csrf": tok, "tipo": "differenza", "etichetta": "Errata",
                                                       "operandi": "D1, D9"}).status_code == 400
    assert "3.400,00" in c.get(f"/pratiche/{pid}/calcoli").text
    ctx.fake_testo = "Differenza di {{IMPORTO:C1}} tra fatturato e dichiarato."
    tok = csrf(c, f"/pratiche/{pid}/atto/nuovo?fase=avvio")
    ctx.fake._create_orig = ctx.fake._create
    def _c(**kw):
        ctx.fake.richieste.append(kw)
        return SimpleNamespace(stop_reason="end_turn", model="m", content=[SimpleNamespace(type="text", text=ctx.fake_testo)])
    ctx.fake.beta.messages.create = _c
    r = c.post(f"/pratiche/{pid}/atto/nuovo", data={"fase": "avvio", "azione": "genera", "conferma": "1", "appunti": "x",
                                                   "giornata": "", "csrf": tok})
    assert r.status_code == 303
    pagina = c.get(r.headers["location"]).text
    assert "euro 3.400,00" in pagina and "Calcolo C1" in pagina and "96.400,00" in pagina


def test_url_database_normalizzato_e_salute(ctx):
    from app.config import normalizza_database_url as n
    assert n("postgres://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert n("postgresql://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert n("sqlite:///x.db") == "sqlite:///x.db"
    assert ctx.c.get("/salute").json() == {"stato": "ok"}
    from sqlalchemy import create_engine
    create_engine(n("postgres://u:p@localhost/db"))      # il driver psycopg e' installabile


def test_bootstrap_utente_da_variabili(tmp_path, monkeypatch):
    st = Settings(database_url=f"sqlite:///{tmp_path}/b.db", data_key=security.nuova_chiave_fernet(),
                  session_secret="y" * 40, https_only=False, anthropic_model="m")
    SM = crea_sessionmaker(crea_engine(st.database_url))
    seg = security.nuovo_segreto_totp()
    monkeypatch.setenv("BOOTSTRAP_PASSWORD_HASH", security.hash_password(PW))
    monkeypatch.setenv("BOOTSTRAP_TOTP_SECRET", seg)
    app = create_app(st, SM)
    create_app(st, SM)                                   # secondo avvio: non crea un secondo utente
    with SM() as s:
        assert len(s.scalars(select(Utente)).all()) == 1
    x = SimpleNamespace(c=TestClient(app, follow_redirects=False), segreto=seg)
    entra(x)                                             # l'accesso funziona con password + TOTP


def test_chiave_dati_derivata_da_stringa_qualsiasi():
    a, b = security.Cifratore("una-stringa-casuale-molto-lunga-123456"), security.Cifratore("una-stringa-casuale-molto-lunga-123456")
    assert b.decifra_testo(a.cifra_testo("ciao")) == "ciao"
    altra = security.Cifratore("un-altra-stringa-casuale-molto-lunga-99")
    with pytest.raises(Exception):
        altra.decifra_testo(a.cifra_testo("ciao"))
    with pytest.raises(RuntimeError):
        security.Cifratore("corta")
    k = security.nuova_chiave_fernet()                 # una chiave Fernet valida resta invariata
    assert security.Cifratore(k).decifra_testo(security.Cifratore(k).cifra_testo("x")) == "x"


def _app_setup(tmp_path, token="tok-di-configurazione-lungo"):
    st = Settings(database_url=f"sqlite:///{tmp_path}/s.db", data_key="chiave-dati-casuale-molto-lunga-000000",
                  session_secret="z" * 40, https_only=False, anthropic_model="m", setup_token=token)
    SM = crea_sessionmaker(crea_engine(st.database_url))
    return st, SM, TestClient(create_app(st, SM), follow_redirects=False)


def test_configurazione_iniziale_da_browser(tmp_path):
    st, SM, c = _app_setup(tmp_path)
    assert "configura il tuo accesso" in c.get("/login").text
    t = csrf(c, "/configura")
    # codice sbagliato e password debole vengono respinti
    assert "non valido" in c.post("/configura", data={"fase": "1", "token": "no", "password": PW, "password2": PW, "csrf": t}).text
    assert "almeno 12" in c.post("/configura", data={"fase": "1", "token": st.setup_token, "password": "corta", "password2": "corta", "csrf": t}).text
    r = c.post("/configura", data={"fase": "1", "token": st.setup_token, "password": PW, "password2": PW, "csrf": t})
    assert "data:image/svg+xml;base64," in r.text
    segreto = re.search(r"<code>([A-Z2-7]{16,})</code>", r.text).group(1)
    # codice TOTP errato: l'utente non viene creato
    assert "non corretto" in c.post("/configura", data={"fase": "2", "codice": "000000", "csrf": t}).text
    with SM() as s:
        assert s.scalars(select(Utente)).all() == []
    r = c.post("/configura", data={"fase": "2", "codice": pyotp.TOTP(segreto).now(), "csrf": t})
    assert r.status_code == 303 and r.headers["location"] == "/login"
    # la pagina sparisce e l'accesso funziona con la password scelta e il TOTP
    assert c.get("/configura").status_code == 404
    x = SimpleNamespace(c=c, segreto=segreto)
    entra(x)


def test_configurazione_disattivata_senza_token(tmp_path):
    _, _, c = _app_setup(tmp_path, token="")
    assert c.get("/configura").status_code == 404


def test_scheda_ai_completa_solo_la_sezione_c_e_non_sovrascrive(ctx):
    c = entra(ctx)
    pid = nuova_pratica(c)
    tok = csrf(c, f"/pratiche/{pid}/scheda")
    # A e B arrivano dalla banca dati (qui inseriti a mano); C3 e' gia' stato scritto dall'operatore
    c.post(f"/pratiche/{pid}/scheda", data={"csrf": tok, "A1": piva_fittizia(), "A2": cf_fittizio(),
           "A3": "Sede in via dei Test n. 27, Mario Rossi", "B1": "2023, 2024", "C3": "Testo scritto da me"})
    r = c.post(f"/pratiche/{pid}/scheda/proponi", data={"csrf": tok, "appunti": "Controllo d'iniziativa"})
    assert r.status_code == 303
    pagina = c.get(f"/pratiche/{pid}/scheda").text
    assert "Testo scritto da me" in pagina                       # non sovrascritto
    assert "Testo proposto C1 su Mario Rossi" in pagina           # segnaposto ripristinato
    assert "Derivato dai dati A/B per C1" in pagina and "Derivato dai dati A/B per C3" not in pagina
    inviato = str(ctx.fake.richieste[-1])
    for dato in ("Rossi", cf_fittizio(), piva_fittizia(), "dei Test"):
        assert dato not in inviato
    assert "SEZIONE C" in ctx.fake.richieste[-1]["system"] and '"A2"' in ctx.fake.richieste[-1]["messages"][0]["content"]


def test_scheda_ai_senza_chiave_mostra_errore(ctx, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    app = create_app(ctx.st, ctx.SM, ai_client=None)
    c = TestClient(app, follow_redirects=False)
    entra(SimpleNamespace(c=c, segreto=ctx.segreto))
    pid = nuova_pratica(c)
    tok = csrf(c, f"/pratiche/{pid}/scheda")
    r = c.post(f"/pratiche/{pid}/scheda/proponi", data={"csrf": tok, "appunti": ""})
    assert r.status_code == 303 and "disattivato" in c.get(r.headers["location"]).text


def test_impostazioni_e_prova_ai(ctx, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-chiave-di-prova-1234")
    c = entra(ctx)
    pagina = c.get("/impostazioni").text
    assert "chiave configurata" in pagina and "1234" in pagina and "sk-ant-chiave" not in pagina   # mascherata
    tok = csrf(c, "/impostazioni")
    r = c.post("/impostazioni/prova", data={"csrf": tok})
    assert r.status_code == 200 and "Collegamento riuscito" in r.text


def test_prova_ai_errori_chiari(ctx, monkeypatch):
    import anthropic
    import httpx2
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-chiave-di-prova-1234")
    resp = httpx2.Response(401, request=httpx2.Request("POST", "https://x"))
    def rifiuta(**kw):
        raise anthropic.AuthenticationError("no", response=resp, body=None)
    ctx.fake.beta.messages.create = rifiuta
    c = entra(ctx)
    tok = csrf(c, "/impostazioni")
    assert "Chiave non valida" in c.post("/impostazioni/prova", data={"csrf": tok}).text
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    app = create_app(ctx.st, ctx.SM, ai_client=None)
    c2 = TestClient(app, follow_redirects=False)
    entra(SimpleNamespace(c=c2, segreto=ctx.segreto))
    t2 = csrf(c2, "/impostazioni")
    assert "AI spenta" in c2.get("/impostazioni").text and "disattivato" in c2.post("/impostazioni/prova", data={"csrf": t2}).text


def test_invito_da_interfaccia_fino_al_word(ctx):
    import io
    import docx
    c = entra(ctx)
    pid = nuova_pratica(c)
    tok = csrf(c, "/impostazioni")
    c.post("/impostazioni/reparto", data={"csrf": tok, "comandante": "Ten. Nome COGNOME", "in_sv": "1",
                                          "referenti": "Lgt. Uno UNO\nMar. Due DUE", "telefono": "0766/856028"})
    assert "Ten. Nome COGNOME" in c.get("/impostazioni").text
    # la fase invito porta al modulo dedicato, non all'AI
    r = c.get(f"/pratiche/{pid}/atto/nuovo?fase=invito")
    assert r.status_code == 303 and r.headers["location"] == f"/pratiche/{pid}/invito"
    pagina = c.get(f"/pratiche/{pid}/invito").text
    assert "MARIO ROSSI" in pagina.upper() and "Documentazione da recare" in pagina
    tok = csrf(c, f"/pratiche/{pid}/invito")
    r = c.post(f"/pratiche/{pid}/invito", data={"csrf": tok, "forma_prefisso": "Ditta ind.le", "denominazione": "ROSSI MARIO",
                                                "luogo": "Tarquinia (VT) via dei Test, nr. 1", "cf": cf_fittizio(), "piva": piva_fittizia(),
                                                "titolo_destinatario": "Sig.", "destinatario": "ROSSI MARIO",
                                                "indirizzo_destinatario": "Via dei Test n. 1 - TARQUINIA",
                                                "periodi": "2022, 2023", "documenti": "Fatture di vendita\nFatture di acquisto",
                                                "motivazione": "emergono scostamenti"})
    assert r.status_code == 303
    w = c.get(f"/pratiche/{pid}/invito/word")
    assert w.status_code == 200 and "INVITO_C-" in w.headers["content-disposition"]
    d = docx.Document(io.BytesIO(w.content))
    t = "\n".join(p.text for p in d.paragraphs)
    assert "COMPAGNIA TARQUINIA" in t and "della ditta individuale “ROSSI MARIO”" in t and "(Ten. Nome COGNOME)" in t
    assert "con il Lgt. Uno UNO - Mar. Due DUE" in t and "periodi d’imposta 2022, 2023" in t
    assert round(d.sections[0].page_width.cm, 1) == 21.0
