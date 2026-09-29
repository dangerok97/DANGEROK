from __future__ import annotations

import datetime as dt
import hmac
import pathlib
import re
import secrets

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from starlette.middleware.sessions import SessionMiddleware

from . import ai as ai_mod
from . import atti_word, calcoli, pvoc as pvoc_mod, invito_word, llm_compat, norme, scheda_ai, piano as piano_mod, schede, security, tipologie, workflow, wordexport
from .config import Settings
from .db import crea_engine, crea_sessionmaker
from .models import Atto, FasePratica, FonteNormativa, Impostazione, LogAI, Pratica, Utente

BASE = pathlib.Path(__file__).parent
ISTRUZIONI = {
    "PVOC": "Redigi il processo verbale di operazioni compiute per la giornata indicata (giornata SUCCESSIVA alla prima), "
            "per la fase indicata. Struttura OBBLIGATORIA, senza inventare titoletti ne' sezioni: (1) apertura \"Il giorno "
            "[data], alle ore [ora], in Tarquinia (VT), presso gli uffici del Reparto operante, viene riaperto il processo "
            "verbale relativo alle operazioni di controllo intraprese in data [data primo giorno] nei confronti della "
            "[parte], per far constatare che i sottoscritti militari verbalizzanti:\"; (2) elenco dei verbalizzanti, uno "
            "per riga con \"- \"; (3) \"hanno ripreso le operazioni di controllo senza la presenza della parte.\" (o con "
            "la parte, se presente); (4) riga in MAIUSCOLO \"OPERAZIONI DI CONTROLLO ESEGUITE NEL GIORNO gg.mm.aaaa\"; "
            "(5) titolo dell'attivita' svolta (una sola) e descrizione in prosa formale; (6) chiusura: \"Il presente atto che "
            "si compone di n. [X] foglio/fogli, viene redatto in due esemplari di cui uno verra' consegnato alla parte alla "
            "prima favorevole occasione.\", \"Le operazioni come sopra descritte si sono concluse alle ore [ora] circa di "
            "oggi stesso.\", \"Fatto, letto e chiuso in data e luogo come sopra, viene confermato e sottoscritto dai soli "
            "verbalizzanti.\" e la riga \"I VERBALIZZANTI\". Non scrivere il paragrafo di apertura del primo giorno.",
    "PVV": "Redigi la bozza del processo verbale di verifica per la giornata indicata, "
           "per la fase indicata, seguendo la struttura e il lessico del Reparto.",
    "PVC": "Redigi la bozza del processo verbale di constatazione (Vol. IV, Allegato 19) con le sezioni "
           "previste, usando solo i fatti presenti negli atti e negli appunti.",
    "CNR": "Redigi la bozza della comunicazione di notizia di reato ex art. 347 c.p.p. (dati sintetici, premessa, "
           "attivita' operativa, sezioni tematiche, allegati), usando solo i fatti presenti negli atti e negli appunti.",
    "INVITO": "Redigi la bozza dell'invito a presentarsi (Vol. IV, Allegato 14) con le sezioni previste.",
}


def _bootstrap_utente(SM, cif) -> None:
    """Primo avvio su un server senza terminale: crea l'UNICO utente da due variabili d'ambiente generate in
    locale con `python -m app.cli prepara-accesso` (hash della password e segreto TOTP; mai la password).
    Dopo il primo avvio le variabili vanno RIMOSSE. Se esiste gia' un utente non fa nulla."""
    import os
    h, t = os.environ.get("BOOTSTRAP_PASSWORD_HASH"), os.environ.get("BOOTSTRAP_TOTP_SECRET")
    if not (h and t):
        return
    with SM() as s:
        if s.scalar(select(Utente.id)) is None:
            s.add(Utente(nome="utente", password_hash=h, totp_cifrato=cif.cifra_testo(t)))
            s.commit()


def create_app(settings: Settings | None = None, sessionmaker=None, ai_client=None) -> FastAPI:
    st = settings or Settings.load()
    SM = sessionmaker or crea_sessionmaker(crea_engine(st.database_url))
    cif = security.Cifratore(st.data_key)
    _bootstrap_utente(SM, cif)
    app = FastAPI(title="Dangerok", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(SessionMiddleware, secret_key=st.session_secret, max_age=st.session_max_age,
                       same_site="strict", https_only=st.https_only, session_cookie="dgk")
    templates = Jinja2Templates(directory=str(BASE / "templates"))
    app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")

    @app.middleware("http")
    async def intestazioni(request: Request, call_next):
        resp = await call_next(request)
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Content-Security-Policy"] = ("default-src 'self'; style-src 'self'; script-src 'self'; "
                                                   "img-src 'self' data:; frame-ancestors 'none'; form-action 'self'")
        if not request.url.path.startswith("/static"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    # ---------------------------------------------------------------- helper
    def db():
        s = SM()
        try:
            yield s
        finally:
            s.close()

    def csrf_token(request: Request) -> str:
        if "csrf" not in request.session:
            request.session["csrf"] = secrets.token_urlsafe(24)
        return request.session["csrf"]

    def check_csrf(request: Request, csrf: str) -> None:
        if not hmac.compare_digest(request.session.get("csrf", ""), csrf or ""):
            raise HTTPException(403, "Token di sicurezza non valido")

    def utente_corrente(request: Request, s=Depends(db)) -> Utente:
        uid = request.session.get("uid")
        u = s.get(Utente, uid) if uid else None
        if not u:
            raise HTTPException(status_code=303, headers={"Location": "/login"})
        return u

    def render(request: Request, nome: str, **ctx) -> HTMLResponse:
        return templates.TemplateResponse(request, nome, {"csrf": csrf_token(request), **ctx})

    def dati_di(p: Pratica) -> dict:
        return cif.decifra_json(p.dati_cifrati) or {}

    def salva_dati(p: Pratica, d: dict) -> None:
        p.dati_cifrati = cif.cifra_json(d)

    def stati_di(p: Pratica) -> dict[str, str]:
        return {f.chiave: f.stato for f in p.fasi}

    def righe(testo: str) -> list[str]:
        return [r.strip() for r in (testo or "").splitlines() if r.strip()]

    def carica(s, pid: int) -> Pratica:
        p = s.get(Pratica, pid)
        if not p:
            raise HTTPException(404, "Pratica non trovata")
        return p

    # ---------------------------------------------------------------- configurazione iniziale (una sola volta)
    def _qr_svg(uri: str) -> str:
        import base64 as b64
        import qrcode
        import qrcode.image.svg
        img = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage, box_size=8)
        return "data:image/svg+xml;base64," + b64.b64encode(img.to_string()).decode()

    def _setup_attivo(s) -> bool:
        return bool(st.setup_token) and s.scalar(select(Utente.id)) is None

    @app.get("/configura", response_class=HTMLResponse)
    def configura_form(request: Request, s=Depends(db)):
        if not _setup_attivo(s):
            raise HTTPException(404)
        return render(request, "configura.html", errore=None, qr=None, segreto=None)

    @app.post("/configura", response_class=HTMLResponse)
    def configura(request: Request, fase: str = Form(...), token: str = Form(""), password: str = Form(""),
                  password2: str = Form(""), codice: str = Form(""), csrf: str = Form(""), s=Depends(db)):
        check_csrf(request, csrf)
        if not _setup_attivo(s):
            raise HTTPException(404)
        if fase == "1":
            if not hmac.compare_digest(token.strip(), st.setup_token):
                return render(request, "configura.html", errore="Codice di configurazione non valido.", qr=None,
                              segreto=None)
            if len(password) < 12 or password != password2:
                return render(request, "configura.html", errore="La password deve avere almeno 12 caratteri "
                              "e coincidere nei due campi.", qr=None, segreto=None)
            segreto = security.nuovo_segreto_totp()
            request.session["setup"] = {"hash": security.hash_password(password), "totp": segreto}
            return render(request, "configura.html", errore=None, segreto=segreto,
                          qr=_qr_svg(security.uri_totp(segreto, "utente")))
        pend = request.session.get("setup")
        if not pend:
            return render(request, "configura.html", errore="Sessione scaduta: ricomincia.", qr=None, segreto=None)
        if not security.verifica_totp(pend["totp"], codice):
            return render(request, "configura.html", errore="Codice non corretto: riprova con quello attuale.",
                          segreto=pend["totp"], qr=_qr_svg(security.uri_totp(pend["totp"], "utente")))
        s.add(Utente(nome="utente", password_hash=pend["hash"], totp_cifrato=cif.cifra_testo(pend["totp"])))
        s.commit()
        request.session.clear()
        return RedirectResponse("/login", status_code=303)

    # ---------------------------------------------------------------- accesso
    @app.get("/login", response_class=HTMLResponse)
    def login_form(request: Request, s=Depends(db)):
        configurato = s.scalar(select(Utente.id)) is not None
        return render(request, "login.html", errore=None, configurato=configurato, setup=_setup_attivo(s))

    @app.post("/login")
    def login(request: Request, password: str = Form(""), codice: str = Form(""), csrf: str = Form(""),
              s=Depends(db)):
        check_csrf(request, csrf)
        u = s.scalar(select(Utente))
        adesso = dt.datetime.now(dt.timezone.utc)
        generico = "Credenziali non valide o accesso temporaneamente bloccato."
        if not u:
            return render(request, "login.html", errore=generico, configurato=False, setup=_setup_attivo(s))
        blocco = u.bloccato_fino
        if blocco is not None and blocco.tzinfo is None:
            blocco = blocco.replace(tzinfo=dt.timezone.utc)
        if blocco and blocco > adesso:
            return render(request, "login.html", errore=generico, configurato=True, setup=False)
        ok = security.verify_password(u.password_hash, password) and \
            security.verifica_totp(cif.decifra_testo(u.totp_cifrato), codice)
        if not ok:
            u.tentativi_falliti += 1
            if u.tentativi_falliti >= st.max_login_failures:
                u.bloccato_fino = adesso + dt.timedelta(minutes=st.lock_minutes)
                u.tentativi_falliti = 0
            s.commit()
            return render(request, "login.html", errore=generico, configurato=True, setup=False)
        u.tentativi_falliti, u.bloccato_fino = 0, None
        s.commit()
        request.session.clear()
        request.session["uid"] = u.id
        return RedirectResponse("/pratiche", status_code=303)

    @app.post("/logout")
    def logout(request: Request, csrf: str = Form("")):
        check_csrf(request, csrf)
        request.session.clear()
        return RedirectResponse("/login", status_code=303)

    @app.get("/")
    def home():
        return RedirectResponse("/pratiche", status_code=303)

    # ---------------------------------------------------------------- pratiche
    @app.get("/pratiche", response_class=HTMLResponse)
    def elenco(request: Request, u=Depends(utente_corrente), s=Depends(db)):
        pratiche = s.scalars(select(Pratica).order_by(Pratica.id.desc())).all()
        righe_ = []
        for p in pratiche:
            prox = workflow.prossima_fase(p.tipo, stati_di(p))
            righe_.append({"p": p, "prossima": prox.titolo if prox else "Percorso concluso"})
        return render(request, "pratiche.html", righe=righe_)

    @app.get("/pratiche/nuova", response_class=HTMLResponse)
    def nuova_form(request: Request, u=Depends(utente_corrente)):
        return render(request, "nuova.html", tipologie=tipologie.elenco())

    @app.post("/pratiche/nuova")
    def nuova(request: Request, tipo: str = Form(...), tipologia: str = Form("generica"), privato: str = Form(""),
              persone: str = Form(""), enti: str = Form(""), codici_fiscali: str = Form(""),
              partite_iva: str = Form(""), indirizzi: str = Form(""), verbalizzanti: str = Form(""),
              forma: str = Form("impresa"), regime: str = Form("non_noto"), modalita: str = Form("reparto"),
              ragione: str = Form(""), csrf: str = Form(""), u=Depends(utente_corrente), s=Depends(db)):
        check_csrf(request, csrf)
        if tipo not in workflow.PERCORSI or tipologia not in tipologie.TIPOLOGIE:
            raise HTTPException(400, "Tipo non valido")
        if forma not in piano_mod.FORME or regime not in piano_mod.REGIMI or modalita not in piano_mod.MODALITA:
            raise HTTPException(400, "Profilo non valido")
        anno = dt.date.today().year
        n = len(s.scalars(select(Pratica.id).where(Pratica.codice.like(f"%-{anno}-%"))).all()) + 1
        p = Pratica(codice=f"{'C' if tipo == 'controllo' else 'V'}-{anno}-{n:03d}", tipo=tipo, tipologia=tipologia)
        salva_dati(p, {"privato": bool(privato),
                       "soggetto": {"persone": righe(persone), "enti": righe(enti),
                                    "codici_fiscali": righe(codici_fiscali), "partite_iva": righe(partite_iva),
                                    "indirizzi": righe(indirizzi)},
                       "verbalizzanti": righe(verbalizzanti), "terzi": [], "scheda": {},
                       "profilo": {"forma": forma, "regime": regime, "modalita": modalita, "ragione": ragione.strip(),
                                   "documenti": [], "tributi": ["IIDD", "IVA"]},
                       "piano": []})
        s.add(p)
        s.flush()
        for f in workflow.fasi_per(tipo):
            s.add(FasePratica(pratica_id=p.id, chiave=f.chiave))
        s.commit()
        return RedirectResponse(f"/pratiche/{p.id}", status_code=303)

    @app.get("/pratiche/{pid}", response_class=HTMLResponse)
    def dettaglio(request: Request, pid: int, u=Depends(utente_corrente), s=Depends(db)):
        p = carica(s, pid)
        stati = stati_di(p)
        prox = workflow.prossima_fase(p.tipo, stati)
        d = dati_di(p)
        sugg = {x["chiave"]: x for x in d.get("piano", [])}
        fasi = [{"f": f, "stato": stati.get(f.chiave, "da_fare"), "sugg": sugg.get(f.chiave)}
                for f in workflow.fasi_per(p.tipo)]
        return render(request, "pratica.html", p=p, fasi=fasi, prossima=prox, atti=p.atti,
                      tip=tipologie.TIPOLOGIE[p.tipologia], ha_piano=bool(sugg),
                      mancanti=piano_mod.promemoria_documenti(d.get("profilo", {})))

    @app.post("/pratiche/{pid}/fase/{chiave}")
    def cambia_fase(request: Request, pid: int, chiave: str, azione: str = Form(...), motivo: str = Form(""),
                    csrf: str = Form(""), u=Depends(utente_corrente), s=Depends(db)):
        check_csrf(request, csrf)
        p = carica(s, pid)
        try:
            fase = workflow.fase_per_chiave(p.tipo, chiave)
        except KeyError:
            raise HTTPException(404)
        rec = next(f for f in p.fasi if f.chiave == chiave)
        try:
            if azione in ("avvia", "completa"):
                workflow.puo_avviare(p.tipo, chiave, stati_di(p))
                rec.stato = "in_corso" if azione == "avvia" else "completata"
            elif azione == "non_applicabile":
                if not workflow.puo_dichiarare_non_applicabile(p.tipo, chiave):
                    raise HTTPException(400, "Questa fase e' obbligatoria")
                if not motivo.strip():
                    raise HTTPException(400, "Serve una motivazione")
                workflow.puo_avviare(p.tipo, chiave, stati_di(p))
                rec.stato, rec.motivo_cifrato = "non_applicabile", cif.cifra_testo(motivo.strip())
            else:
                raise HTTPException(400, "Azione non valida")
        except workflow.OrdineViolato as e:
            raise HTTPException(409, str(e))
        s.commit()
        return RedirectResponse(f"/pratiche/{pid}", status_code=303)

    # ---------------------------------------------------------------- scheda Allegato 23
    @app.get("/pratiche/{pid}/scheda", response_class=HTMLResponse)
    def scheda_form(request: Request, pid: int, u=Depends(utente_corrente), s=Depends(db)):
        p = carica(s, pid)
        d = dati_di(p)
        campi = schede.campi_allegato23(d.get("privato", False))
        valori = d.get("scheda", {})
        mancanti = schede.completezza(valori, d.get("privato", False))
        return render(request, "scheda.html", p=p, campi=campi, valori=valori,
                      spieg=d.get("scheda_spiegazioni", {}),
                      da_importare=[c for c in mancanti if c[0] in "AB"],
                      da_completare=[c for c in mancanti if c[0] == "C"], errore=request.query_params.get("errore"))

    @app.post("/pratiche/{pid}/scheda")
    async def scheda_salva(request: Request, pid: int, u=Depends(utente_corrente), s=Depends(db)):
        f = await request.form()
        check_csrf(request, f.get("csrf", ""))
        p = carica(s, pid)
        d = dati_di(p)
        validi = {c.codice for c in schede.campi_allegato23(d.get("privato", False))}
        d["scheda"] = {k: str(v) for k, v in f.items() if k in validi}
        salva_dati(p, d)
        s.commit()
        return RedirectResponse(f"/pratiche/{pid}/scheda", status_code=303)

    # ---------------------------------------------------------------- calcoli tracciati
    def _calcoli_ctx(p: Pratica, errore=None):
        cfg = dati_di(p).get("calcoli", {"dati": [], "calcoli": []})
        try:
            reg = calcoli.registro_da_dati(cfg)
        except calcoli.CalcoloErrore as e:
            reg, errore = calcoli.Registro(), errore or str(e)
        return dict(p=p, cfg=cfg, reg=reg, errore=errore, euro=calcoli.euro)

    @app.get("/pratiche/{pid}/calcoli", response_class=HTMLResponse)
    def calcoli_vista(request: Request, pid: int, u=Depends(utente_corrente), s=Depends(db)):
        return render(request, "calcoli.html", **_calcoli_ctx(carica(s, pid)))

    @app.post("/pratiche/{pid}/calcoli/dato")
    def calcoli_dato(request: Request, pid: int, etichetta: str = Form(...), valore: str = Form(...),
                     fonte: str = Form(...), unita: str = Form("euro"), csrf: str = Form(""),
                     u=Depends(utente_corrente), s=Depends(db)):
        check_csrf(request, csrf)
        p = carica(s, pid)
        d = dati_di(p)
        cfg = d.setdefault("calcoli", {"dati": [], "calcoli": []})
        try:
            calcoli.parse_importo(valore)
        except Exception:
            raise HTTPException(400, "Valore non valido")
        if unita not in ("euro", "percentuale") or not etichetta.strip() or not fonte.strip():
            raise HTTPException(400, "Etichetta e fonte sono obbligatorie")
        cfg["dati"].append({"id": f"D{len(cfg['dati']) + 1}", "etichetta": etichetta.strip(),
                            "valore": valore.strip(), "fonte": fonte.strip(), "unita": unita})
        salva_dati(p, d)
        s.commit()
        return RedirectResponse(f"/pratiche/{pid}/calcoli", status_code=303)

    @app.post("/pratiche/{pid}/calcoli/op")
    def calcoli_op(request: Request, pid: int, tipo: str = Form(...), etichetta: str = Form(...),
                   operandi: str = Form(...), param: str = Form(""), csrf: str = Form(""),
                   u=Depends(utente_corrente), s=Depends(db)):
        check_csrf(request, csrf)
        p = carica(s, pid)
        d = dati_di(p)
        cfg = d.setdefault("calcoli", {"dati": [], "calcoli": []})
        nuovo = {"id": f"C{len(cfg['calcoli']) + 1}", "tipo": tipo, "etichetta": etichetta.strip(),
                 "operandi": [x.strip() for x in operandi.replace(";", ",").split(",") if x.strip()], "param": param}
        try:
            calcoli.registro_da_dati({"dati": cfg["dati"], "calcoli": cfg["calcoli"] + [nuovo]})
        except (calcoli.CalcoloErrore, Exception) as e:
            raise HTTPException(400, f"Operazione non valida: {e}")
        cfg["calcoli"].append(nuovo)
        salva_dati(p, d)
        s.commit()
        return RedirectResponse(f"/pratiche/{pid}/calcoli", status_code=303)

    # ---------------------------------------------------------------- piano suggerito
    def client_ai():
        return ai_client or ai_mod._client()

    @app.post("/pratiche/{pid}/piano/suggerisci")
    def piano_suggerisci(request: Request, pid: int, con_ai: str = Form(""), csrf: str = Form(""),
                         u=Depends(utente_corrente), s=Depends(db)):
        check_csrf(request, csrf)
        p = carica(s, pid)
        d = dati_di(p)
        profilo = {**piano_mod.profilo_predefinito(), **d.get("profilo", {})}
        piano = piano_mod.suggerisci_fasi(p.tipo, profilo)
        avviso = ""
        if con_ai:
            try:
                piano = piano_mod.raffina_con_ai(ai_mod.costruisci_pseudonimizzatore(d), p.tipo, profilo, piano,
                                                 client=client_ai(), modello=st.anthropic_model)
            except (ai_mod.AIDisattivata, ai_mod.LeakError) as e:
                avviso = str(e)
        d["piano"] = [x.__dict__ for x in piano]
        salva_dati(p, d)
        s.commit()
        return RedirectResponse(f"/pratiche/{pid}" + ("?avviso=1" if avviso else ""), status_code=303)

    @app.post("/pratiche/{pid}/piano/applica")
    def piano_applica(request: Request, pid: int, csrf: str = Form(""), u=Depends(utente_corrente),
                      s=Depends(db)):
        """Segna 'non applicabile' (con la motivazione suggerita) le fasi facoltative non pertinenti, in ordine."""
        check_csrf(request, csrf)
        p = carica(s, pid)
        d = dati_di(p)
        for x in d.get("piano", []):
            if x["esito"] != piano_mod.NON_PERTINENTE:
                continue
            fase = workflow.fase_per_chiave(p.tipo, x["chiave"])
            rec = next(f for f in p.fasi if f.chiave == x["chiave"])
            if fase.facoltativa and rec.stato == "da_fare":
                rec.stato, rec.motivo_cifrato = "non_applicabile", cif.cifra_testo("Suggerito dall'app: " + x["motivo"])
        s.commit()
        return RedirectResponse(f"/pratiche/{pid}", status_code=303)

    # ---------------------------------------------------------------- ricerca normativa
    @app.get("/pratiche/{pid}/norme", response_class=HTMLResponse)
    def norme_vista(request: Request, pid: int, u=Depends(utente_corrente), s=Depends(db)):
        p = carica(s, pid)
        fonti = s.scalars(select(FonteNormativa).where(FonteNormativa.pratica_id == pid)
                          .order_by(FonteNormativa.id.desc())).all()
        return render(request, "norme.html", p=p, fonti=fonti, ricerca=None, errore=None, domini=norme.DOMINI_UFFICIALI)

    @app.post("/pratiche/{pid}/norme", response_class=HTMLResponse)
    def norme_cerca(request: Request, pid: int, quesito: str = Form(...), periodo: str = Form(...),
                    csrf: str = Form(""), u=Depends(utente_corrente), s=Depends(db)):
        check_csrf(request, csrf)
        p = carica(s, pid)
        pseudo = ai_mod.costruisci_pseudonimizzatore(dati_di(p))
        errore, ric = None, None
        try:
            ric = norme.ricerca_normativa(pseudo, quesito, periodo, client=client_ai(), modello=st.anthropic_model)
            for f in ric.fonti:
                s.add(FonteNormativa(pratica_id=pid, quesito=quesito, periodo=periodo, url=f.url, titolo=f.titolo,
                                     estratto=f.estratto, dominio=f.dominio, ufficiale=int(f.ufficiale)))
            s.commit()
        except ai_mod.LeakError as e:
            errore = f"Quesito BLOCCATO: contiene dati riconoscibili ({e}). Formulalo in modo generale."
        except (ai_mod.AIDisattivata, llm_compat.NonSupportato) as e:
            errore = str(e)
        fonti = s.scalars(select(FonteNormativa).where(FonteNormativa.pratica_id == pid)
                          .order_by(FonteNormativa.id.desc())).all()
        return render(request, "norme.html", p=p, fonti=fonti, ricerca=ric, errore=errore, domini=norme.DOMINI_UFFICIALI)

    @app.post("/pratiche/{pid}/scheda/proponi")
    def scheda_proponi(request: Request, pid: int, appunti: str = Form(""), csrf: str = Form(""),
                       u=Depends(utente_corrente), s=Depends(db)):
        """L'AI propone SOLO i campi C ancora vuoti; non tocca cio' che l'operatore ha scritto."""
        check_csrf(request, csrf)
        p = carica(s, pid)
        d = dati_di(p)
        privato = d.get("privato", False)
        valori = d.get("scheda", {})
        vuoti = [c for c in schede.campi_allegato23(privato)
                 if c.codice.startswith("C") and not (valori.get(c.codice) or "").strip()]
        if not vuoti:
            return RedirectResponse(f"/pratiche/{pid}/scheda", status_code=303)
        try:
            prop = scheda_ai.proponi_sezione_c(ai_mod.costruisci_pseudonimizzatore(d), valori=valori,
                                               profilo=d.get("profilo", {}), appunti=appunti, campi=vuoti,
                                               client=client_ai(), modello=st.anthropic_model)
        except (ai_mod.AIDisattivata, ai_mod.LeakError, RuntimeError) as e:
            return RedirectResponse(f"/pratiche/{pid}/scheda?errore={str(e)[:160]}", status_code=303)
        sp = d.setdefault("scheda_spiegazioni", {})
        for cod, v in prop.items():
            valori[cod] = v["testo"]
            sp[cod] = v["spiegazione"]
        d["scheda"] = valori
        salva_dati(p, d)
        s.commit()
        return RedirectResponse(f"/pratiche/{pid}/scheda", status_code=303)

    # ---------------------------------------------------------------- atti e AI
    def contesto_ai(p: Pratica, d: dict, appunti: str, fase: workflow.Fase, giornata: str) -> str:
        sog = d.get("soggetto", {})
        parti = [f"Tipo di intervento: {p.tipo}. Tipologia: {tipologie.TIPOLOGIE[p.tipologia]['nome']}.",
                 f"Fase: {fase.titolo} ({fase.rif}). Giornata: {giornata or '[DA COMPILARE]'}.",
                 "Soggetto: " + "; ".join(sog.get("persone", []) + sog.get("enti", [])),
                 "Identificativi: " + "; ".join(sog.get("codici_fiscali", []) + sog.get("partite_iva", [])),
                 "Indirizzi: " + "; ".join(sog.get("indirizzi", [])),
                 "Verbalizzanti: " + "; ".join(d.get("verbalizzanti", [])),
                 "Scheda Allegato 23: " + "; ".join(f"{k}={v}" for k, v in d.get("scheda", {}).items() if v)]
        for a in p.atti[-6:]:
            parti.append(f"--- Atto precedente {a.tipo} {a.giornata} ---\n{cif.decifra_testo(a.contenuto_cifrato)}")
        parti.append(f"--- APPUNTI DELL'OPERATORE PER QUESTO ATTO ---\n{appunti}")
        return "\n".join(parti)

    @app.get("/pratiche/{pid}/atto/nuovo", response_class=HTMLResponse)
    def atto_form(request: Request, pid: int, fase: str, u=Depends(utente_corrente), s=Depends(db)):
        p = carica(s, pid)
        try:
            f = workflow.fase_per_chiave(p.tipo, fase)
        except KeyError:
            raise HTTPException(404)
        if not f.atto:
            raise HTTPException(400, "Questa fase non prevede un atto")
        if f.atto == "INVITO":
            return RedirectResponse(f"/pratiche/{pid}/invito", status_code=303)
        if f.atto == "PVOC" and f.chiave == "avvio":
            return RedirectResponse(f"/pratiche/{pid}/pvoc-primo", status_code=303)
        return render(request, "atto_nuovo.html", p=p, f=f, anteprima=None, appunti="", giornata="",
                      errore=None, bozza=None)

    @app.post("/pratiche/{pid}/atto/nuovo", response_class=HTMLResponse)
    def atto_azione(request: Request, pid: int, fase: str = Form(...), azione: str = Form(...),
                    appunti: str = Form(""), giornata: str = Form(""), conferma: str = Form(""),
                    csrf: str = Form(""), u=Depends(utente_corrente), s=Depends(db)):
        check_csrf(request, csrf)
        p = carica(s, pid)
        f = workflow.fase_per_chiave(p.tipo, fase)
        d = dati_di(p)
        pseudo = ai_mod.costruisci_pseudonimizzatore(d)
        ctx = dict(p=p, f=f, anteprima=None, appunti=appunti, giornata=giornata, errore=None, bozza=None)
        try:
            contesto = contesto_ai(p, d, appunti, f, giornata)
            if azione == "anteprima":
                system, user = ai_mod.prepara_richiesta(pseudo, istruzione=ISTRUZIONI[f.atto], contesto=contesto,
                                                        checklist=list(f.checklist),
                                                        registro=calcoli.registro_da_dati(d.get("calcoli", {})))
                ctx["anteprima"] = {"testo": user, "segnaposto": sorted(pseudo.tabella.keys())}
            elif azione == "genera":
                if not conferma:
                    ctx["errore"] = "Conferma di aver controllato l'anteprima prima di generare."
                else:
                    b = ai_mod.genera_bozza(pseudo, istruzione=ISTRUZIONI[f.atto], contesto=contesto,
                                            checklist=list(f.checklist), modello=st.anthropic_model,
                                            client=ai_client,
                                            registro=calcoli.registro_da_dati(d.get("calcoli", {})))
                    s.add(LogAI(pratica_id=p.id, sezione=f"{f.atto}/{f.chiave}", modello=b.modello,
                                testo_inviato=b.inviato))
                    a = Atto(pratica_id=p.id, tipo=f.atto, fase=f.chiave, giornata=giornata, generato_da_ai=1,
                             contenuto_cifrato=cif.cifra_testo(b.testo))
                    s.add(a)
                    s.commit()
                    return RedirectResponse(f"/pratiche/{pid}/atto/{a.id}", status_code=303)
            else:
                raise HTTPException(400, "Azione non valida")
        except ai_mod.LeakError as e:
            s.add(LogAI(pratica_id=p.id, sezione=f"{f.atto}/{f.chiave}", testo_inviato="(bloccato)", esito="bloccato"))
            s.commit()
            ctx["errore"] = f"Invio BLOCCATO: {e}. Aggiungi il dato all'anagrafica della pratica."
        except ai_mod.AIDisattivata as e:
            ctx["errore"] = str(e)
        except ai_mod.AIRifiutata as e:
            ctx["errore"] = str(e)
        return render(request, "atto_nuovo.html", **ctx)

    def pvoc_primo_iniziale(p: Pratica, d: dict) -> dict:
        sog = d.get("soggetto", {})
        persone, enti = sog.get("persone", []), sog.get("enti", [])
        base = {k: "" for k in pvoc_mod.CAMPI}
        base.update({"titolo": "Il Sig.", "tributo": "I.V.A.",
                     "denominazione": (enti[0] if enti else (persone[0] if persone else "")),
                     "rappresentante": persone[0] if persone else "", "luogo": (sog.get("indirizzi") or [""])[0],
                     "residenza": (sog.get("indirizzi") or [""])[0], "cf": (sog.get("codici_fiscali") or [""])[0],
                     "piva": (sog.get("partite_iva") or [""])[0],
                     "ragione": d.get("profilo", {}).get("ragione", "")})
        return {**base, **d.get("pvoc_primo", {})}

    @app.get("/pratiche/{pid}/pvoc-primo", response_class=HTMLResponse)
    def pvoc_primo_form(request: Request, pid: int, u=Depends(utente_corrente), s=Depends(db)):
        p = carica(s, pid)
        d = dati_di(p)
        return render(request, "pvoc_primo.html", p=p, v=pvoc_primo_iniziale(p, d), verbalizzanti=d.get("verbalizzanti", []))

    @app.post("/pratiche/{pid}/pvoc-primo")
    async def pvoc_primo_crea(request: Request, pid: int, u=Depends(utente_corrente), s=Depends(db)):
        f = await request.form()
        check_csrf(request, f.get("csrf", ""))
        p = carica(s, pid)
        d = dati_di(p)
        dati = {k: str(f.get(k, "")).strip() for k in pvoc_mod.CAMPI}
        dati["ivi"] = bool(f.get("ivi"))
        d["pvoc_primo"] = dati
        salva_dati(p, d)
        testo = pvoc_mod.primo_giorno(dati, d.get("verbalizzanti", []),
                                      impresa=d.get("profilo", {}).get("forma", "impresa") == "impresa")
        a = Atto(pratica_id=p.id, tipo="PVOC", fase="avvio", giornata=dati["data"], generato_da_ai=0,
                 contenuto_cifrato=cif.cifra_testo(testo))
        s.add(a)
        s.commit()
        return RedirectResponse(f"/pratiche/{pid}/atto/{a.id}", status_code=303)

    @app.get("/pratiche/{pid}/atto/{aid}", response_class=HTMLResponse)
    def atto_vista(request: Request, pid: int, aid: int, u=Depends(utente_corrente), s=Depends(db)):
        a = s.get(Atto, aid)
        if not a or a.pratica_id != pid:
            raise HTTPException(404)
        return render(request, "atto.html", p=a.pratica, a=a, testo=cif.decifra_testo(a.contenuto_cifrato))

    @app.get("/pratiche/{pid}/atto/{aid}/word")
    def atto_word(pid: int, aid: int, spiegazioni: int = 1, u=Depends(utente_corrente), s=Depends(db)):
        a = s.get(Atto, aid)
        if not a or a.pratica_id != pid:
            raise HTTPException(404)
        testo = cif.decifra_testo(a.contenuto_cifrato)
        if a.tipo in atti_word.FORMATI:
            sog = dati_di(a.pratica).get("soggetto", {})
            dati = atti_word.crea_atto(a.tipo, testo, con_spiegazioni=bool(spiegazioni), data=a.giornata,
                                       soggetto=", ".join((sog.get("enti") or sog.get("persone") or [])[:1]))
        else:
            dati = wordexport.crea_docx(testo, con_spiegazioni=bool(spiegazioni))
        nome = f"{a.tipo}_{a.pratica.codice}_{(a.giornata or 'bozza').replace('/', '-')}"
        nome += "_con-spiegazioni" if spiegazioni else "_pulito"
        return Response(dati, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        headers={"Content-Disposition": f'attachment; filename="{nome}.docx"'})

    @app.post("/pratiche/{pid}/atto/{aid}")
    def atto_salva(request: Request, pid: int, aid: int, testo: str = Form(""), csrf: str = Form(""),
                   u=Depends(utente_corrente), s=Depends(db)):
        check_csrf(request, csrf)
        a = s.get(Atto, aid)
        if not a or a.pratica_id != pid:
            raise HTTPException(404)
        a.contenuto_cifrato = cif.cifra_testo(testo)
        s.commit()
        return RedirectResponse(f"/pratiche/{pid}/atto/{aid}", status_code=303)

    @app.get("/salute")
    def salute():
        """Controllo di stato per l'hosting: non espone dati."""
        return {"stato": "ok"}

    # ---------------------------------------------------------------- impostazioni del Reparto e invito
    def reparto_di(s) -> dict:
        r = s.get(Impostazione, "reparto")
        base = {"comandante": "", "in_sv": True, "referenti": [], "telefono": "0766/856028"}
        return {**base, **(cif.decifra_json(r.valore_cifrato) if r else {})}

    @app.post("/impostazioni/reparto")
    def salva_reparto(request: Request, comandante: str = Form(""), in_sv: str = Form(""), referenti: str = Form(""),
                      telefono: str = Form("0766/856028"), csrf: str = Form(""), u=Depends(utente_corrente),
                      s=Depends(db)):
        check_csrf(request, csrf)
        val = {"comandante": comandante.strip(), "in_sv": bool(in_sv), "referenti": righe(referenti),
               "telefono": telefono.strip() or "0766/856028"}
        r = s.get(Impostazione, "reparto") or Impostazione(chiave="reparto")
        r.valore_cifrato = cif.cifra_json(val)
        s.merge(r)
        s.commit()
        return RedirectResponse("/impostazioni", status_code=303)

    def invito_iniziale(p: Pratica, d: dict) -> dict:
        """Valori proposti nel modulo dell'invito, ricavati dalla pratica; quelli salvati dall'utente hanno la precedenza."""
        sog = d.get("soggetto", {})
        persone, enti = sog.get("persone", []), sog.get("enti", [])
        forma = d.get("profilo", {}).get("forma", "impresa")
        denom = (enti[0] if enti else (persone[0].upper() if persone else ""))
        anni = re.findall(r"\b(?:19|20)\d{2}\b", d.get("scheda", {}).get("B1", ""))
        base = {"forma_prefisso": {"impresa": "Ditta ind.le", "professionista": "Prof.", "ente": "Ente",
                                    "privato": "Sig."}.get(forma, "Ditta ind.le"),
                "denominazione": denom, "luogo": (sog.get("indirizzi") or [""])[0], "attivita": "", "codice_attivita": "",
                "cf": (sog.get("codici_fiscali") or [""])[0], "piva": (sog.get("partite_iva") or [""])[0],
                "titolo_destinatario": "Sig.", "destinatario": (persone[0].upper() if persone else ""),
                "indirizzo_destinatario": (sog.get("indirizzi") or [""])[0], "periodi": ", ".join(anni),
                "ora": "", "data": "", "documenti": "\n".join(tipologie.TIPOLOGIE[p.tipologia]["documenti"]),
                "motivazione": d.get("profilo", {}).get("ragione", "")}
        return {**base, **d.get("invito", {})}

    @app.get("/pratiche/{pid}/invito", response_class=HTMLResponse)
    def invito_form(request: Request, pid: int, u=Depends(utente_corrente), s=Depends(db)):
        p = carica(s, pid)
        d = dati_di(p)
        return render(request, "invito.html", p=p, v=invito_iniziale(p, d), rep=reparto_di(s), intro=invito_word.INTRO_RAGIONI[p.tipo],
                      salvato=bool(d.get("invito")))

    @app.post("/pratiche/{pid}/invito")
    async def invito_salva(request: Request, pid: int, u=Depends(utente_corrente), s=Depends(db)):
        f = await request.form()
        check_csrf(request, f.get("csrf", ""))
        p = carica(s, pid)
        d = dati_di(p)
        campi = ("forma_prefisso", "denominazione", "luogo", "attivita", "codice_attivita", "cf", "piva",
                 "titolo_destinatario", "destinatario", "indirizzo_destinatario", "periodi", "ora", "data",
                 "documenti", "motivazione", "nascita", "qualita")
        d["invito"] = {k: str(f.get(k, "")).strip() for k in campi}
        d["invito"]["ivi"] = bool(f.get("ivi"))
        salva_dati(p, d)
        s.commit()
        return RedirectResponse(f"/pratiche/{pid}/invito", status_code=303)

    @app.get("/pratiche/{pid}/invito/word")
    def invito_word_dl(pid: int, u=Depends(utente_corrente), s=Depends(db)):
        p = carica(s, pid)
        d = dati_di(p)
        dati = invito_iniziale(p, d)
        if p.tipo != "controllo":                            # il controllo riporta i periodi come scritti (es. «… fino al 16/02»)
            dati["periodi"] = [x.strip() for x in re.split(r"[;,\n]", dati.get("periodi", "")) if x.strip()]
        contenuto = invito_word.crea_invito(dati, p.tipo, reparto_di(s))
        return Response(contenuto, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        headers={"Content-Disposition": f'attachment; filename="INVITO_{p.codice}_{p.tipo}.docx"'})

    # ---------------------------------------------------------------- impostazioni e prova AI
    def _stato_ai() -> dict:
        c = ai_mod.configurazione()
        return {k: c[k] for k in ("provider", "attiva", "modello", "chiave_mascherata", "ricerca_web",
                                  "gratuito_con_dati_usati")}

    @app.get("/impostazioni", response_class=HTMLResponse)
    def impostazioni(request: Request, u=Depends(utente_corrente), s=Depends(db)):
        log = s.scalars(select(LogAI).order_by(LogAI.id.desc()).limit(20)).all()
        return render(request, "impostazioni.html", ai=_stato_ai(), esito=None, log=log, rep=reparto_di(s))

    @app.post("/impostazioni/prova", response_class=HTMLResponse)
    def prova_ai(request: Request, csrf: str = Form(""), u=Depends(utente_corrente), s=Depends(db)):
        """Chiamata minima (poche centinaia di token, nessun dato della pratica) per verificare chiave e collegamento."""
        check_csrf(request, csrf)
        import anthropic
        esito = {"ok": False, "testo": ""}
        try:
            r = client_ai().beta.messages.create(
                model=ai_mod.configurazione()["modello"], max_tokens=1000, output_config={"effort": "low"},
                messages=[{"role": "user", "content": "Rispondi soltanto con la parola OK."}])
            risposta = "".join(b.text for b in r.content if getattr(b, "type", "") == "text").strip()
            u_ = getattr(r, "usage", None)
            esito = {"ok": True, "testo": f"Risposta: «{risposta[:40]}». Modello: {getattr(r, 'model', st.anthropic_model)}. "
                     f"Token usati: {getattr(u_, 'input_tokens', '?')} in ingresso, {getattr(u_, 'output_tokens', '?')} in uscita."}
        except ai_mod.AIDisattivata as e:
            esito["testo"] = str(e)
        except llm_compat.ServizioAIErrore as e:
            esito["testo"] = e.messaggio
        except anthropic.AuthenticationError:
            esito["testo"] = "Chiave non valida: controlla di averla copiata per intero, senza spazi."
        except anthropic.PermissionDeniedError:
            esito["testo"] = "Accesso negato per questa chiave o questo modello."
        except anthropic.RateLimitError:
            esito["testo"] = "Limite di richieste raggiunto: riprova tra poco."
        except anthropic.APIConnectionError:
            esito["testo"] = "Impossibile raggiungere il servizio: riprova."
        except anthropic.APIStatusError as e:
            esito["testo"] = f"Errore del servizio (codice {e.status_code}). Se parla di credito, verifica il saldo dell'account."
        log = s.scalars(select(LogAI).order_by(LogAI.id.desc()).limit(20)).all()
        return render(request, "impostazioni.html", ai=_stato_ai(), esito=esito, log=log, rep=reparto_di(s))

    # ---------------------------------------------------------------- PWA
    @app.get("/manifest.webmanifest")
    def manifest():
        return FileResponse(BASE / "static" / "manifest.webmanifest", media_type="application/manifest+json")

    @app.get("/sw.js")
    def sw():
        return FileResponse(BASE / "static" / "sw.js", media_type="application/javascript")

    return app
