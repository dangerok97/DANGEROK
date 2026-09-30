"""Biblioteca della prassi dell'Agenzia delle Entrate (e altre fonti ufficiali): indice per tema, download automatico dai siti
ufficiali, ricerca per paragrafi e scoperta di nuovi documenti dalle ricerche dell'assistente.

Flusso automatico (nessuna azione dell'operatore):
1. dal caso (tipologia, motivazione, documenti, riscontri) si riconoscono i TEMI (es. superbonus, sconto in fattura);
2. i documenti dell'indice per quei temi non ancora in biblioteca vengono scaricati (solo host ufficiali) e salvati;
3. per ogni turno si estraggono dai documenti i PARAGRAFI piu' pertinenti al caso e ai riscontri e si passano all'AI con
   documento e sezione, cosi' che citi la prassi (es. circolare 23/E del 2022) invece di ricordarla a memoria;
4. le fonti ufficiali trovate dalle ricerche dell'assistente (circolari, risoluzioni, risposte) entrano in biblioteca da sole.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import pathlib
import re
import threading
from urllib.parse import urlparse

from sqlalchemy import select

from . import metodo
from .models import PrassiDocumento

INDICE = pathlib.Path(__file__).parent / "knowledge" / "prassi_indice.json"
HOST_AMMESSI = ("agenziaentrate.gov.it", "finanze.gov.it", "mef.gov.it", "gazzettaufficiale.it", "normattiva.it",
                "cortedicassazione.it", "giustiziatributaria.gov.it", "eur-lex.europa.eu")
MAX_BYTE = 25 * 1024 * 1024
MAX_CARATTERI = 900_000
_lock = threading.Lock()


def indice() -> dict:
    return json.loads(INDICE.read_text(encoding="utf-8")) if INDICE.exists() else {"temi": {}, "documenti": []}


def host_ammesso(url: str) -> bool:
    u = urlparse(url)
    h = (u.hostname or "").lower()
    return u.scheme in ("http", "https") and any(h == d or h.endswith("." + d) for d in HOST_AMMESSI)


# ------------------------------------------------------------------ temi del caso
def temi_del_caso(testo: str) -> list[str]:
    """Temi dell'indice le cui parole chiave compaiono nel testo del caso (motivazione, documenti, riscontri, messaggi)."""
    t = " " + re.sub(r"\s+", " ", testo.lower()) + " "
    out = []
    for tema, chiavi in indice().get("temi", {}).items():
        punti = sum(1 for k in chiavi if k.lower() in t)
        if punti >= 2 or (punti >= 1 and tema.split()[0].lower() in t):
            out.append(tema)
    return out


# ------------------------------------------------------------------ scarico
def _testo_da_contenuto(dati: bytes, tipo_contenuto: str, url: str) -> str:
    if dati[:5] == b"%PDF-" or "pdf" in tipo_contenuto.lower():
        from pypdf import PdfReader
        try:
            r = PdfReader(io.BytesIO(dati))
            return "\n".join((p.extract_text() or "") for p in r.pages)[:MAX_CARATTERI]
        except Exception as e:                                 # noqa: BLE001
            raise ValueError("PDF non leggibile") from e
    from lxml import html
    doc = html.fromstring(dati)
    for el in doc.xpath("//script|//style|//nav|//footer"):
        el.getparent().remove(el)
    return re.sub(r"\n{3,}", "\n\n", doc.text_content())[:MAX_CARATTERI]


def scarica(url: str, client=None) -> str:
    """Testo del documento alla URL (solo host ufficiali, anche nei reindirizzamenti); prova anche la variante senza «/» finale."""
    try:
        return _scarica(url, client)
    except ValueError as e:
        if url.endswith("/") and "HTTP 4" in str(e):
            return _scarica(url.rstrip("/"), client)
        raise


def _scarica(url: str, client=None) -> str:
    """Scarica una URL. Solleva ValueError se non riesce."""
    import httpx
    if not host_ammesso(url):
        raise ValueError("Sito non ufficiale: il documento non viene scaricato")
    c = client or httpx.Client(timeout=40, follow_redirects=False, headers={"User-Agent": "Mozilla/5.0 (Dangerok biblioteca prassi)"})
    try:
        for _ in range(5):
            r = c.get(url)
            if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                url = str(httpx.URL(url).join(r.headers["location"]))
                if not host_ammesso(url):
                    raise ValueError("Reindirizzamento verso un sito non ufficiale")
                continue
            if r.status_code != 200:
                raise ValueError(f"Risposta HTTP {r.status_code}")
            if len(r.content) > MAX_BYTE:
                raise ValueError("Documento troppo grande")
            testo = _testo_da_contenuto(r.content, r.headers.get("content-type", ""), url)
            if len(testo.strip()) < 500:
                raise ValueError("Testo non estraibile (scansione o pagina vuota)")
            return testo
        raise ValueError("Troppi reindirizzamenti")
    except httpx.HTTPError as e:
        raise ValueError(f"Sito non raggiungibile ({type(e).__name__})") from e
    finally:
        if client is None:
            c.close()


# ------------------------------------------------------------------ biblioteca
def assicura_indice(s) -> None:
    """Porta in tabella i documenti dell'indice (stato da_scaricare) se mancano."""
    esistenti = {c for c in s.scalars(select(PrassiDocumento.codice)).all()}
    for x in indice().get("documenti", []):
        if x["codice"] not in esistenti:
            s.add(PrassiDocumento(codice=x["codice"], tipo=x.get("tipo", "circolare"), numero=x.get("numero", ""), anno=int(x.get("anno", 0)),
                                  titolo=x.get("titolo", "")[:400], url=x["url"], temi=x.get("temi", ""), origine="indice"))
    s.commit()


def sincronizza(s, temi: list[str] | None = None, scarica_fn=None, massimo: int = 12) -> dict:
    """Scarica i documenti in attesa (o in errore da piu' di un giorno) relativi ai temi. Ritorna i conteggi."""
    scarica_fn = scarica_fn or scarica
    assicura_indice(s)
    ora = dt.datetime.now(dt.timezone.utc)
    esito = {"scaricati": 0, "errori": 0, "gia_pronti": 0}
    q = select(PrassiDocumento).order_by(PrassiDocumento.anno.desc())
    for d in s.scalars(q).all():
        if temi is not None and not any(t.lower() in d.temi.lower() for t in temi):
            continue
        if d.stato == "pronto":
            esito["gia_pronti"] += 1
            continue
        agg = d.aggiornato_il if d.aggiornato_il.tzinfo else d.aggiornato_il.replace(tzinfo=dt.timezone.utc)
        if d.stato == "errore" and (ora - agg) < dt.timedelta(days=1):
            continue
        if esito["scaricati"] + esito["errori"] >= massimo:
            break
        try:
            d.testo = scarica_fn(d.url)
            d.stato, d.errore = "pronto", ""
            esito["scaricati"] += 1
        except ValueError as e:
            d.stato, d.errore = "errore", str(e)[:300]
            esito["errori"] += 1
        d.aggiornato_il = ora
        s.commit()
    return esito


def sincronizza_in_background(SM, temi: list[str], scarica_fn=None) -> None:
    """Avvia lo scarico in un thread (non blocca la chat); un solo scarico alla volta."""
    def lavoro():
        if not _lock.acquire(blocking=False):
            return
        try:
            with SM() as s:
                sincronizza(s, temi, scarica_fn)
        except Exception:                                      # noqa: BLE001
            pass
        finally:
            _lock.release()
    threading.Thread(target=lavoro, daemon=True).start()


def scopri_da_fonti(s, base_normativa: list[dict]) -> int:
    """Le fonti ufficiali trovate dalle ricerche (circolari, risoluzioni, risposte) entrano in biblioteca."""
    nuovi = 0
    esistenti = {u for u in s.scalars(select(PrassiDocumento.url)).all()}
    for v in base_normativa or []:
        for f in v.get("fonti", []):
            url = f.get("url") or ""
            titolo = (f.get("titolo") or "").strip()
            if not url or url in esistenti or not host_ammesso(url) or not f.get("ufficiale", True):
                continue
            m = re.search(r"(?i)\b(circolare|risoluzione|risposta|principio di diritto|sentenza)\b[^0-9]{0,12}(?:n\.?\s*)?(\d+(?:/[A-Z])?)(?:[^0-9]{1,20}(\d{4}))?", titolo)
            if not m and "/documents/" not in url and not url.lower().endswith(".pdf"):
                continue
            tipo = m.group(1).lower() if m else "documento"
            numero = m.group(2) if m else ""
            anno = int(m.group(3)) if m and m.group(3) else 0
            codice = re.sub(r"[^A-Z0-9]+", "-", f"{tipo[:4]}-{numero}-{anno}-{abs(hash(url)) % 10000}".upper())[:40]
            s.add(PrassiDocumento(codice=codice, tipo=tipo, numero=numero, anno=anno, titolo=titolo[:400] or url[-80:], url=url,
                                  temi=(v.get("quesito", "") or "")[:300], origine="scoperto"))
            esistenti.add(url)
            nuovi += 1
    if nuovi:
        s.commit()
    return nuovi


# ------------------------------------------------------------------ ricerca per paragrafi
def paragrafi(testo: str) -> list[tuple[str, str]]:
    """[(sezione, paragrafo)] dal testo: la sezione e' l'ultimo titolo numerato visto (es. «3.2 ...»)."""
    sezione, out = "", []
    for blocco in re.split(r"\n\s*\n|\n(?=\d{1,2}(?:\.\d{1,2}){0,3}\.?\s+[A-ZÀ-Ü])", testo):
        b = re.sub(r"\s+", " ", blocco).strip()
        if len(b) < 60:
            m = re.match(r"^(\d{1,2}(?:\.\d{1,2}){0,3})\.?\s+(.{3,160})$", b)
            if m:
                sezione = f"{m.group(1)} {m.group(2)[:80]}"
            continue
        m = re.match(r"^(\d{1,2}(?:\.\d{1,2}){0,3})\.?\s+([A-ZÀ-Ü][^.]{3,100})", b)
        if m and len(b) < 400:
            sezione = f"{m.group(1)} {m.group(2)[:80]}"
        out.append((sezione, b))
    return out


def cerca(s, interrogazione: str, temi: list[str] | None = None, n: int = 10, max_caratteri: int = 14000) -> list[dict]:
    """I paragrafi piu' pertinenti all'interrogazione nei documenti pronti dei temi: [{codice, titolo, sezione, testo}]."""
    q = metodo.parole(interrogazione)
    if not q:
        return []
    cand = []
    for d in s.scalars(select(PrassiDocumento).where(PrassiDocumento.stato == "pronto")).all():
        if temi is not None and not any(t.lower() in d.temi.lower() for t in temi):
            continue
        for sez, par in paragrafi(d.testo):
            w = metodo.parole(par + " " + sez)
            punti = len(q & w)
            if punti >= 3:
                cand.append((punti + (1 if len(par) > 200 else 0) + d.anno / 10000, d, sez, par))
    cand.sort(key=lambda x: -x[0])
    out, usati = [], 0
    for _, d, sez, par in cand:
        if len(out) >= n or usati + len(par) > max_caratteri:
            continue
        usati += len(par)
        out.append({"codice": d.codice, "titolo": f"{d.tipo} {d.numero} del {d.anno}" if d.numero else d.titolo, "sezione": sez, "testo": par[:1800]})
    return out


def passaggi_testo(passaggi: list[dict], stato: str = "") -> str:
    if not passaggi:
        return (stato + "\n" if stato else "") + "- nessun passaggio di prassi in biblioteca pertinente (o biblioteca non ancora scaricata)"
    righe = [stato] if stato else []
    for p in passaggi:
        righe.append(f"[{p['codice']} - {p['titolo']}{' - sez. ' + p['sezione'] if p['sezione'] else ''}] {p['testo']}")
    return "\n".join(righe)


def stato_biblioteca(s) -> dict:
    docs = s.scalars(select(PrassiDocumento).order_by(PrassiDocumento.anno.desc(), PrassiDocumento.codice)).all()
    return {"totale": len(docs), "pronti": sum(1 for d in docs if d.stato == "pronto"), "errori": sum(1 for d in docs if d.stato == "errore"),
            "documenti": [{"codice": d.codice, "tipo": d.tipo, "numero": d.numero, "anno": d.anno, "titolo": d.titolo, "stato": d.stato,
                           "errore": d.errore, "caratteri": len(d.testo or ""), "temi": d.temi, "origine": d.origine, "url": d.url} for d in docs]}
