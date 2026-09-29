from __future__ import annotations

import datetime as dt
import hmac
import pathlib
import secrets

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from starlette.middleware.sessions import SessionMiddleware

from . import ai as ai_mod
from . import schede, security, tipologie, workflow
from .config import Settings
from .db import crea_engine, crea_sessionmaker
from .models import Atto, FasePratica, LogAI, Pratica, Utente

BASE = pathlib.Path(__file__).parent
ISTRUZIONI = {
    "PVOC": "Redigi la bozza del processo verbale di operazioni compiute per la giornata indicata, "
            "per la fase indicata, seguendo la struttura e il lessico del Reparto.",
    "PVV": "Redigi la bozza del processo verbale di verifica per la giornata indicata, "
           "per la fase indicata, seguendo la struttura e il lessico del Reparto.",
    "PVC": "Redigi la bozza del processo verbale di constatazione (Vol. IV, Allegato 19) con le sezioni "
           "previste, usando solo i fatti presenti negli atti e negli appunti.",
    "CNR": "Redigi la bozza della comunicazione di notizia di reato ex art. 347 c.p.p. (dati sintetici, premessa, "
           "attivita' operativa, sezioni tematiche, allegati), usando solo i fatti presenti negli atti e negli appunti.",
    "INVITO": "Redigi la bozza dell'invito a presentarsi (Vol. IV, Allegato 14) con le sezioni previste.",
}


def create_app(settings: Settings | None = None, sessionmaker=None, ai_client=None) -> FastAPI:
    st = settings or Settings.load()
    SM = sessionmaker or crea_sessionmaker(crea_engine(st.database_url))
    cif = security.Cifratore(st.data_key)
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

    # ---------------------------------------------------------------- accesso
    @app.get("/login", response_class=HTMLResponse)
    def login_form(request: Request, s=Depends(db)):
        configurato = s.scalar(select(Utente.id)) is not None
        return render(request, "login.html", errore=None, configurato=configurato)

    @app.post("/login")
    def login(request: Request, password: str = Form(""), codice: str = Form(""), csrf: str = Form(""),
              s=Depends(db)):
        check_csrf(request, csrf)
        u = s.scalar(select(Utente))
        adesso = dt.datetime.now(dt.timezone.utc)
        generico = "Credenziali non valide o accesso temporaneamente bloccato."
        if not u:
            return render(request, "login.html", errore=generico, configurato=False)
        blocco = u.bloccato_fino
        if blocco is not None and blocco.tzinfo is None:
            blocco = blocco.replace(tzinfo=dt.timezone.utc)
        if blocco and blocco > adesso:
            return render(request, "login.html", errore=generico, configurato=True)
        ok = security.verify_password(u.password_hash, password) and \
            security.verifica_totp(cif.decifra_testo(u.totp_cifrato), codice)
        if not ok:
            u.tentativi_falliti += 1
            if u.tentativi_falliti >= st.max_login_failures:
                u.bloccato_fino = adesso + dt.timedelta(minutes=st.lock_minutes)
                u.tentativi_falliti = 0
            s.commit()
            return render(request, "login.html", errore=generico, configurato=True)
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
              csrf: str = Form(""), u=Depends(utente_corrente), s=Depends(db)):
        check_csrf(request, csrf)
        if tipo not in workflow.PERCORSI or tipologia not in tipologie.TIPOLOGIE:
            raise HTTPException(400, "Tipo non valido")
        anno = dt.date.today().year
        n = len(s.scalars(select(Pratica.id).where(Pratica.codice.like(f"%-{anno}-%"))).all()) + 1
        p = Pratica(codice=f"{'C' if tipo == 'controllo' else 'V'}-{anno}-{n:03d}", tipo=tipo, tipologia=tipologia)
        salva_dati(p, {"privato": bool(privato),
                       "soggetto": {"persone": righe(persone), "enti": righe(enti),
                                    "codici_fiscali": righe(codici_fiscali), "partite_iva": righe(partite_iva),
                                    "indirizzi": righe(indirizzi)},
                       "verbalizzanti": righe(verbalizzanti), "terzi": [], "scheda": {}})
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
        fasi = [{"f": f, "stato": stati.get(f.chiave, "da_fare")} for f in workflow.fasi_per(p.tipo)]
        return render(request, "pratica.html", p=p, fasi=fasi, prossima=prox, atti=p.atti,
                      tip=tipologie.TIPOLOGIE[p.tipologia])

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
        return render(request, "scheda.html", p=p, campi=campi, valori=d.get("scheda", {}),
                      mancanti=schede.completezza(d.get("scheda", {}), d.get("privato", False)))

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
                                                        checklist=list(f.checklist))
                ctx["anteprima"] = {"testo": user, "segnaposto": sorted(pseudo.tabella.keys())}
            elif azione == "genera":
                if not conferma:
                    ctx["errore"] = "Conferma di aver controllato l'anteprima prima di generare."
                else:
                    b = ai_mod.genera_bozza(pseudo, istruzione=ISTRUZIONI[f.atto], contesto=contesto,
                                            checklist=list(f.checklist), modello=st.anthropic_model,
                                            client=ai_client)
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

    @app.get("/pratiche/{pid}/atto/{aid}", response_class=HTMLResponse)
    def atto_vista(request: Request, pid: int, aid: int, u=Depends(utente_corrente), s=Depends(db)):
        a = s.get(Atto, aid)
        if not a or a.pratica_id != pid:
            raise HTTPException(404)
        return render(request, "atto.html", p=a.pratica, a=a, testo=cif.decifra_testo(a.contenuto_cifrato))

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

    # ---------------------------------------------------------------- PWA
    @app.get("/manifest.webmanifest")
    def manifest():
        return FileResponse(BASE / "static" / "manifest.webmanifest", media_type="application/manifest+json")

    @app.get("/sw.js")
    def sw():
        return FileResponse(BASE / "static" / "sw.js", media_type="application/javascript")

    return app
