"""Word di PVOC, PVV, PVC e CNR con le caratteristiche degli atti del Reparto (misurate sugli esempi):
A4, Arial 12, margini propri di ciascun atto, stemma + intestazione del Reparto in testa alla prima pagina,
intestazione corrente dalla seconda pagina ("Segue p.v. di ... redatto in data ... nei confronti di ...", foglio n.).

Nel testo dell'AI valgono le stesse convenzioni di `wordexport` ({{SPIEGA: ...}} in giallo, [DA COMPILARE: ...] in
turchese). Struttura riconosciuta: titolo (riga "PROCESSO VERBALE ..."), righe TUTTE MAIUSCOLE = titoletti in grassetto
(VERBALIZZANTI centrato), elenchi con "-" o "•", riga "I VERBALIZZANTI ... LA PARTE" = firme.
"""
from __future__ import annotations

import io
import pathlib
import re
import zipfile

import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH as AL, WD_COLOR_INDEX, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Cm, Pt

from . import wordexport

_LOGO = pathlib.Path(__file__).parent / "wordtemplates" / "invito.docx"
INDIRIZZO = "Via delle Fiamme Gialle n. 1 - 01016 Tarquinia (VT) – 0766/856028 – Pec: vt1120000p@pec.gdf.it"

# margini (alto, basso, sinistro, destro) e distanza dell'intestazione, in cm, misurati sugli esempi del Reparto
FORMATI = {
    "PVOC": dict(titolo="PROCESSO VERBALE DI OPERAZIONI COMPIUTE", pt_titolo=12, margini=(1.27, 1.00, 1.27, 1.27),
                 corrente="Segue p.v. di operazioni compiute redatto in data {data} nei confronti di {soggetto}",
                 foglio="- foglio n. {n} -", pt_corrente=10, box=True, logo_cm=(1.51, 2.01), pt_ind=10),
    "PVV": dict(titolo="PROCESSO VERBALE DI VERIFICA", pt_titolo=12, margini=(0.75, 1.00, 2.00, 2.00),
                corrente="Segue p.v. di verifica redatto in data {data} nei confronti di {soggetto}",
                foglio="- foglio n. {n} -", pt_corrente=11, box=True, logo_cm=(1.22, 1.37), pt_ind=9),
    "PVC": dict(titolo="PROCESSO VERBALE DI CONSTATAZIONE", pt_titolo=14, margini=(2.00, 2.25, 2.00, 2.00),
                corrente="segue processo verbale di constatazione redatto in data {data} nei confronti di {soggetto}",
                foglio="foglio nr. {n}", pt_corrente=10, box=True, logo_cm=(1.93, 1.88), pt_ind=10),
    "CNR": dict(titolo="", pt_titolo=12, margini=(2.50, 1.75, 2.00, 2.00),
                corrente="Segue comunicazione di notizia di reato ex art. 347 c.p.p. redatta in data {data} nei confronti di {soggetto}",
                foglio="foglio n. {n}", pt_corrente=10, box=False, logo_cm=(1.93, 1.88), pt_ind=10),
}
_RE_TITOLO = re.compile(r"^\s*PROCESSO VERBALE\b", re.I)
_RE_TITOLO_PREFISSO = re.compile(r"^\s*PROCESSO VERBALE(?: DI [A-ZÀ-Ü' ]+?)?(?=\s+[A-Z][a-zà-ü]|\s*[:\-–.]|\s*$)[\s:\-–.]*")
_RE_FIRME = re.compile(r"^\s*I VERBALIZZANTI\b")
_RE_ELENCO = re.compile(r"^\s*(--|-|•|–|\+)\s+(.*)$")


def _logo() -> bytes:
    with zipfile.ZipFile(_LOGO) as z:
        return z.read("word/media/image1.png")


def _font(run, size=None, bold=None, italic=None):
    run.font.name = "Arial"
    rpr = run._r.get_or_add_rPr()
    rpr.rFonts.set(qn("w:cs"), "Arial")
    rpr.rFonts.set(qn("w:eastAsia"), "Arial")
    if size:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic
    return run


def _campo(par, istruzione: str, **fmt):
    for tipo, testo in (("begin", None), (None, istruzione), ("separate", None), (None, "1"), ("end", None)):
        r = _font(par.add_run(), **fmt)
        if tipo:
            f = OxmlElement("w:fldChar")
            f.set(qn("w:fldCharType"), tipo)
            r._r.append(f)
        elif testo == istruzione:
            t = OxmlElement("w:instrText")
            t.set(qn("xml:space"), "preserve")
            t.text = f" {istruzione} "
            r._r.append(t)
        else:
            r.text = testo


def _riga(par, testo: str, con_spiegazioni: bool, size=12, bold=False, italic=False):
    """Scrive il testo nel paragrafo applicando giallo (spiegazioni) e turchese (dati da compilare)."""
    grassetto = False                                        # **testo** = grassetto (anche a cavallo dei segmenti)
    for t, k in wordexport.segmenti(testo, con_spiegazioni):
        for i, parte in enumerate(t.split("**") if k != "spiega" else [t]):
            if i:
                grassetto = not grassetto
            if not parte:
                continue
            r = _font(par.add_run(parte), size=size, bold=(bold or grassetto) or None,
                      italic=True if (k == "spiega" or italic) else None)
            if k == "spiega":
                r.font.highlight_color = WD_COLOR_INDEX.YELLOW
            elif k == "dacomp":
                r.font.highlight_color = WD_COLOR_INDEX.TURQUOISE


def _par(d, allineamento=AL.JUSTIFY, prima=6, dopo=None, rientro=None, sporgente=None):
    p = d.add_paragraph()
    p.alignment = allineamento
    f = p.paragraph_format
    f.space_before, f.space_after = Pt(prima), Pt(0 if dopo is None else dopo)
    if rientro is not None:
        f.left_indent = Cm(rientro)
    if sporgente is not None:
        f.first_line_indent = Cm(-sporgente)
    return p


def _riquadro(par):
    ppr = par._p.get_or_add_pPr()
    ppr.append(parse_xml(
        f'<w:pBdr {nsdecls("w")}>' + "".join(
            f'<w:{l} w:val="single" w:sz="6" w:space="1" w:color="auto"/>' for l in ("top", "left", "bottom", "right"))
        + "</w:pBdr>"))
    ppr.append(parse_xml(f'<w:shd {nsdecls("w")} w:val="pct10" w:color="auto" w:fill="auto"/>'))


def _intestazione_corrente(sez, fmt, data: str, soggetto: str):
    sez.different_first_page_header_footer = True
    h = sez.header
    h.is_linked_to_previous = False
    p = h.paragraphs[0]
    p.alignment = AL.LEFT
    if fmt["box"]:
        _riquadro(p)
    p.paragraph_format.tab_stops.add_tab_stop(Cm(16.0 if fmt["margini"][2] > 1.5 else 18.0), WD_TAB_ALIGNMENT.RIGHT)
    _riga(p, fmt["corrente"].format(data=data, soggetto=soggetto), True, size=fmt["pt_corrente"], italic=True)
    _font(p.add_run("\t"), size=fmt["pt_corrente"], italic=True)
    pre, post = fmt["foglio"].split("{n}")
    _font(p.add_run(pre), size=fmt["pt_corrente"], italic=True)
    _campo(p, "PAGE", size=fmt["pt_corrente"], italic=True)
    _font(p.add_run(post), size=fmt["pt_corrente"], italic=True)
    sez.first_page_header.is_linked_to_previous = False


def crea_atto(tipo: str, testo: str, *, con_spiegazioni: bool = True, data: str = "", soggetto: str = "") -> bytes:
    fmt = FORMATI[tipo]
    data = data.strip() or "[DA COMPILARE: data dell'atto]"
    soggetto = soggetto.strip() or "[DA COMPILARE: soggetto]"
    d = docx.Document()
    n = d.styles["Normal"]
    n.font.name, n.font.size = "Arial", Pt(12)
    n.element.get_or_add_rPr().rFonts.set(qn("w:cs"), "Arial")
    n.element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "Arial")
    n.paragraph_format.space_after = Pt(0)
    s = d.sections[0]
    s.page_width, s.page_height = Cm(21.0), Cm(29.7)
    s.top_margin, s.bottom_margin, s.left_margin, s.right_margin = (Cm(x) for x in fmt["margini"])
    s.header_distance = s.footer_distance = Cm(1.25)
    _intestazione_corrente(s, fmt, data, soggetto)

    # stemma e intestazione del Reparto (prima pagina)
    p = _par(d, AL.CENTER, prima=0)
    w, h = fmt["logo_cm"]
    p.add_run().add_picture(io.BytesIO(_logo()), width=Cm(w), height=Cm(h))
    for t, pt, b in (("Guardia di Finanza", 16, True), ("COMPAGNIA TARQUINIA", 16, True),
                     ("Sezione Operativa Volante", 12, True)):
        _font(_par(d, AL.CENTER, prima=0).add_run(t), size=pt, bold=b)
    _font(_par(d, AL.CENTER, prima=0).add_run(INDIRIZZO), size=fmt["pt_ind"])
    _par(d, prima=6)

    if fmt["titolo"]:
        _font(_par(d, AL.CENTER).add_run(fmt["titolo"]), size=fmt["pt_titolo"], bold=True)

    righe = re.sub(r"\{\{\s*SPIEGA:.*?\}\}", lambda m: m.group(0).replace("\n", " "), testo, flags=re.S | re.I).split("\n")
    titolo_visto = not fmt["titolo"]
    elenco_militari = False                                 # righe dopo VERBALIZZANTI: nominativi centrati
    for riga in righe:
        r = re.sub(r"^\s*#{1,6}\s+", "", riga.replace("\r", "")).rstrip()   # niente titoli markdown
        if not r.strip():
            _par(d, prima=6)
            continue
        nudo = wordexport.pulisci(r).strip()
        if not titolo_visto and _RE_TITOLO.match(nudo):
            titolo_visto = True
            if nudo.isupper() and len(nudo) < 90:
                continue                                    # il titolo lo mette il programma, identico agli esempi
            r = _RE_TITOLO_PREFISSO.sub("", r, count=1).strip()   # titolo e testo sulla stessa riga: si tiene il testo
            if not r:
                continue
            nudo = wordexport.pulisci(r).strip()
        if _RE_FIRME.match(nudo):
            colonne = [c.strip() for c in re.split(r"\s{2,}|\t+", nudo) if c.strip()]
            posizioni = {1: [3.5], 2: [3.5, 13.0], 3: [3.5, 9.0, 14.25]}.get(len(colonne), [3.5, 13.0])
            p = _par(d, AL.LEFT, prima=18)
            for x in posizioni:
                p.paragraph_format.tab_stops.add_tab_stop(Cm(x), WD_TAB_ALIGNMENT.CENTER)
            _font(p.add_run("".join("\t" + c for c in colonne)), size=12)
            continue
        m = _RE_ELENCO.match(r)
        if m:
            seg, corpo = m.group(1), m.group(2)
            if seg == "+":                                   # capoverso rientrato, senza trattino
                _riga(_par(d, rientro=0.635), corpo, con_spiegazioni)
            elif seg == "--":                                # sotto-punto (come gli elenchi annidati degli atti)
                p = _par(d, rientro=1.386, sporgente=0.635)
                p.paragraph_format.tab_stops.add_tab_stop(Cm(1.386))
                _riga(p, "\t" + corpo, con_spiegazioni)
            else:
                p = _par(d, rientro=0.635, sporgente=0.635)
                p.paragraph_format.tab_stops.add_tab_stop(Cm(0.635))
                _riga(p, "-\t" + corpo, con_spiegazioni)
            continue
        if nudo.isupper() and 3 <= len(nudo) <= 90 and not re.search(r"\d{3,}", nudo):
            centrato = nudo.startswith("VERBALIZZANTI") or nudo == "OPERAZIONI DI CONTROLLO ESEGUITE NEL GIORNO"
            elenco_militari = nudo.startswith("VERBALIZZANTI")
            p = _par(d, AL.CENTER if centrato else AL.LEFT)
            _riga(p, r.strip(), con_spiegazioni, bold=True)
            continue
        if elenco_militari:
            _riga(_par(d, AL.CENTER), r.strip(), con_spiegazioni)
            continue
        _riga(_par(d), r.strip(), con_spiegazioni)

    d.core_properties.author = d.core_properties.last_modified_by = ""
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()
