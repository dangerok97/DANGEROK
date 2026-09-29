"""Anonimizzazione locale di file .docx (da eseguire PRIMA di caricare atti d'esempio altrove).

Cosa fa: sostituisce i dati riconosciuti in corpo, tabelle, intestazioni/piè di pagina; azzera i metadati
(autore, ultimo salvataggio, titolo); neutralizza i collegamenti mailto/URL. Cosa NON fa: non puo'
ripulire oggetti incorporati (Excel/immagini) - in tal caso si ferma (fail-closed) salvo consenso esplicito.
La formattazione interna a un paragrafo modificato viene semplificata (si perde il grassetto/corsivo a meta' frase).
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass

import docx

from .pseudonymizer import Pseudonymizer


class OggettiIncorporati(Exception):
    pass


@dataclass
class Esito:
    paragrafi_modificati: int
    segnaposto: dict[str, str]
    avvisi: list[str]
    residui: list[str]


def _paragrafi(doc):
    def da_container(c):
        for p in c.paragraphs:
            yield p
        for t in getattr(c, "tables", []):
            for r in t.rows:
                for cell in r.cells:
                    yield from da_container(cell)

    yield from da_container(doc)
    for sez in doc.sections:
        for parte in (sez.header, sez.footer, sez.first_page_header, sez.first_page_footer,
                      sez.even_page_header, sez.even_page_footer):
            try:
                yield from da_container(parte)
            except Exception:
                continue


def anonimizza_docx(src: str, dst: str, pseudo: Pseudonymizer, consenti_oggetti: bool = False) -> Esito:
    d = docx.Document(src)
    avvisi: list[str] = []
    embedded = [n for n in d.part.package.iter_parts()
                if str(n.partname).startswith(("/word/embeddings/", "/word/media/", "/word/activeX/"))]
    if embedded and not consenti_oggetti:
        raise OggettiIncorporati(
            f"Il documento contiene {len(embedded)} oggetti incorporati/immagini che non posso ripulire: "
            "rimuovili a mano o usa --consenti-oggetti (a tuo rischio).")
    if embedded:
        avvisi.append(f"{len(embedded)} oggetti incorporati NON anonimizzati")

    n = 0
    testi_finali: list[str] = []
    visti: set = set()  # gli elementi XML stessi (non i loro id(): quelli possono essere riutilizzati)
    for p in _paragrafi(d):
        if p._p in visti:
            continue
        visti.add(p._p)
        orig = p.text
        if not orig.strip():
            continue
        nuovo = pseudo.anonimizza(orig)
        testi_finali.append(nuovo)
        if nuovo != orig and p.runs:
            p.runs[0].text = nuovo
            for r in p.runs[1:]:
                r.text = ""
            n += 1

    for rel in d.part.rels.values():
        if rel.is_external and rel.reltype.endswith("/hyperlink"):
            rel._target = "https://anonimizzato.invalid/"
            avvisi.append("collegamento ipertestuale neutralizzato")

    cp = d.core_properties
    cp.author = cp.last_modified_by = cp.title = cp.subject = cp.comments = cp.keywords = cp.category = ""
    d.save(dst)
    residui = pseudo.verifica("\n".join(testi_finali))
    return Esito(n, pseudo.tabella, sorted(set(avvisi)), residui)


def salva_mappa(esito: Esito, path: str) -> None:
    """La mappa segnaposto->dato reale resta SOLO in locale: non caricarla ne' committarla."""
    pathlib.Path(path).write_text(json.dumps(esito.segnaposto, ensure_ascii=False, indent=2), encoding="utf-8")
