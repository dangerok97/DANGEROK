"""Esportazione in Word delle bozze, con le spiegazioni dell'AI evidenziate in giallo.

Convenzioni nel testo prodotto dall'AI:
- {{SPIEGA: ...}}         spiegazione del passaggio precedente (perche' e' scritto cosi', fonte, cautele)
- [DA COMPILARE: ...]     dato mancante che l'operatore deve inserire
In Word le spiegazioni diventano "(Spiegazione: ...)" in corsivo con evidenziatore GIALLO, i dati mancanti
sono evidenziati in TURCHESE. Per eliminare tutte le spiegazioni in Word: Ctrl+H > Altro > Formato >
Evidenziatore, sostituire con nulla; oppure scaricare la versione "pulita".
"""
from __future__ import annotations

import io
import re

import docx
from docx.enum.text import WD_COLOR_INDEX, WD_ALIGN_PARAGRAPH
from docx.shared import Pt

RE_SPIEGA = re.compile(r"\s*\{\{\s*SPIEGA:\s*(.*?)\s*\}\}", re.S | re.I)
RE_DACOMP = re.compile(r"(\[DA COMPILARE:[^\]]*\])")


def pulisci(testo: str) -> str:
    """Testo senza spiegazioni (i dati da compilare restano, perche' vanno completati)."""
    return RE_SPIEGA.sub("", testo)


def segmenti(riga: str, con_spiegazioni: bool) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    pos = 0
    for m in RE_SPIEGA.finditer(riga):
        if m.start() > pos:
            out.append((riga[pos:m.start()], "testo"))
        if con_spiegazioni:
            out.append((f" (Spiegazione: {m.group(1).strip()})", "spiega"))
        pos = m.end()
    if pos < len(riga):
        out.append((riga[pos:], "testo"))
    finale: list[tuple[str, str]] = []
    for t, k in out:
        if k != "testo":
            finale.append((t, k))
            continue
        for parte in RE_DACOMP.split(t):
            if parte:
                finale.append((parte, "dacomp" if RE_DACOMP.fullmatch(parte) else "testo"))
    return finale


def crea_docx(testo: str, con_spiegazioni: bool = True) -> bytes:
    d = docx.Document()
    stile = d.styles["Normal"]
    stile.font.name, stile.font.size = "Times New Roman", Pt(12)
    # una spiegazione puo' occupare piu' righe nel testo: la si tratta come unita' prima di dividere in paragrafi
    blocchi = []
    for blocco in re.split(r"\n", RE_SPIEGA.sub(lambda m: m.group(0).replace("\n", " "), testo)):
        blocchi.append(blocco)
    for riga in blocchi:
        p = d.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        segs = segmenti(riga, con_spiegazioni)
        if not segs and not riga.strip():
            continue
        titolo = riga.strip().isupper() and 3 < len(riga.strip()) < 90
        for t, k in segs:
            r = p.add_run(t)
            if titolo and k == "testo":
                r.bold = True
            if k == "spiega":
                r.italic = True
                r.font.highlight_color = WD_COLOR_INDEX.YELLOW
            elif k == "dacomp":
                r.font.highlight_color = WD_COLOR_INDEX.TURQUOISE
    d.core_properties.author = ""
    d.core_properties.last_modified_by = ""
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()
