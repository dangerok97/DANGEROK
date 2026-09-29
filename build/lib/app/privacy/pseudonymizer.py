"""Pseudonimizzazione dei testi prima dell'invio a servizi esterni (AI).

Principi:
- i dati identificativi vengono sostituiti da segnaposto stabili (es. [PERSONA_1]);
- la tabella segnaposto -> valore reale resta in memoria locale e non viene mai inviata;
- fail-closed: `verifica()` segnala ogni residuo riconoscibile e `anonimizza_o_blocca()` interrompe l'invio.

Limite dichiarato: il riconoscimento automatico non e' infallibile. I nomi vanno
forniti dall'anagrafica della pratica (`aggiungi_persona`, `aggiungi_ente`); i rilevatori
strutturati (CF, P.IVA, IBAN, e-mail, ecc.) coprono il resto.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

TOKEN_RE = re.compile(r"\[([A-Z_]+)_(\d+)\]")

_APOS = "['’`´]"
_STOP_PAROLE = {"di", "de", "del", "della", "dei", "degli", "delle", "da", "la", "il", "lo", "le",
                "e", "ed", "del", "van", "von", "el", "al", "d", "dal", "dalla", "detto"}
_FORME_GIURIDICHE = [
    r"s\.?\s?r\.?\s?l\.?\s?s\.?", r"s\.?\s?r\.?\s?l\.?", r"s\.?\s?p\.?\s?a\.?", r"s\.?\s?a\.?\s?s\.?",
    r"s\.?\s?n\.?\s?c\.?", r"s\.?\s?s\.?\s?d\.?", r"s\.?\s?s\.?", r"s\.?\s?c\.?\s?a\.?\s?r\.?\s?l\.?",
    r"soc(?:iet[àa]|\.)\s+cooperativa(?:\s+(?:sociale|agricola))?", r"a\s+socio\s+unico",
    r"a\s+responsabilit[àa]\s+limitata", r"e\s+c\.?", r"&\s*c\.?", r"di\s+.{2,40}\s+(?:e|&)\s+c\.?",
]
_RE_FORMA_FINALE = re.compile(r"[\s,\-]*(?:" + "|".join(_FORME_GIURIDICHE) + r")\s*$", re.IGNORECASE)

# --- rilevatori strutturati -------------------------------------------------------------
_CF_CHR = "[0-9LMNPQRSTUV]"  # cifre e lettere di omocodia
RE_CF = re.compile(
    rf"(?<![A-Za-z0-9])[A-Za-z]{{6}}{_CF_CHR}{{2}}[A-EHLMPR-Ta-ehlmpr-t]{_CF_CHR}{{2}}[A-Za-z]{_CF_CHR}{{3}}[A-Za-z](?![A-Za-z0-9])",
    re.IGNORECASE,
)
RE_PIVA = re.compile(r"(?<![\d.,])(?:IT\s?)?\d{11}(?![\d]|[.,]\d)")
RE_PIVA_CTX = re.compile(
    r"((?:partita\s+i\.?\s?v\.?\s?a\.?|p\.?\s?i\.?\s?v\.?\s?a\.?|c\.?\s?f\.?|codice\s+fiscale)\s*[:\-]?\s*)(\d{8,11})(?!\d)",
    re.IGNORECASE,
)
RE_IBAN_CAND = re.compile(r"(?<![A-Za-z0-9])[A-Z]{2}\d{2}(?:\s?[0-9A-Z]{4}){4,7}(?:\s?[0-9A-Z]{1,3})?(?![A-Za-z0-9])")
RE_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
RE_TEL = re.compile(r"(?<![\d/])(?:\+39\s?)?(?:0\d{1,3}[\s/.\-]?\d{5,8}|3\d{2}[\s.\-]?\d{6,7})(?![\d])")
RE_TARGA = re.compile(r"(?<![A-Za-z0-9])[A-Z]{2}\s?\d{3}\s?[A-Z]{2}(?![A-Za-z0-9])")
RE_DOC = re.compile(
    r"((?:patente(?:\s+di\s+guida)?|carta\s+d.identit[àa](?:\s+elettronica)?|passaporto)"
    r"(?:\s+(?:recante|rilasciat[ao]|n\.|nr\.?|n°|numero))*\s*[:\-]?\s*)([A-Z0-9]{6,12})(?![A-Za-z0-9])",
    re.IGNORECASE,
)
RE_NASCITA = re.compile(
    r"(nat[oa]\s+)((?:a|in)\s+[^,\n;]{2,45}?\s*(?:\([A-Za-z]{2}\))?\s*,?\s*il\s+\d{1,2}\s*[/.\-]\s*\d{1,2}\s*[/.\-]\s*\d{2,4})",
    re.IGNORECASE,
)
_TIPI_VIA = (r"via|viale|v\.le|piazza|p\.zza|piazzale|corso|c\.so|largo|strada|str\.|localit[àa]|loc\.|"
             r"vicolo|lungotevere|contrada|c\.da|borgo|vicoletto")
RE_INDIRIZZO = re.compile(
    rf"(?<![A-Za-z])(?:{_TIPI_VIA})\s+[A-Za-zÀ-ÿ'’\.\s]{{2,50}}?(?:,\s*|\s+)"
    rf"(?:(?:n\.|nr\.|civ\.|n°)\s*)?\d{{1,4}}(?:\s?/?\s?[A-Za-z](?![A-Za-z]))?(?:\s*(?:int|interno|scala|sc)\.?\s*\w+)?",
    re.IGNORECASE,
)
_TITOLI = r"(?:Sig\.ra|Sig\.na|Sig\.|Sigg\.|Dott\.ssa|Dott\.|Ing\.|Avv\.|Geom\.|Rag\.|Prof\.|Arch\.|Dr\.)"
RE_TITOLATO = re.compile(
    rf"({_TITOLI}\s+)((?:[A-ZÀ-Ý][A-Za-zÀ-ÿ'’]+)(?:\s+[A-ZÀ-Ý][A-Za-zÀ-ÿ'’]+){{0,3}})"
)


def cf_valido(cf: str) -> bool:
    """Controllo del carattere di controllo del codice fiscale (16 caratteri)."""
    cf = cf.upper()
    if len(cf) != 16:
        return False
    dispari = {**dict(zip("0123456789", [1, 0, 5, 7, 9, 13, 15, 17, 19, 21])),
               **dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ",
                          [1, 0, 5, 7, 9, 13, 15, 17, 19, 21, 2, 4, 18, 20, 11, 3, 6, 8, 12, 14, 16, 10, 22, 25, 24, 23]))}
    pari = {**{c: i for i, c in enumerate("0123456789")}, **{c: i for i, c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ")}}
    tot = sum(dispari[c] if i % 2 == 0 else pari[c] for i, c in enumerate(cf[:15]))
    return "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[tot % 26] == cf[15]


def piva_valida(p: str) -> bool:
    p = re.sub(r"\D", "", p)
    if len(p) != 11:
        return False
    s = 0
    for i, ch in enumerate(p[:10]):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        s += d
    return (10 - s % 10) % 10 == int(p[10])


def iban_valido(s: str) -> bool:
    s = re.sub(r"\s", "", s).upper()
    if not (15 <= len(s) <= 34):
        return False
    r = s[4:] + s[:4]
    num = "".join(str(int(c, 36)) for c in r)
    return int(num) % 97 == 1


class LeakError(Exception):
    """Il testo contiene ancora dati riconoscibili: l'invio va bloccato."""

    def __init__(self, problemi: list[str]):
        super().__init__("Dati identificativi residui nel testo: " + "; ".join(problemi))
        self.problemi = problemi


def _pattern_da_variante(v: str) -> str:
    """Compila una variante testuale in regex tollerante a spazi, apostrofi e maiuscole."""
    out = []
    for ch in v:
        if ch.isspace():
            out.append(r"\s+")
        elif ch in "'’`´":
            out.append(_APOS)
        else:
            out.append(re.escape(ch))
    return "".join(out)


@dataclass
class Pseudonymizer:
    _voci: list[tuple[str, str, list[str]]] = field(default_factory=list)  # (categoria, canonico, varianti)
    _fwd: dict[tuple[str, str], str] = field(default_factory=dict)
    _rev: dict[str, str] = field(default_factory=dict)
    _cont: dict[str, int] = field(default_factory=dict)

    # -- anagrafica nota --------------------------------------------------------------
    def aggiungi_persona(self, nome_completo: str, cognome: str | None = None, categoria: str = "PERSONA") -> None:
        parole = [p for p in re.split(r"\s+", nome_completo.strip()) if p]
        if not parole:
            return
        var: set[str] = {" ".join(parole)}
        if len(parole) <= 4:
            import itertools
            for perm in itertools.permutations(parole):
                var.add(" ".join(perm))
        if cognome:
            var.add(cognome)
        for p in parole:
            if len(p) >= 4 and p.lower() not in _STOP_PAROLE:
                var.add(p)
        if len(parole) >= 2:  # forma "COGNOME N." e "N. Cognome"
            for p in parole:
                for q in parole:
                    if p != q and len(q) >= 1:
                        var.add(f"{p} {q[0]}.")
                        var.add(f"{q[0]}. {p}")
        self._voci.append((categoria, " ".join(parole), sorted(var, key=len, reverse=True)))

    def aggiungi_ente(self, denominazione: str) -> None:
        d = denominazione.strip().strip("“”\"'")
        if not d:
            return
        var = {d}
        nucleo = d
        while True:
            n2 = _RE_FORMA_FINALE.sub("", nucleo).strip(" ,-–\"'“”")
            if n2 == nucleo or not n2:
                break
            nucleo = n2
        if len(nucleo) >= 4:
            var.add(nucleo)
        self._voci.append(("ENTE", d, sorted(var, key=len, reverse=True)))

    def aggiungi_identificativo(self, valore: str, categoria: str) -> None:
        v = valore.strip()
        if v:
            self._voci.append((categoria, v, [v]))

    # -- utilita' interne -------------------------------------------------------------
    def _token(self, categoria: str, canonico: str) -> str:
        key = (categoria, canonico.strip().lower())
        if key not in self._fwd:
            self._cont[categoria] = self._cont.get(categoria, 0) + 1
            tok = f"[{categoria}_{self._cont[categoria]}]"
            self._fwd[key] = tok
            self._rev[tok] = canonico
        return self._fwd[key]

    @staticmethod
    def _fuori_token(testo: str):
        parti = TOKEN_RE.split(testo)  # non usato: gestiamo a mano per mantenere i token
        return parti

    def _applica(self, testo: str, rx: re.Pattern, fn) -> str:
        segmenti = re.split(r"(\[[A-Z_]+_\d+\])", testo)
        for i in range(0, len(segmenti), 2):
            segmenti[i] = rx.sub(fn, segmenti[i])
        return "".join(segmenti)

    # -- anonimizzazione --------------------------------------------------------------
    def anonimizza(self, testo: str) -> str:
        # 0) e-mail/PEC intere per prime: contengono spesso nomi e domini identificativi
        testo = self._applica(testo, RE_EMAIL, lambda m: self._token("EMAIL", m.group(0)))

        # 1) anagrafica nota (varianti piu' lunghe per prime, su tutte le categorie)
        tutte = [(len(v), cat, canon, v) for cat, canon, vs in self._voci for v in vs]
        tutte.sort(key=lambda x: -x[0])
        for _, cat, canon, v in tutte:
            rx = re.compile(r"(?<![A-Za-z0-9À-ÿ])" + _pattern_da_variante(v) + r"(?![A-Za-z0-9À-ÿ])", re.IGNORECASE)
            testo = self._applica(testo, rx, lambda m, c=cat, k=canon: self._token(c, k))

        # 2) contesti con etichetta (documenti, nascita, P.IVA/CF numerici con etichetta)
        testo = self._applica(testo, RE_DOC, lambda m: m.group(1) + self._token("DOC", m.group(2)))
        testo = self._applica(testo, RE_NASCITA, lambda m: m.group(1) + self._token("NASCITA", m.group(2)))
        testo = self._applica(testo, RE_PIVA_CTX, lambda m: m.group(1) + self._token("PIVA", m.group(2)))

        # 3) rilevatori strutturati
        testo = self._applica(testo, RE_IBAN_CAND,
                              lambda m: self._token("IBAN", m.group(0)) if iban_valido(m.group(0)) else m.group(0))
        testo = self._applica(testo, RE_CF, lambda m: self._token("CF", m.group(0).upper()))
        testo = self._applica(testo, RE_PIVA, lambda m: self._token("PIVA", m.group(0)))
        testo = self._applica(testo, RE_INDIRIZZO, lambda m: self._token("INDIRIZZO", m.group(0)))
        testo = self._applica(testo, RE_TEL, lambda m: self._token("TEL", m.group(0)))
        testo = self._applica(testo, RE_TARGA, lambda m: self._token("TARGA", m.group(0)))

        # 4) persone introdotte da un titolo (Sig., Dott., ...), non presenti in anagrafica
        testo = self._applica(testo, RE_TITOLATO, lambda m: m.group(1) + self._token("PERSONA", m.group(2)))
        return testo

    # -- verifica ---------------------------------------------------------------------
    def verifica(self, testo_anonimo: str) -> list[str]:
        problemi: list[str] = []
        pulito = TOKEN_RE.sub(" ", testo_anonimo)
        for cat, canon, vs in self._voci:
            for v in vs:
                if re.search(r"(?<![A-Za-z0-9À-ÿ])" + _pattern_da_variante(v) + r"(?![A-Za-z0-9À-ÿ])", pulito, re.IGNORECASE):
                    problemi.append(f"{cat} ancora presente")
                    break
        checks = [("CF", RE_CF), ("P.IVA/CF numerico", RE_PIVA), ("e-mail", RE_EMAIL), ("indirizzo", RE_INDIRIZZO)]
        for nome, rx in checks:
            if rx.search(pulito):
                problemi.append(f"{nome} residuo")
        for m in RE_IBAN_CAND.finditer(pulito):
            if iban_valido(m.group(0)):
                problemi.append("IBAN residuo")
                break
        return sorted(set(problemi))

    def anonimizza_o_blocca(self, testo: str) -> str:
        out = self.anonimizza(testo)
        problemi = self.verifica(out)
        if problemi:
            raise LeakError(problemi)
        return out

    # -- ripristino -------------------------------------------------------------------
    def ripristina(self, testo: str) -> tuple[str, list[str]]:
        sconosciuti: list[str] = []

        def sost(m: re.Match) -> str:
            tok = m.group(0)
            if tok in self._rev:
                return self._rev[tok]
            sconosciuti.append(tok)
            return tok

        return TOKEN_RE.sub(sost, testo), sconosciuti

    @property
    def tabella(self) -> dict[str, str]:
        return dict(self._rev)
