from __future__ import annotations

from decimal import Decimal

import datetime as dt
import hmac
import pathlib
import re
import os
import secrets
import threading

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from starlette.middleware.sessions import SessionMiddleware

from . import ai as ai_mod
from . import prassi as prassi_mod
from . import analisi, atti_word, calcoli, chat as chat_mod, metodo as metodo_mod, pvoc as pvoc_mod, pvc as pvc_mod, invito_word, llm_compat, norme, scheda_ai, piano as piano_mod, schede, security, tipologie, workflow, wordexport
from .config import Settings
from .db import crea_engine, crea_sessionmaker
from .models import PrassiDocumento, Atto, ConoscenzaReparto, DocumentoPratica, FasePratica, FatturaPratica, FonteNormativa, Impostazione, LogAI, MessaggioChat, Pratica, Utente

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
    "PVC": "Redigi SOLO le quattro sezioni variabili del processo verbale di constatazione; intestazione, FATTO e sezione "
           "conclusiva le aggiunge il programma con le formule del Reparto, NON scriverle. Rispondi esattamente con quattro "
           "blocchi, ciascuno preceduto da una riga di marca: \"=== CONTABILE ===\" (esito del controllo contabile: registri "
           "e libri esaminati), \"=== SOSTANZIALE ===\" (controllo sostanziale: riscontri di coerenza, riscontro analitico "
           "normativo con i fatti accertati e i conti), \"=== FORMALI ===\" (riga \">> PERIODI D'IMPOSTA ...\" e le violazioni "
           "formali, oppure \"Nei periodi d'imposta in esame non si rilevano violazioni di carattere formale.\"), "
           "\"=== SOSTANZIALI ===\" (per ogni periodo: riga \">> PERIODO D'IMPOSTA aaaa\", poi per tributo \"A. Violazioni "
           "in materia di ...\", una tabella con righe \"| | Descrizione della violazione constatata | Fonte normativa della "
           "violazione\" e \"| a. | titolo della violazione e descrizione, con gli importi | Norma violata: ...\", poi \"L'autore "
           "della violazione sub A., lettera a., e' da individuarsi ...\"; per i periodi senza violazioni: \"Per il periodo "
           "d'imposta in esame non si rilevano violazioni di carattere sostanziale.\"). Usa solo i fatti presenti negli atti e "
           "negli appunti.",
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
        manuale = {k: v for k, v in d.get("pvoc_primo", {}).items() if v not in ("", None)}
        return {**base, **d.get("fascicolo", {}).get("pvoc_primo", {}), **manuale}

    def pvc_iniziale(p: Pratica, d: dict) -> dict:
        base = {k: v for k, v in pvoc_primo_iniziale(p, d).items() if k in pvc_mod.CAMPI}
        base.update({k: "" for k in pvc_mod.CAMPI if k not in base})
        base["sede"] = base.get("sede") or base.get("luogo", "")
        base["dal"] = base.get("dal") or d.get("pvoc_primo", {}).get("dal", "")
        base["al"] = base.get("al") or d.get("pvoc_primo", {}).get("al", "")
        base["data_inizio"] = base.get("data_inizio") or d.get("pvoc_primo", {}).get("data", "")
        base["direttore"] = base.get("direttore") or d.get("pvoc_primo", {}).get("direttore", "")
        base["documenti_richiesti"] = base.get("documenti_richiesti") or d.get("pvoc_primo", {}).get("documenti", "").replace("\n", "; ")
        return {**base, **{k: v for k, v in d.get("pvc", {}).items() if v not in ("", None)}}

    @app.get("/pratiche/{pid}/pvc-dati", response_class=HTMLResponse)
    def pvc_dati_form(request: Request, pid: int, u=Depends(utente_corrente), s=Depends(db)):
        p = carica(s, pid)
        d = dati_di(p)
        return render(request, "pvc_dati.html", p=p, v=pvc_iniziale(p, d), verbalizzanti=d.get("verbalizzanti", []))

    @app.post("/pratiche/{pid}/pvc-dati")
    async def pvc_dati_salva(request: Request, pid: int, u=Depends(utente_corrente), s=Depends(db)):
        f = await request.form()
        check_csrf(request, f.get("csrf", ""))
        p = carica(s, pid)
        d = dati_di(p)
        dati = {k: str(f.get(k, "")).strip() for k in pvc_mod.CAMPI}
        for k in pvc_mod.FLAG:
            dati[k] = bool(f.get(k))
        if dati["attivita"] not in pvc_mod.ATTIVITA:
            dati["attivita"] = "controllo"
        d["pvc"] = dati
        salva_dati(p, d)
        s.commit()
        return RedirectResponse(f"/pratiche/{pid}/chat", status_code=303)

    @app.get("/pratiche/{pid}/pvoc-primo", response_class=HTMLResponse)
    def pvoc_primo_form(request: Request, pid: int, u=Depends(utente_corrente), s=Depends(db)):
        p = carica(s, pid)
        d = dati_di(p)
        return render(request, "pvoc_primo.html", p=p, v=pvoc_primo_iniziale(p, d), verbalizzanti=d.get("verbalizzanti", []))

    def crea_pvoc_primo(s, p: Pratica, d: dict, dati: dict) -> Atto:
        testo = pvoc_mod.primo_giorno(dati, d.get("verbalizzanti", []),
                                      impresa=d.get("profilo", {}).get("forma", "impresa") == "impresa")
        a = Atto(pratica_id=p.id, tipo="PVOC", fase="avvio", giornata=dati.get("data", ""), generato_da_ai=0,
                 contenuto_cifrato=cif.cifra_testo(testo))
        s.add(a)
        return a

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
        a = crea_pvoc_primo(s, p, d, dati)
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

    # ---------------------------------------------------------------- assistente conversazionale
    def fasi_chat(p: Pratica) -> list[dict]:
        stati = stati_di(p)
        return [{"chiave": f.chiave, "titolo": f.titolo, "stato": stati.get(f.chiave, "da_fare"), "atto": f.atto,
                 "condizionale": f.condizionale} for f in workflow.fasi_per(p.tipo)]

    def documenti_di(s, p: Pratica) -> list[dict]:
        docs = s.scalars(select(DocumentoPratica).where(DocumentoPratica.pratica_id == p.id).order_by(DocumentoPratica.id)).all()
        return [{"id": x.id, "nome": cif.decifra_testo(x.nome_cifrato), "tipo": x.tipo, "caratteri": x.caratteri,
                 "testo": cif.decifra_testo(x.testo_cifrato)} for x in docs]

    def messaggi_di(s, p: Pratica) -> list[MessaggioChat]:
        return list(s.scalars(select(MessaggioChat).where(MessaggioChat.pratica_id == p.id).order_by(MessaggioChat.id)).all())

    def registro_sicuro(d: dict) -> calcoli.Registro:
        try:
            return calcoli.registro_da_dati(d.get("calcoli", {"dati": [], "calcoli": []}))
        except calcoli.CalcoloErrore:
            return calcoli.Registro()

    def fatture_di(s, p: Pratica) -> list[dict]:
        righe = s.scalars(select(FatturaPratica).where(FatturaPratica.pratica_id == p.id).order_by(FatturaPratica.id)).all()
        return [cif.decifra_json(x.dati_cifrati) for x in righe]

    def aggiorna_analisi(s, p: Pratica, d: dict) -> None:
        """Ricalcola prospetto, dati tracciati automatici e riscontri oggettivi dalle fatture caricate (le decisioni restano)."""
        sog = d.get("soggetto", {}) or {}
        ids = {analisi._norm_id(x) for x in (sog.get("partite_iva", []) or []) + (sog.get("codici_fiscali", []) or [])} - {""}
        res = analisi.analizza(fatture_di(s, p), ids, p.tipologia)
        if d.get("movimenti_crediti"):
            from . import crediti
            vend = {}
            for x in res["dati"]:
                if x["id"].startswith("F_V") and x["id"].endswith("_TOT"):
                    vend[int(x["id"][3:7])] = Decimal(x["valore"])
            cr = crediti.analizza(d["movimenti_crediti"], ids, vend)
            res = {"dati": res["dati"] + cr["dati"], "riscontri": res["riscontri"] + cr["riscontri"],
                   "prospetto": (res["prospetto"] + "\n\n" if res["prospetto"] else "") + cr["prospetto"]}
        cfg = d.setdefault("calcoli", {"dati": [], "calcoli": []})
        cfg["dati"] = [x for x in cfg["dati"] if not x.get("auto")] + res["dati"]
        d["riscontri"] = analisi.unisci_riscontri(d.get("riscontri", []), res["riscontri"])
        d["prospetto_fatture"] = res["prospetto"]

    def ctx_chat(s, p: Pratica, **extra) -> dict:
        d = dati_di(p)
        fasc = d.get("fascicolo", {}) or {}
        fasi_val = {f["chiave"]: f["atto"] for f in fasi_chat(p)}
        prop = [{**x, "titolo": next((f["titolo"] for f in fasi_chat(p) if f["chiave"] == x["fase"]), x["fase"])}
                for x in fasc.get("proposte", []) if x.get("fase") in fasi_val]
        base = dict(p=p, msgs=[(m.ruolo, cif.decifra_testo(m.contenuto_cifrato)) for m in messaggi_di(s, p)],
                    documenti=documenti_di(s, p), fascicolo=fasc, proposte=prop, ai=_stato_ai(),
                    riscontri=d.get("riscontri", []), prospetto=d.get("prospetto_fatture", ""),
                    base_normativa=list(reversed(d.get("base_normativa", []))),
                    titoli_fasi={f["chiave"]: f["titolo"] for f in fasi_chat(p)},
                    bozza="", errore=None, sospetti=None, nota=None)
        job = d.get("job_chat") or {}
        if job.get("stato") == "in_corso":
            try:
                vecchio = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(job["inizio"])) > dt.timedelta(minutes=15)
            except (KeyError, ValueError):
                vecchio = True
            if vecchio:                                        # il processo e' morto (riavvio del server): si sblocca la chat
                d["job_chat"] = {"stato": "letto"}
                salva_dati(p, d)
                s.commit()
                base["errore"] = "L'elaborazione precedente non si e' conclusa (il server si e' riavviato?). Riinvia il messaggio."
            else:
                base["in_corso"] = job.get("messaggio", "")
        elif job.get("stato") == "finito":
            for k, v in (job.get("esito") or {}).items():
                if v and k not in extra:
                    base[k] = v
            d["job_chat"] = {"stato": "letto"}
            salva_dati(p, d)
            s.commit()
        base.update(extra)
        return base

    def pseudo_per(d: dict):
        pseudo = ai_mod.costruisci_pseudonimizzatore(d)
        for n in d.get("chat_persone", []):
            pseudo.aggiungi_persona(n)
        for n in d.get("chat_enti", []):
            pseudo.aggiungi_ente(n)
        return pseudo

    def registra_nomi(d: dict, nomi: list[tuple[str, str]]) -> None:
        """Aggiunge all'anagrafica (quindi alla pseudonimizzazione) persone/enti citati nei documenti o indicati dall'operatore."""
        for n, tipo in nomi:
            chiave = "chat_enti" if tipo == "ente" else "chat_persone"
            if n and n not in d.setdefault(chiave, []):
                d[chiave].append(n)

    def esegui_ricerche(s, p: Pratica, d: dict, pseudo, client, ricerche: list[dict], budget_s: float = 45.0) -> int:
        """Consulta le fonti aperte per i quesiti generali (in parallelo, entro un tempo massimo) e ne registra esito e fonti.
        Ritorna quante ricerche sono andate a buon fine."""
        import concurrent.futures as cf
        base = d.setdefault("base_normativa", [])
        lavori = []                                               # (voce, quesito, periodo)
        for r in ricerche:
            q = chat_mod.quesito_pulito(r["quesito"])
            voce = {"id": f"Q{len(base) + len(lavori) + 1}", "quesito": q or "(quesito scartato: sembrava contenere nomi propri)",
                    "periodo": r["periodo"], "data": dt.datetime.now(dt.timezone.utc).strftime("%d/%m/%Y"), "sintesi": "", "fonti": []}
            if not q:
                voce["esito"] = "scartato"
                base.append(voce)
                voce["id"] = f"Q{len(base)}"
            elif any(x["quesito"] == q and x["periodo"] == r["periodo"] and x.get("esito") == "ok" for x in base) or any(v[1] == q for v in lavori):
                continue                                                          # gia' consultata
            else:
                lavori.append((voce, q, r["periodo"]))
        if not lavori:
            return 0

        def una(q, periodo):
            try:
                return norme.ricerca_normativa(pseudo, q, periodo, client=client, modello=st.anthropic_model), None
            except Exception as e:                                # noqa: BLE001 - l'esito viene classificato sotto
                return None, e
        ex = cf.ThreadPoolExecutor(max_workers=min(4, len(lavori)))
        futuri = [ex.submit(una, q, per) for _, q, per in lavori]
        cf.wait(futuri, timeout=budget_s)
        ex.shutdown(wait=False, cancel_futures=True)
        ok = 0
        for (voce, q, per), fu in zip(lavori, futuri):
            if not fu.done():
                voce["esito"], voce["sintesi"] = "non_riuscita", "Tempo scaduto: la ricerca verra' ripetuta al prossimo messaggio."
            else:
                ric, e = fu.result()
                if e is None:
                    voce["esito"] = "ok"
                    ok += 1
                    voce["sintesi"] = ric.risposta[:6000]
                    voce["fonti"] = [{"url": f.url, "titolo": f.titolo[:200], "dominio": f.dominio, "ufficiale": f.ufficiale,
                                      "estratto": f.estratto[:600]} for f in ric.fonti][:20]
                    for f in ric.fonti[:20]:
                        s.add(FonteNormativa(pratica_id=p.id, quesito=q, periodo=per, url=f.url[:600], titolo=f.titolo[:300],
                                             estratto=f.estratto, dominio=f.dominio[:120], ufficiale=int(f.ufficiale)))
                elif isinstance(e, ai_mod.LeakError):
                    voce["esito"], voce["quesito"] = "scartato", "(quesito scartato: conteneva dati riconoscibili)"
                elif isinstance(e, llm_compat.NonSupportato):
                    voce["esito"], voce["sintesi"] = "non_riuscita", str(e)
                elif isinstance(e, llm_compat.ServizioAIErrore):
                    voce["esito"], voce["sintesi"] = "non_riuscita", e.messaggio
                else:
                    voce["esito"], voce["sintesi"] = "non_riuscita", f"Errore della ricerca ({type(e).__name__})."
            base.append(voce)
        return ok

    def riscontri_da_istruire(d: dict) -> list[dict]:
        return [r for r in d.get("riscontri", []) if r.get("stato") == "proposto" and not r.get("ricerca_prassi") and not r.get("fonti")][:6]

    def istruttoria(s, p: Pratica, d: dict, pseudo, client, descrizione_caso: str, riscontri: list[dict] | None = None, massimo: int = 8) -> int:
        """ISTRUTTORIA NORMATIVA AUTOMATICA: un pianificatore AI decide quali ricerche su fonti aperte servono al caso (e ai rilievi gia'
        emersi), il programma le esegue e le fonti ufficiali trovate entrano nella biblioteca della prassi. Ritorna le ricerche riuscite."""
        fatte = [v["quesito"] for v in d.get("base_normativa", []) if v.get("esito") == "ok"]
        parti = ["CASO:\n" + descrizione_caso[:5000]]
        if riscontri:
            parti.append("RILIEVI GIA' EMERSI DA VERIFICARE CON LA PRASSI:\n" + "\n".join(
                f"- {r['descrizione'][:400]} [norma indicata: {r.get('norma', '')[:150]}]" for r in riscontri))
        parti.append("RICERCHE GIA' ESEGUITE (non ripeterle):\n" + ("\n".join(f"- {q}" for q in fatte[-25:]) or "- nessuna"))
        try:
            testo, _, _ = ai_mod.chiama_chat(client, st.anthropic_model, chat_mod.SYSTEM_PIANO.replace("{massimo}", str(massimo)),
                                             [{"role": "user", "content": pseudo.anonimizza_o_blocca("\n\n".join(parti))}], max_tokens=3000)
        except (ai_mod.AIRifiutata, llm_compat.ServizioAIErrore):
            return 0
        piano = chat_mod.piano_da_testo(testo, massimo)
        ok = esegui_ricerche(s, p, d, pseudo, client, piano) if piano else 0
        try:
            prassi_mod.scopri_da_fonti(s, d.get("base_normativa", []))
        except Exception:                                          # noqa: BLE001
            pass
        for r in riscontri or []:
            r["ricerca_prassi"] = True
        return ok

    def descrizione_caso(d: dict, p: Pratica, testo_utente: str) -> str:
        fasc = d.get("fascicolo", {}) or {}
        prof = d.get("profilo", {}) or {}
        return "\n".join(x for x in [f"Tipo di intervento: {p.tipo}. Tipologia: {tipologie.TIPOLOGIE[p.tipologia]['nome']}.",
                                     f"Forma del soggetto: {prof.get('forma', '')}; regime: {prof.get('regime', '')}.",
                                     f"Motivazione: {fasc.get('motivazione', '')}", f"Obiettivo: {fasc.get('obiettivo', '')}",
                                     f"Messaggio dell'operatore: {testo_utente}"] if x.split(': ', 1)[-1].strip())

    def metodo_per(s, d: dict, p: Pratica, atto: str = "", extra: str = "") -> tuple[str, list[str]]:
        """(metodo del Reparto pertinente al caso, brani di stile) dalla libreria."""
        fasc = d.get("fascicolo", {}) or {}
        q = " ".join([tipologie.TIPOLOGIE[p.tipologia]["nome"], p.tipologia.replace("_", " "), fasc.get("motivazione", ""),
                      fasc.get("obiettivo", ""), " ".join(v.get("quesito", "") for v in d.get("base_normativa", [])), extra])
        voci = libreria_di(s)
        return metodo_mod.metodo_testo(metodo_mod.seleziona(voci, q, atto)), metodo_mod.esempi_di_stile(voci, q, atto) if atto else []

    def prassi_per(s, d: dict, p: Pratica, docs: list[dict], extra: str = "") -> str:
        """Paragrafi di prassi pertinenti al caso, dalla biblioteca; scarica in background i documenti dei temi riconosciuti."""
        fasc = d.get("fascicolo", {}) or {}
        caso = " ".join([tipologie.TIPOLOGIE[p.tipologia]["nome"], p.tipologia.replace("_", " "), fasc.get("motivazione", ""), fasc.get("obiettivo", "")]
                        + [x["testo"][:2500] for x in docs[:8]] + [r["descrizione"] + " " + r.get("ragionamento", "") for r in d.get("riscontri", [])] + [extra])
        temi = prassi_mod.temi_del_caso(caso)
        try:
            prassi_mod.scopri_da_fonti(s, d.get("base_normativa", []))
            if temi:
                prassi_mod.assicura_indice(s)
                attesa = [x for x in s.scalars(select(PrassiDocumento)).all()
                          if x.stato != "pronto" and any(t.lower() in x.temi.lower() for t in temi)]
                if attesa and os.environ.get("PRASSI_DOWNLOAD", "0") == "1":   # di default niente scaricamenti: la prassi si cerca sul web
                    prassi_mod.sincronizza_in_background(SM, temi)
            passaggi = prassi_mod.cerca(s, caso[:6000], temi or None)
            st_b = prassi_mod.stato_biblioteca(s)
        except Exception:                                      # noqa: BLE001 - la biblioteca non deve mai bloccare la chat
            return ""
        stato = (f"BIBLIOTECA: {st_b['pronti']} documenti scaricati su {st_b['totale']}; temi riconosciuti nel caso: "
                 f"{', '.join(temi) or 'nessuno'}" + (" (scaricamento in corso per altri documenti: riprova tra poco)" if temi and st_b["pronti"] < st_b["totale"] else ""))
        return prassi_mod.passaggi_testo(passaggi, stato)

    def catalogo_per(d: dict, p: Pratica, docs: list[dict]) -> str:
        """Catalogo dei ragionamenti sulle violazioni, con le aree piu' pertinenti al caso in evidenza."""
        fasc = d.get("fascicolo", {}) or {}
        caso = " ".join([tipologie.TIPOLOGIE[p.tipologia]["nome"], p.tipologia.replace("_", " "), d.get("profilo", {}).get("regime", ""),
                         d.get("profilo", {}).get("forma", ""), fasc.get("motivazione", ""), fasc.get("obiettivo", "")]
                        + [x["testo"][:1500] for x in docs[:6]] + [r["descrizione"] for r in d.get("riscontri", [])])
        return metodo_mod.catalogo_testo(caso)

    def turno(request: Request, s, p: Pratica, testo_utente: str, forza: bool = False):
        """Un giro di conversazione. Ritorna (risposta_html_ctx). Nulla viene salvato se qualcosa fallisce o viene bloccato."""
        d = dati_di(p)
        pseudo = pseudo_per(d)
        storia = [(m.ruolo, cif.decifra_testo(m.contenuto_cifrato)) for m in messaggi_di(s, p)][-30:]
        if storia and storia[0][0] != "user":
            storia = storia[1:]
        storia.append(("user", testo_utente))
        fasi = fasi_chat(p)
        fasi_valide = {f["chiave"]: f["atto"] for f in fasi}
        docs_ctx = documenti_di(s, p)

        def costruisci_system() -> str:
            ctx_txt = chat_mod.contesto(p.tipo, tipologie.TIPOLOGIE[p.tipologia]["nome"], fasi, d, docs_ctx,
                                        [{"tipo": a.tipo, "giornata": a.giornata, "fase": a.fase} for a in p.atti],
                                        pvoc_primo_iniziale(p, d), prospetto=d.get("prospetto_fatture", ""),
                                        voci=registro_sicuro(d).elenco_per_prompt(), base_normativa=d.get("base_normativa", []),
                                        metodo=metodo_per(s, d, p)[0], catalogo=catalogo_per(d, p, docs_ctx),
                                        prassi=prassi_per(s, d, p, docs_ctx, testo_utente))
            return pseudo.anonimizza_o_blocca(chat_mod.system() + "\n\nMODO DI OPERARE DEL REPARTO:\n"
                                              + ai_mod.playbook() + "\n\nSTATO DELLA PRATICA:\n" + ctx_txt)
        visibili: list[str] = []
        log_testi: list[str] = []
        try:
            system = costruisci_system()
            msgs = [{"role": r, "content": pseudo.anonimizza_o_blocca(t)} for r, t in storia]
            libero = "\n".join(m["content"] for m, (r, _) in zip(msgs, storia) if r == "user") + "\n" + "\n".join(
                pseudo.anonimizza(x["testo"]) for x in documenti_di(s, p))          # solo testo scritto/caricato dall'operatore
            ignora = set(d.get("chat_ignora", []))
            sospetti = [n for n in chat_mod.nomi_sospetti(libero) if n not in ignora]
            if sospetti and not forza:
                return ctx_chat(s, p, bozza=testo_utente, sospetti=sospetti)
            client = ai_client or ai_mod._client()
            eseguite_auto = 0
            if st.istruttoria_auto:                                # ISTRUTTORIA NORMATIVA AUTOMATICA prima di rispondere
                ist = d.setdefault("istruttoria", {})
                if testo_utente.lower().startswith("istruttoria normativa"):
                    ist.clear()
                    for r_ in d.get("riscontri", []):
                        r_.pop("ricerca_prassi", None)
                fasc_ = d.get("fascicolo", {}) or {}
                if not ist.get("caso") and (fasc_.get("motivazione") or docs_ctx or len(testo_utente) > 80):
                    eseguite_auto += istruttoria(s, p, d, pseudo, client, descrizione_caso(d, p, testo_utente))
                    ist["caso"] = True
                da_ = riscontri_da_istruire(d)
                if da_:
                    eseguite_auto += istruttoria(s, p, d, pseudo, client, descrizione_caso(d, p, testo_utente), da_)
                if eseguite_auto:
                    system = costruisci_system()
            testo, stop, modello = ai_mod.chiama_chat(client, st.anthropic_model, system, msgs)
            log_testi.append(system + "\n\n" + "\n".join(f"[{m['role']}] {m['content']}" for m in msgs))
            giro = 0
            while True:
                visibile_anon, azioni = chat_mod.separa_azioni(testo)
                validate = chat_mod.valida_azioni(azioni, pseudo.ripristina, fasi_valide, set(registro_sicuro(d).voci),
                                                  {v["id"] for v in d.get("base_normativa", [])})
                visibili.append(pseudo.ripristina(visibile_anon)[0])
                chat_mod.applica_azioni(d, validate)
                ricerche = validate.get("ricerche", []) if giro < 3 else []
                auto = False
                if not ricerche and st.istruttoria_auto and giro < 3:
                    da_ = riscontri_da_istruire(d)                                    # nuovi rilievi: verifica automatica sulla prassi
                    if da_:
                        n_ = istruttoria(s, p, d, pseudo, client, descrizione_caso(d, p, testo_utente), da_)
                        eseguite_auto += n_
                        auto = n_ > 0
                if not ricerche and not auto:
                    break
                if ricerche:
                    eseguite_auto += esegui_ricerche(s, p, d, pseudo, client, ricerche)   # consultazione automatica delle fonti aperte
                giro += 1
                system = costruisci_system()
                msgs = msgs + [{"role": "assistant", "content": testo},
                               {"role": "user", "content": "[Programma] Ricerche completate: i risultati sono nella sezione BASE NORMATIVA "
                                                           "RACCOLTA del contesto. Prosegui la risposta all'operatore usando solo quelle fonti."}]
                testo, stop, modello = ai_mod.chiama_chat(client, st.anthropic_model, system, msgs)
                log_testi.append(f"[seconda chiamata dopo ricerca]\n{system}\n\n" + "\n".join(f"[{m['role']}] {m['content']}" for m in msgs))
        except ai_mod.LeakError as e:
            s.add(LogAI(pratica_id=p.id, sezione="chat", testo_inviato="(bloccato)", esito="bloccato"))
            s.commit()
            return ctx_chat(s, p, bozza=testo_utente, errore=f"Invio BLOCCATO: {e}. Aggiungi il dato all'anagrafica della pratica.")
        except (ai_mod.AIDisattivata, ai_mod.AIRifiutata) as e:
            return ctx_chat(s, p, bozza=testo_utente, errore=str(e))
        except llm_compat.ServizioAIErrore as e:
            return ctx_chat(s, p, bozza=testo_utente, errore=str(e))
        except Exception as e:                                   # errori di rete/servizio: non perdere il messaggio
            return ctx_chat(s, p, bozza=testo_utente, errore=f"Errore del servizio AI ({type(e).__name__}). Riprova.")
        visibile = "\n\n".join(v for v in visibili if v.strip())
        salva_dati(p, d)
        s.add(LogAI(pratica_id=p.id, sezione="chat", modello=modello, testo_inviato="\n\n=====\n\n".join(log_testi)))
        s.add(MessaggioChat(pratica_id=p.id, ruolo="user", contenuto_cifrato=cif.cifra_testo(testo_utente)))
        s.add(MessaggioChat(pratica_id=p.id, ruolo="assistant", contenuto_cifrato=cif.cifra_testo(visibile)))
        s.commit()
        nota = "Risposta interrotta per lunghezza: chiedi di proseguire." if stop == "max_tokens" else None
        if eseguite_auto:
            nota = (nota + " " if nota else "") + f"Istruttoria normativa automatica: {eseguite_auto} ricerche su fonti aperte eseguite (vedi «Fonti consultate»)."
        return ctx_chat(s, p, nota=nota)

    @app.get("/pratiche/{pid}/chat", response_class=HTMLResponse)
    def chat_vista(request: Request, pid: int, u=Depends(utente_corrente), s=Depends(db)):
        p = carica(s, pid)
        return render(request, "chat.html", **ctx_chat(s, p))

    def avvia_turno(request: Request, s, p: Pratica, testo: str, forza: bool = False):
        """Con la modalita' asincrona il turno gira in un thread (l'elaborazione puo' durare minuti: ricerche, documenti lunghi) e la
        pagina si aggiorna da sola; altrimenti risponde subito (test, uso locale)."""
        if not st.chat_asincrona:
            return render(request, "chat.html", **turno(request, s, p, testo, forza=forza))
        d = dati_di(p)
        job = d.get("job_chat") or {}
        if job.get("stato") == "in_corso":
            return render(request, "chat.html", **ctx_chat(s, p, bozza=testo))
        d["job_chat"] = {"stato": "in_corso", "inizio": dt.datetime.now(dt.timezone.utc).isoformat(), "messaggio": testo[:300]}
        salva_dati(p, d)
        s.commit()
        pid = p.id

        def lavoro():
            try:
                with SM() as s2:
                    p2 = s2.get(Pratica, pid)
                    try:
                        ctx = turno(None, s2, p2, testo, forza=forza)
                    except Exception as e:                      # noqa: BLE001
                        ctx = {"errore": f"Errore durante l'elaborazione ({type(e).__name__}). Riprova."}
                    s2.refresh(p2)
                    d2 = dati_di(p2)
                    d2["job_chat"] = {"stato": "finito", "esito": {k: ctx.get(k) for k in ("errore", "sospetti", "bozza", "nota") if ctx.get(k)}}
                    salva_dati(p2, d2)
                    s2.commit()
            except Exception:                                  # noqa: BLE001
                pass
        threading.Thread(target=lavoro, daemon=True).start()
        return render(request, "chat.html", **ctx_chat(s, p))

    @app.get("/pratiche/{pid}/chat/stato")
    def chat_stato(pid: int, u=Depends(utente_corrente), s=Depends(db)):
        p = carica(s, pid)
        return {"stato": (dati_di(p).get("job_chat") or {}).get("stato", "nessuno")}

    @app.post("/pratiche/{pid}/chat", response_class=HTMLResponse)
    async def chat_invia(request: Request, pid: int, u=Depends(utente_corrente), s=Depends(db)):
        f = await request.form()
        check_csrf(request, f.get("csrf", ""))
        p = carica(s, pid)
        testo = str(f.get("messaggio", "")).strip()
        if not testo:
            return render(request, "chat.html", **ctx_chat(s, p, errore="Scrivi un messaggio."))
        return avvia_turno(request, s, p, testo[:8000], forza=bool(f.get("forza")))

    @app.post("/pratiche/{pid}/chat/anagrafica", response_class=HTMLResponse)
    async def chat_anagrafica(request: Request, pid: int, u=Depends(utente_corrente), s=Depends(db)):
        """Per ogni nome segnalato: e' una persona, un ente oppure non e' un dato personale. Poi il messaggio riparte."""
        f = await request.form()
        check_csrf(request, f.get("csrf", ""))
        p = carica(s, pid)
        d = dati_di(p)
        nomi, tipi = f.getlist("nome"), f.getlist("tipo")
        for n, t in zip(nomi, tipi):
            n = str(n).strip()
            if t in ("persona", "ente"):
                registra_nomi(d, [(n, t)])
            elif t == "ignora" and n not in d.setdefault("chat_ignora", []):
                d["chat_ignora"].append(n)
        salva_dati(p, d)
        s.commit()
        testo = str(f.get("messaggio", "")).strip()
        if not testo:
            return render(request, "chat.html", **ctx_chat(s, p))
        return avvia_turno(request, s, p, testo)

    @app.post("/pratiche/{pid}/chat/documento", response_class=HTMLResponse)
    async def chat_documento(request: Request, pid: int, u=Depends(utente_corrente), s=Depends(db)):
        f = await request.form()
        check_csrf(request, f.get("csrf", ""))
        p = carica(s, pid)
        up = f.get("file")
        if up is None or not getattr(up, "filename", ""):
            return render(request, "chat.html", **ctx_chat(s, p, errore="Scegli un file da caricare."))
        dati_file = await up.read()
        if len(dati_file) > 15 * 1024 * 1024:
            return render(request, "chat.html", **ctx_chat(s, p, errore="File troppo grande (massimo 15 MB)."))
        try:
            tipo, testo_doc, nomi = chat_mod.estrai_testo(up.filename, dati_file)
        except ValueError as e:
            return render(request, "chat.html", **ctx_chat(s, p, errore=str(e)))
        d = dati_di(p)
        registra_nomi(d, nomi)
        doc = DocumentoPratica(pratica_id=p.id, nome_cifrato=cif.cifra_testo(up.filename[:200]), tipo=tipo,
                               testo_cifrato=cif.cifra_testo(testo_doc), caratteri=len(testo_doc))
        s.add(doc)
        s.flush()
        if tipo == "movimenti_crediti":
            from . import crediti
            d["movimenti_crediti"] = crediti.movimenti_da_righe(crediti.righe_da_xlsx(dati_file))
            aggiorna_analisi(s, p, d)
        if tipo == "xml_fattura":
            for ft in chat_mod.fatture_xml(dati_file):
                s.add(FatturaPratica(pratica_id=p.id, documento_id=doc.id, dati_cifrati=cif.cifra_json(ft)))
            s.flush()
            aggiorna_analisi(s, p, d)
        salva_dati(p, d)
        s.commit()
        return avvia_turno(request, s, p, f"Ho caricato il documento «{up.filename[:120]}» ({tipo}, {len(testo_doc)} caratteri). Cosa ne deduci e cosa manca?")

    @app.post("/pratiche/{pid}/chat/riscontro", response_class=HTMLResponse)
    def chat_riscontro(request: Request, pid: int, rid: str = Form(""), azione: str = Form(...), csrf: str = Form(""),
                       u=Depends(utente_corrente), s=Depends(db)):
        """L'operatore conferma o scarta un riscontro proposto (dal programma o dall'AI): solo i confermati vanno negli atti."""
        check_csrf(request, csrf)
        p = carica(s, pid)
        d = dati_di(p)
        stato = {"conferma": "confermato", "scarta": "scartato", "riapri": "proposto", "conferma_tutti": "confermato"}.get(azione)
        if not stato:
            raise HTTPException(400, "Azione non valida")
        for r in d.get("riscontri", []):
            if (azione == "conferma_tutti" and r["stato"] == "proposto") or r["id"] == rid:
                r["stato"] = stato
        salva_dati(p, d)
        s.commit()
        return render(request, "chat.html", **ctx_chat(s, p))

    @app.post("/pratiche/{pid}/chat/genera", response_class=HTMLResponse)
    def chat_genera(request: Request, pid: int, fase: str = Form(...), giornata: str = Form(""), csrf: str = Form(""),
                    u=Depends(utente_corrente), s=Depends(db)):
        check_csrf(request, csrf)
        p = carica(s, pid)
        try:
            f = workflow.fase_per_chiave(p.tipo, fase)
        except KeyError:
            raise HTTPException(404)
        if not f.atto:
            raise HTTPException(400, "Questa fase non prevede un atto")
        if f.atto == "INVITO":
            return RedirectResponse(f"/pratiche/{pid}/invito", status_code=303)
        try:
            workflow.puo_avviare(p.tipo, fase, stati_di(p))
        except workflow.OrdineViolato as e:
            return render(request, "chat.html", **ctx_chat(s, p, errore=f"Ordine della circolare: {e}"))
        d = dati_di(p)
        giornata = giornata.strip()
        rec = next((x for x in p.fasi if x.chiave == fase), None)
        if p.tipo == "controllo" and fase == "avvio":            # PVOC del primo giorno: formule fisse del Reparto, senza AI
            dati = pvoc_primo_iniziale(p, d)
            if giornata:
                dati["data"] = giornata
            a = crea_pvoc_primo(s, p, d, dati)
        else:
            pseudo = pseudo_per(d)
            fasc = d.get("fascicolo", {}) or {}
            docs = documenti_di(s, p)
            appunti = (f"MOTIVAZIONE DEL CONTROLLO: {fasc.get('motivazione', '')}\nOBIETTIVO: {fasc.get('obiettivo', '')}\n"
                       "DOCUMENTI ACQUISITI:\n" + "\n".join(f"--- {x['nome']} ---\n{x['testo'][:q]}" for x, q in zip(docs, chat_mod.quote_documenti([len(y['testo']) for y in docs], totale=120_000)))
                       + "\nINDICAZIONI DELL'OPERATORE NELLA CHAT:\n"
                       + "\n".join(cif.decifra_testo(m.contenuto_cifrato) for m in messaggi_di(s, p) if m.ruolo == "user")[-12000:])
            ris = [r for r in d.get("riscontri", []) if r["stato"] == "confermato" and (f.atto == "PVC" or r["fase"] == fase)]
            istruzione = ISTRUZIONI[f.atto]
            if d.get("base_normativa"):
                appunti += "\nBASE NORMATIVA RACCOLTA (fonti aperte, ricerche automatiche):\n" + chat_mod.base_normativa_testo(d["base_normativa"], 9000)
            istruzione += (" Riferimenti normativi, di prassi e giurisprudenziali: usa solo quelli presenti in BASE NORMATIVA RACCOLTA o nei "
                           "RISCONTRI; se te ne serve un altro scrivi [DA COMPILARE: riferimento da verificare].")
            metodo_txt, esempi = metodo_per(s, d, p, f.atto, f.titolo)
            appunti += "\nMETODO DEL REPARTO PERTINENTE (precedenti, schede di ragionamento, spunti operativi):\n" + metodo_txt
            istruzione += "\n\n" + metodo_mod.REGOLA_CONCILIAZIONE
            if ris:
                appunti += ("\nRISCONTRI CONFERMATI DA CONSTATARE IN QUESTO ATTO (id | periodo | tipo):\n" + "\n".join(
                    f"- {r['id']} | {r['periodo']} | {r['tipo']}: {r['descrizione']} Norma: {r['norma']}."
                    + (f" Ragionamento: {r['ragionamento']}." if r.get("ragionamento") else "")
                    + (f" Effetti a catena da constatare a parte: {'; '.join(r['effetti'])}." if r.get("effetti") else "")
                    + " Importi tracciati: "
                    + (", ".join("{{IMPORTO:" + i + "}}" for i in r["importi"]) or "nessuno") for r in ris))
                istruzione += (" Nell'atto CONSTATA, una per una, le violazioni elencate in RISCONTRI CONFERMATI: fatto accertato, periodo "
                               "d'imposta, norma violata e, se presenti, gli importi con {{IMPORTO:id}}. Non constatare violazioni non elencate, "
                               "non attenuare ne' enfatizzare, non inventare importi.")
                if f.atto == "PVC":
                    istruzione += " Nel PVC raggruppa le violazioni per periodo d'imposta e per tributo, distinguendo formali e sostanziali."
            try:
                contesto = contesto_ai(p, d, appunti, f, giornata)
                registro = registro_sicuro(d)
                ignora = set(d.get("chat_ignora", []))
                libero = "\n".join([fasc.get("motivazione", ""), fasc.get("obiettivo", "")] + [x["testo"] for x in docs]
                                    + [cif.decifra_testo(mm.contenuto_cifrato) for mm in messaggi_di(s, p) if mm.ruolo == "user"])
                sosp = [n for n in chat_mod.nomi_sospetti(pseudo.anonimizza(libero)) if n not in ignora]
                if sosp:
                    return render(request, "chat.html", **ctx_chat(s, p, sospetti=sosp, bozza="",
                                                                  errore="Prima di redigere l'atto indica come trattare questi nomi."))
                b = ai_mod.genera_bozza(pseudo, istruzione=istruzione, contesto=contesto, checklist=list(f.checklist),
                                        esempi=esempi, modello=st.anthropic_model, client=ai_client, registro=registro)
            except ai_mod.LeakError as e:
                return render(request, "chat.html", **ctx_chat(s, p, errore=f"Invio BLOCCATO: {e}."))
            except (ai_mod.AIDisattivata, ai_mod.AIRifiutata, llm_compat.ServizioAIErrore) as e:
                return render(request, "chat.html", **ctx_chat(s, p, errore=str(e)))
            except Exception as e:
                return render(request, "chat.html", **ctx_chat(s, p, errore=f"Errore del servizio AI ({type(e).__name__}). Riprova."))
            s.add(LogAI(pratica_id=p.id, sezione=f"{f.atto}/{f.chiave}", modello=b.modello, testo_inviato=b.inviato))
            testo_atto = b.testo
            if f.atto == "PVC":                                  # parte fissa del Reparto + sezioni 1-4 dell'AI
                sez = pvc_mod.separa_sezioni(b.testo)
                if not sez:
                    s.commit()
                    return render(request, "chat.html", **ctx_chat(s, p, errore="La risposta dell'AI non e' nel formato atteso "
                                                                   "(quattro sezioni marcate). Riprova a generare."))
                testo_atto = pvc_mod.costruisci(pvc_iniziale(p, d), d.get("verbalizzanti", []),
                                                impresa=d.get("profilo", {}).get("forma", "impresa") == "impresa", sezioni=sez)
            a = Atto(pratica_id=p.id, tipo=f.atto, fase=f.chiave, giornata=giornata, generato_da_ai=1,
                     contenuto_cifrato=cif.cifra_testo(testo_atto))
            s.add(a)
        if rec is not None and rec.stato == "da_fare":
            rec.stato = "in_corso"
        fasc = d.setdefault("fascicolo", {})
        fasc["proposte"] = [x for x in fasc.get("proposte", []) if x.get("fase") != fase]
        salva_dati(p, d)
        s.commit()
        return RedirectResponse(f"/pratiche/{pid}/atto/{a.id}", status_code=303)

    # ---------------------------------------------------------------- biblioteca della prassi
    @app.get("/prassi", response_class=HTMLResponse)
    def prassi_pagina(request: Request, u=Depends(utente_corrente), s=Depends(db)):
        prassi_mod.assicura_indice(s)
        return render(request, "prassi.html", b=prassi_mod.stato_biblioteca(s), nota=request.query_params.get("nota"))

    @app.post("/prassi/aggiorna")
    def prassi_aggiorna(request: Request, csrf: str = Form(""), u=Depends(utente_corrente), s=Depends(db)):
        check_csrf(request, csrf)
        prassi_mod.assicura_indice(s)
        for x in s.scalars(select(PrassiDocumento).where(PrassiDocumento.stato == "errore")).all():
            x.aggiornato_il = dt.datetime(2000, 1, 1, tzinfo=dt.timezone.utc)
        s.commit()
        prassi_mod.sincronizza_in_background(SM, None)
        return RedirectResponse("/prassi?nota=Scaricamento+avviato:+ricarica+la+pagina+tra+qualche+istante", status_code=303)

    @app.post("/prassi/aggiungi")
    def prassi_aggiungi(request: Request, url: str = Form(""), titolo: str = Form(""), temi: str = Form(""), csrf: str = Form(""),
                        u=Depends(utente_corrente), s=Depends(db)):
        check_csrf(request, csrf)
        url = url.strip()
        if not prassi_mod.host_ammesso(url):
            return RedirectResponse("/prassi?nota=Indirizzo+non+ufficiale:+non+aggiunto", status_code=303)
        if s.scalar(select(PrassiDocumento).where(PrassiDocumento.url == url)) is None:
            s.add(PrassiDocumento(codice=f"MAN-{abs(hash(url)) % 100000}", tipo="documento", titolo=titolo.strip()[:400] or url[-80:], url=url,
                                  temi=(temi.strip() or "manuale")[:400], origine="manuale"))
            s.commit()
        prassi_mod.sincronizza_in_background(SM, None)
        return RedirectResponse("/prassi?nota=Documento+aggiunto:+scaricamento+avviato", status_code=303)

    @app.post("/prassi/carica")
    async def prassi_carica(request: Request, u=Depends(utente_corrente), s=Depends(db)):
        """Se il sito ufficiale non e' raggiungibile dal server: si carica il PDF scaricato a mano e entra in biblioteca come gli altri."""
        f = await request.form()
        check_csrf(request, f.get("csrf", ""))
        up = f.get("file")
        if up is None or not getattr(up, "filename", ""):
            return RedirectResponse("/prassi?nota=Scegli+un+file", status_code=303)
        try:
            _, testo, _ = chat_mod.estrai_testo(up.filename, await up.read())
        except ValueError as e:
            return RedirectResponse("/prassi?nota=" + str(e).replace(" ", "+")[:80], status_code=303)
        cod = str(f.get("codice", "")).strip().upper()
        d = s.scalar(select(PrassiDocumento).where(PrassiDocumento.codice == cod)) if cod else None
        if d is None:
            d = PrassiDocumento(codice=cod or f"MAN-{abs(hash(up.filename)) % 100000}", tipo="documento", titolo=str(f.get("titolo", "")).strip()[:400] or up.filename[:200],
                                url="", origine="manuale")
            s.add(d)
        d.testo, d.stato, d.errore = testo[:900000], "pronto", ""
        if str(f.get("temi", "")).strip():
            d.temi = str(f.get("temi")).strip()[:400]
        s.commit()
        return RedirectResponse("/prassi?nota=Documento+caricato", status_code=303)

    # ---------------------------------------------------------------- libreria del Reparto (metodo, precedenti, spunti)
    def libreria_di(s) -> list[dict]:
        out = []
        for x in s.scalars(select(ConoscenzaReparto).order_by(ConoscenzaReparto.id)).all():
            v = cif.decifra_json(x.dati_cifrati) or {}
            out.append({"id": x.id, "tipo": x.tipo, "atto": x.atto, "stato": x.stato, "titolo": v.get("titolo", ""),
                        "tag": v.get("tag", ""), "testo": v.get("testo", ""), "scheda": v.get("scheda", ""),
                        "sospetti": v.get("sospetti", []), "integrato": False})
        return out + metodo_mod.integrati()

    def voce_salva(x: ConoscenzaReparto, **campi) -> None:
        v = cif.decifra_json(x.dati_cifrati) or {}
        v.update(campi)
        x.dati_cifrati = cif.cifra_json(v)

    def libreria_ctx(s, **extra) -> dict:
        voci = libreria_di(s)
        return {"voci": voci, "da_rivedere": [v for v in voci if v["stato"] == "da_revisionare"], "errore": None, "nota": None,
                "ai": _stato_ai(), **extra}

    def distilla_voce(s, x: ConoscenzaReparto) -> str | None:
        """Estrae la scheda di ragionamento da un precedente pronto. Ritorna un messaggio d'errore oppure None."""
        v = cif.decifra_json(x.dati_cifrati) or {}
        try:
            scheda = metodo_mod.distilla(ai_client or ai_mod._client(), st.anthropic_model, x.atto, v.get("testo", ""))
        except ai_mod.LeakError as e:
            return f"Scheda non estratta: nel testo resta qualcosa di riconoscibile ({e})."
        except (ai_mod.AIDisattivata, ai_mod.AIRifiutata, llm_compat.ServizioAIErrore) as e:
            return f"Scheda non estratta: {e}"
        except Exception as e:
            return f"Scheda non estratta ({type(e).__name__}): riprova dal pulsante «Estrai di nuovo il ragionamento»."
        voce_salva(x, scheda=scheda)
        return None

    def inserisci_voce(s, tipo: str, atto: str, titolo: str, tag: str, testo: str) -> tuple[ConoscenzaReparto, str | None]:
        pulito, sospetti = metodo_mod.ripulisci(testo)
        x = ConoscenzaReparto(tipo=tipo, atto=atto if atto in ("PVOC", "PVV", "PVC", "CNR") else "",
                              stato="da_revisionare" if sospetti else "pronto")
        x.dati_cifrati = cif.cifra_json({"titolo": titolo.strip()[:200] or "Senza titolo", "tag": tag.strip()[:200],
                                         "testo": pulito, "scheda": "", "sospetti": sospetti})
        s.add(x)
        s.flush()
        errore = None
        if tipo == "precedente" and not sospetti:
            errore = distilla_voce(s, x)
        s.commit()
        return x, errore

    @app.get("/libreria", response_class=HTMLResponse)
    def libreria_vista(request: Request, u=Depends(utente_corrente), s=Depends(db)):
        return render(request, "libreria.html", **libreria_ctx(s))

    @app.post("/libreria/spunto", response_class=HTMLResponse)
    def libreria_spunto(request: Request, titolo: str = Form(...), tag: str = Form(""), atto: str = Form(""),
                        testo: str = Form(...), csrf: str = Form(""), u=Depends(utente_corrente), s=Depends(db)):
        check_csrf(request, csrf)
        if not testo.strip():
            return render(request, "libreria.html", **libreria_ctx(s, errore="Scrivi il testo dello spunto."))
        inserisci_voce(s, "spunto", atto, titolo, tag, testo.strip()[:8000])
        return render(request, "libreria.html", **libreria_ctx(s, nota="Spunto salvato."))

    @app.post("/libreria/precedente", response_class=HTMLResponse)
    async def libreria_precedente(request: Request, u=Depends(utente_corrente), s=Depends(db)):
        f = await request.form()
        check_csrf(request, f.get("csrf", ""))
        up = f.get("file")
        if up is None or not getattr(up, "filename", ""):
            return render(request, "libreria.html", **libreria_ctx(s, errore="Scegli il file dell'atto."))
        dati_file = await up.read()
        if len(dati_file) > 15 * 1024 * 1024:
            return render(request, "libreria.html", **libreria_ctx(s, errore="File troppo grande (massimo 15 MB)."))
        try:
            _, testo, _ = chat_mod.estrai_testo(up.filename, dati_file)
        except ValueError as e:
            return render(request, "libreria.html", **libreria_ctx(s, errore=str(e)))
        x, errore = inserisci_voce(s, "precedente", str(f.get("atto", "")), str(f.get("titolo", "")) or up.filename.rsplit(".", 1)[0],
                                   str(f.get("tag", "")), testo)
        nota = ("Atto caricato. Prima di usarlo controlla i nomi dubbi qui sotto." if x.stato == "da_revisionare"
                else "Atto caricato e ripulito dai dati personali." + ("" if errore else " Ragionamento estratto."))
        return render(request, "libreria.html", **libreria_ctx(s, nota=nota, errore=errore))

    @app.post("/libreria/{vid}/revisione", response_class=HTMLResponse)
    async def libreria_revisione(request: Request, vid: int, u=Depends(utente_corrente), s=Depends(db)):
        """L'operatore classifica i nomi dubbi (persona / ente / non e' un dato personale); poi il testo e' pronto."""
        f = await request.form()
        check_csrf(request, f.get("csrf", ""))
        x = s.get(ConoscenzaReparto, vid)
        if not x:
            raise HTTPException(404)
        v = cif.decifra_json(x.dati_cifrati) or {}
        scelte = {str(n): str(t) for n, t in zip(f.getlist("nome"), f.getlist("tipo"))}
        testo = metodo_mod.applica_nomi(v.get("testo", ""), scelte)
        testo, ancora = metodo_mod.ripulisci(testo)
        ignorati = {n for n, t in scelte.items() if t == "ignora"}
        ancora = [n for n in ancora if n not in ignorati]
        voce_salva(x, testo=testo, sospetti=ancora)
        x.stato = "da_revisionare" if ancora else "pronto"
        errore = None
        if x.stato == "pronto" and x.tipo == "precedente":
            errore = distilla_voce(s, x)
        s.commit()
        return render(request, "libreria.html", **libreria_ctx(s, errore=errore,
                                                               nota="Testo pronto." if x.stato == "pronto" else "Restano nomi da classificare."))

    @app.post("/libreria/{vid}/scheda", response_class=HTMLResponse)
    def libreria_scheda(request: Request, vid: int, scheda: str = Form(""), azione: str = Form("salva"), csrf: str = Form(""),
                        u=Depends(utente_corrente), s=Depends(db)):
        check_csrf(request, csrf)
        x = s.get(ConoscenzaReparto, vid)
        if not x:
            raise HTTPException(404)
        errore = None
        if azione == "rigenera":
            errore = distilla_voce(s, x)
        else:
            voce_salva(x, scheda=scheda.strip()[:6000])
        s.commit()
        return render(request, "libreria.html", **libreria_ctx(s, errore=errore))

    @app.post("/libreria/{vid}/elimina")
    def libreria_elimina(request: Request, vid: int, csrf: str = Form(""), u=Depends(utente_corrente), s=Depends(db)):
        check_csrf(request, csrf)
        x = s.get(ConoscenzaReparto, vid)
        if x:
            s.delete(x)
            s.commit()
        return RedirectResponse("/libreria", status_code=303)

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
